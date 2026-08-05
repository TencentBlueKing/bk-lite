from pathlib import Path

import pytest

from service import runtime


def create_win_copy_module(collections_root: Path) -> None:
    module_file = collections_root / "ansible_collections" / "ansible" / "windows" / "plugins" / "modules" / "win_copy.ps1"
    module_file.parent.mkdir(parents=True)
    module_file.touch()


def test_configure_ansible_environment_rejects_invalid_explicit_collection_path(tmp_path: Path, monkeypatch):
    collections_root = tmp_path / "collections"
    (collections_root / "ansible" / "windows").mkdir(parents=True)
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", str(collections_root))

    with pytest.raises(RuntimeError, match="ansible.windows win_copy"):
        runtime.configure_ansible_environment()


def test_configure_ansible_environment_rejects_invalid_bundled_collection_path(tmp_path: Path, monkeypatch):
    collections_root = tmp_path / "_internal" / "collections"
    (collections_root / "ansible" / "windows").mkdir(parents=True)
    monkeypatch.delenv("ANSIBLE_COLLECTIONS_PATH", raising=False)
    monkeypatch.setattr(runtime, "application_root", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="ansible.windows win_copy"):
        runtime.configure_ansible_environment()

    assert "ANSIBLE_COLLECTIONS_PATH" not in runtime.os.environ


def test_configure_ansible_environment_accepts_any_valid_explicit_collection_root(tmp_path: Path, monkeypatch):
    invalid_root = tmp_path / "invalid"
    valid_root = tmp_path / "valid"
    invalid_root.mkdir()
    create_win_copy_module(valid_root)
    configured_path = runtime.os.pathsep.join((str(invalid_root), str(valid_root)))
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", configured_path)

    runtime.configure_ansible_environment()

    assert runtime.os.environ["ANSIBLE_COLLECTIONS_PATH"] == configured_path


def test_configure_ansible_environment_accepts_ansible_collections_directory_itself(tmp_path: Path, monkeypatch):
    collections_root = tmp_path / "collections"
    create_win_copy_module(collections_root)
    namespace_root = collections_root / "ansible_collections"
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", str(namespace_root))

    runtime.configure_ansible_environment()

    assert runtime.os.environ["ANSIBLE_COLLECTIONS_PATH"] == str(namespace_root)
