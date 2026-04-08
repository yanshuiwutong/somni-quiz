from __future__ import annotations

import argparse
import os
import tarfile
import tempfile
from pathlib import Path

import paramiko


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = "/root/somni-graph-quiz"
STREAMLIT_PORT = 51062
GRPC_PORT = 18000
SYSTEMD_STREAMLIT_UNIT = "/etc/systemd/system/somni-graph-quiz-streamlit.service"
SYSTEMD_GRPC_UNIT = "/etc/systemd/system/somni-graph-quiz-grpc.service"


def _build_archive() -> Path:
    fd, archive_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    archive = Path(archive_path)
    excluded_dirs = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", ".venv", "venv"}
    excluded_suffixes = {".pyc", ".pyo"}

    with tarfile.open(archive, "w:gz") as tar:
        for path in PROJECT_ROOT.rglob("*"):
            if any(part in excluded_dirs for part in path.parts):
                continue
            if path.name == ".env":
                continue
            if path.suffix in excluded_suffixes:
                continue
            tar.add(path, arcname=path.relative_to(PROJECT_ROOT).as_posix(), recursive=False)
    return archive


def _load_env_text() -> str:
    env_path = PROJECT_ROOT / ".env"
    text = env_path.read_text(encoding="utf-8")
    return text.replace("SOMNI_GRPC_PORT=19000", f"SOMNI_GRPC_PORT={GRPC_PORT}")


def _run(ssh: paramiko.SSHClient, command: str, timeout: int = 300) -> str:
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    rc = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    if rc != 0:
        raise RuntimeError(f"{command}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    return out


def _run_allow_failure(ssh: paramiko.SSHClient, command: str, timeout: int = 300) -> str:
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return out + err


def _streamlit_unit(conda_root: str, env_name: str) -> str:
    return f"""[Unit]
Description=Somni Graph Quiz Streamlit (51062)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={REMOTE_ROOT}
EnvironmentFile={REMOTE_ROOT}/.env
ExecStart={conda_root} run -n {env_name} python -m streamlit run {REMOTE_ROOT}/app.py --server.address 0.0.0.0 --server.port {STREAMLIT_PORT} --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""


def _grpc_unit(conda_root: str, env_name: str) -> str:
    return f"""[Unit]
Description=Somni Graph Quiz gRPC (18000)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={REMOTE_ROOT}
EnvironmentFile={REMOTE_ROOT}/.env
Environment=SOMNI_GRPC_PORT={GRPC_PORT}
ExecStart={conda_root} run -n {env_name} python -m somni_graph_quiz.adapters.grpc
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""


def _refresh_services(ssh: paramiko.SSHClient) -> None:
    _run(ssh, "systemctl daemon-reload")
    _run_allow_failure(ssh, "systemctl disable --now somni-streamlit-51062.service", timeout=120)
    _run_allow_failure(ssh, "systemctl disable --now somni-api-18000.service", timeout=120)
    _run(ssh, "systemctl enable somni-graph-quiz-streamlit.service somni-graph-quiz-grpc.service", timeout=120)
    _run(ssh, "systemctl restart somni-graph-quiz-streamlit.service somni-graph-quiz-grpc.service", timeout=120)
    _run(ssh, "systemctl status somni-graph-quiz-streamlit.service --no-pager", timeout=120)
    _run(ssh, "systemctl status somni-graph-quiz-grpc.service --no-pager", timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--remote-root", default=REMOTE_ROOT)
    parser.add_argument("--conda-bin", default="/root/miniconda3/bin/conda")
    parser.add_argument("--env-name", default="somni-graph-quiz")
    args = parser.parse_args()

    archive = _build_archive()
    env_text = _load_env_text()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        args.host,
        username=args.user,
        password=args.password,
        timeout=20,
        banner_timeout=20,
        auth_timeout=20,
    )
    try:
        _run(ssh, f"mkdir -p {args.remote_root}")
        sftp = ssh.open_sftp()
        try:
            sftp.put(str(archive), "/tmp/somni-graph-quiz.tar.gz")
            with sftp.open(f"{args.remote_root}/.env", "w") as handle:
                handle.write(env_text)
            with sftp.open(SYSTEMD_STREAMLIT_UNIT, "w") as handle:
                handle.write(_streamlit_unit(args.conda_bin, args.env_name))
            with sftp.open(SYSTEMD_GRPC_UNIT, "w") as handle:
                handle.write(_grpc_unit(args.conda_bin, args.env_name))
        finally:
            sftp.close()

        _run(ssh, f"tar -xzf /tmp/somni-graph-quiz.tar.gz -C {args.remote_root}")
        _run_allow_failure(
            ssh,
            (
                f"bash -lc 'if [ ! -x /root/miniconda3/envs/{args.env_name}/bin/python ]; "
                f"then {args.conda_bin} create -y -n {args.env_name} python=3.11; fi'"
            ),
            timeout=1800,
        )
        _run(ssh, f"{args.conda_bin} run -n {args.env_name} python -m pip install -e {args.remote_root}", timeout=1800)
        _refresh_services(ssh)
    finally:
        ssh.close()
        archive.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
