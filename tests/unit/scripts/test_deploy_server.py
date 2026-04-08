"""Tests for the deployment helper script."""

from __future__ import annotations

import importlib.util
import tarfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "deploy_server.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("deploy_server", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_archive_excludes_local_dotenv(tmp_path: Path) -> None:
    module = _load_module()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".env").write_text("SOMNI_GRPC_PORT=19000\n", encoding="utf-8")
    (project_root / "README.md").write_text("hello\n", encoding="utf-8")
    (project_root / "src").mkdir()
    (project_root / "src" / "module.py").write_text("print('hi')\n", encoding="utf-8")

    module.PROJECT_ROOT = project_root

    archive = module._build_archive()
    try:
        with tarfile.open(archive, "r:gz") as handle:
            names = set(handle.getnames())
    finally:
        archive.unlink(missing_ok=True)

    assert ".env" not in names
    assert "README.md" in names
    assert "src/module.py" in names


def test_refresh_services_restarts_targets(monkeypatch) -> None:
    module = _load_module()
    events: list[tuple[str, str]] = []

    monkeypatch.setattr(module, "_run", lambda ssh, command, timeout=300: events.append(("run", command)) or "")
    monkeypatch.setattr(
        module,
        "_run_allow_failure",
        lambda ssh, command, timeout=300: events.append(("allow", command)) or "",
    )

    module._refresh_services(object())

    assert events == [
        ("run", "systemctl daemon-reload"),
        ("allow", "systemctl disable --now somni-streamlit-51062.service"),
        ("allow", "systemctl disable --now somni-api-18000.service"),
        ("run", "systemctl enable somni-graph-quiz-streamlit.service somni-graph-quiz-grpc.service"),
        ("run", "systemctl restart somni-graph-quiz-streamlit.service somni-graph-quiz-grpc.service"),
        ("run", "systemctl status somni-graph-quiz-streamlit.service --no-pager"),
        ("run", "systemctl status somni-graph-quiz-grpc.service --no-pager"),
    ]
