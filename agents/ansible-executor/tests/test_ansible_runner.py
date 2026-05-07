import zipfile

import pytest

from core.config import ServiceConfig
from service import ansible_runner
from service.ansible_runner import _safe_extract_zip, _safe_workspace_path
from service.ansible_runner import PlaybookRequest, prepare_playbook_execution


def test_safe_workspace_path_rejects_parent_escape(tmp_path):
    with pytest.raises(ValueError):
        _safe_workspace_path(tmp_path, "../evil.txt", "file name")


def test_safe_extract_zip_rejects_symlink(tmp_path):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "target.txt")

    with zipfile.ZipFile(archive_path, "r") as archive:
        with pytest.raises(ValueError):
            _safe_extract_zip(archive, tmp_path / "workspace")


def test_safe_extract_zip_allows_regular_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/file.txt", "hello")

    with zipfile.ZipFile(archive_path, "r") as archive:
        _safe_extract_zip(archive, workspace)

    assert (workspace / "nested" / "file.txt").read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_prepare_playbook_execution_rejects_unsafe_zip_member(tmp_path, monkeypatch):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.yml", "- hosts: all\n")
        archive.writestr("playbook.yml", "- hosts: all\n")

    async def fake_download(config, workspace, bucket_name, file_item):
        return str(archive_path)

    monkeypatch.setattr(ansible_runner, "BASE_TASK_DIR", tmp_path / "work")
    monkeypatch.setattr(ansible_runner, "download_object_to_workspace", fake_download)

    config = ServiceConfig(nats_servers=["nats://127.0.0.1:4222"], nats_instance_id="default")
    request = PlaybookRequest(
        playbook_path="playbook.yml",
        inventory_content="[all]\n127.0.0.1 ansible_connection=local\n",
        files=[{"name": "payload.zip", "file_key": "payload.zip", "bucket_name": "bucket"}],
    )

    with pytest.raises(ValueError, match="zip member"):
        await prepare_playbook_execution(config, request)


@pytest.mark.asyncio
async def test_prepare_playbook_execution_rejects_ambiguous_zip_playbook_entry(tmp_path, monkeypatch):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("alpha/playbook.yml", "- hosts: all\n")
        archive.writestr("beta/playbook.yml", "- hosts: all\n")

    async def fake_download(config, workspace, bucket_name, file_item):
        return str(archive_path)

    monkeypatch.setattr(ansible_runner, "BASE_TASK_DIR", tmp_path / "work")
    monkeypatch.setattr(ansible_runner, "download_object_to_workspace", fake_download)

    config = ServiceConfig(nats_servers=["nats://127.0.0.1:4222"], nats_instance_id="default")
    request = PlaybookRequest(
        playbook_path="playbook.yml",
        inventory_content="[all]\n127.0.0.1 ansible_connection=local\n",
        files=[{"name": "payload.zip", "file_key": "payload.zip", "bucket_name": "bucket"}],
    )

    with pytest.raises(ValueError, match="多个入口文件"):
        await prepare_playbook_execution(config, request)


@pytest.mark.asyncio
async def test_prepare_playbook_execution_prefers_exact_zip_playbook_path(tmp_path, monkeypatch):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bundle/playbook.yml", "- hosts: all\n")
        archive.writestr("bundle/nested/playbook.yml", "- hosts: all\n")

    async def fake_download(config, workspace, bucket_name, file_item):
        return str(archive_path)

    monkeypatch.setattr(ansible_runner, "BASE_TASK_DIR", tmp_path / "work")
    monkeypatch.setattr(ansible_runner, "download_object_to_workspace", fake_download)

    config = ServiceConfig(nats_servers=["nats://127.0.0.1:4222"], nats_instance_id="default")
    request = PlaybookRequest(
        playbook_path="bundle/nested/playbook.yml",
        inventory_content="[all]\n127.0.0.1 ansible_connection=local\n",
        files=[{"name": "payload.zip", "file_key": "payload.zip", "bucket_name": "bucket"}],
    )

    _, workspace, prepared_request = await prepare_playbook_execution(config, request)

    assert prepared_request.playbook_path == str(workspace / "bundle" / "nested" / "playbook.yml")


@pytest.mark.asyncio
async def test_prepare_playbook_execution_rejects_missing_explicit_zip_playbook_path(tmp_path, monkeypatch):
    archive_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("other/playbook.yml", "- hosts: all\n")

    async def fake_download(config, workspace, bucket_name, file_item):
        return str(archive_path)

    monkeypatch.setattr(ansible_runner, "BASE_TASK_DIR", tmp_path / "work")
    monkeypatch.setattr(ansible_runner, "download_object_to_workspace", fake_download)

    config = ServiceConfig(nats_servers=["nats://127.0.0.1:4222"], nats_instance_id="default")
    request = PlaybookRequest(
        playbook_path="bundle/playbook.yml",
        inventory_content="[all]\n127.0.0.1 ansible_connection=local\n",
        files=[{"name": "payload.zip", "file_key": "payload.zip", "bucket_name": "bucket"}],
    )

    with pytest.raises(ValueError, match="ZIP 解压后未找到入口文件: bundle/playbook.yml"):
        await prepare_playbook_execution(config, request)
