from pathlib import Path

import pytest

import build_support


def test_ansible_collection_data_keeps_ansible_collections_directory(tmp_path: Path):
    collections_root = tmp_path / "collections-root"
    source_root = collections_root / "ansible_collections"
    module_file = source_root / "ansible" / "windows" / "plugins" / "modules" / "win_copy.ps1"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("# fixture", encoding="utf-8")

    datas = build_support.ansible_collections_root_to_datas(collections_root)

    assert datas == [(str(source_root.resolve()), "collections/ansible_collections")]


def test_packaged_collection_verification_rejects_missing_win_copy(tmp_path: Path):
    packaged_root = tmp_path / "ansible-executor"
    packaged_root.mkdir()

    with pytest.raises(RuntimeError, match="win_copy.ps1"):
        build_support.verify_packaged_ansible_windows_collection(packaged_root)


def test_packaged_collection_verification_accepts_win_copy(tmp_path: Path):
    packaged_root = tmp_path / "ansible-executor"
    module_file = packaged_root / "_internal" / "collections" / "ansible_collections" / "ansible" / "windows" / "plugins" / "modules" / "win_copy.ps1"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("# fixture", encoding="utf-8")

    assert build_support.verify_packaged_ansible_windows_collection(packaged_root) == module_file
