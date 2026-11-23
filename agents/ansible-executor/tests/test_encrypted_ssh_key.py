"""Both Ansible SSH invocations must consume the same unlocked, private, task-local key."""

import asyncio
import os
import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from service import ansible_runner as runner
from service.linux_script_delivery import _private_key_path

PASSPHRASE = "test-passphrase-for-job-target"


def _encrypted_key(key_format):
    if key_format == "openssh":
        key = ed25519.Ed25519PrivateKey.generate()
        private_format = serialization.PrivateFormat.OpenSSH
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_format = serialization.PrivateFormat.TraditionalOpenSSL
    content = key.private_bytes(serialization.Encoding.PEM, private_format, serialization.BestAvailableEncryption(PASSPHRASE.encode())).decode()
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
    return content, public


def _prepare(which, credentials):
    if which == "adhoc":
        request = runner.AdhocRequest(module="ping", host_credentials=credentials)
        return runner.prepare_adhoc_execution(request)[1]
    request = runner.PlaybookRequest(playbook_content="- hosts: all\n  tasks: []", host_credentials=credentials)
    return asyncio.run(runner.prepare_playbook_execution(None, request))[1]


@pytest.mark.parametrize("which", ["adhoc", "playbook"])
@pytest.mark.parametrize("key_format", ["openssh", "pem"])
def test_ssh_reads_original_public_identity_without_interactive_passphrase(tmp_path, monkeypatch, which, key_format):
    monkeypatch.setattr(runner, "BASE_TASK_DIR", tmp_path)
    content, expected = _encrypted_key(key_format)
    host = {"connection": "ssh", "host": "192.0.2.12", "user": "reader", "private_key_content": content, "private_key_passphrase": PASSPHRASE}
    opened = []
    real_open = os.open

    def record_create(path, flags, mode=0o777, *args, **kwargs):
        if Path(path).name.startswith("id_rsa") and flags & os.O_CREAT:
            opened.append((mode, flags))
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", record_create)
    workspace = _prepare(which, [host])
    try:
        key_file = workspace / "id_rsa_0"
        assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
        assert len(opened) == 1 and opened[0][0] == 0o600 and opened[0][1] & os.O_EXCL
        inventory = (workspace / "inventory.ini").read_text()
        assert str(key_file) in inventory
        assert content not in inventory and PASSPHRASE not in inventory
        assert _private_key_path(workspace, 0, host) == str(key_file)
        output = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(key_file)], stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=True
        )
        assert output.stdout.strip().split()[:2] == expected.split()
    finally:
        runner.cleanup_workspace(workspace)
    assert not workspace.exists()


@pytest.mark.parametrize("which", ["adhoc", "playbook"])
def test_wrong_passphrase_removes_all_prepared_keys_without_disclosing_material(tmp_path, monkeypatch, which):
    monkeypatch.setattr(runner, "BASE_TASK_DIR", tmp_path)
    content, _ = _encrypted_key("openssh")
    host = {"host": "192.0.2.13", "connection": "ssh", "private_key_content": content, "private_key_passphrase": PASSPHRASE}
    with pytest.raises(ValueError, match="SSH private key or passphrase is invalid") as error:
        _prepare(which, [host, {**host, "host": "192.0.2.14", "private_key_passphrase": "wrong-passphrase"}])
    assert content not in str(error.value) and "wrong-passphrase" not in str(error.value)
    assert not list(tmp_path.iterdir())
