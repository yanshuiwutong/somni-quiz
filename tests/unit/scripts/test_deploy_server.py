from __future__ import annotations

from types import SimpleNamespace

import scripts.deploy_server as deploy_server


class DummySSHClient:
    def __init__(self) -> None:
        self.policy = None
        self.connect_kwargs = None

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs


def test_connect_ssh_disables_key_and_agent_auth(monkeypatch) -> None:
    dummy_client = DummySSHClient()
    monkeypatch.setattr(deploy_server.paramiko, "SSHClient", lambda: dummy_client)
    monkeypatch.setattr(deploy_server.paramiko, "AutoAddPolicy", lambda: "policy")

    args = SimpleNamespace(host="example.com", user="root", password="secret")

    client = deploy_server._connect_ssh(args)

    assert client is dummy_client
    assert dummy_client.policy == "policy"
    assert dummy_client.connect_kwargs == {
        "hostname": "example.com",
        "username": "root",
        "password": "secret",
        "timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 20,
        "look_for_keys": False,
        "allow_agent": False,
    }
