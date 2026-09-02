"""SSH SFTP 传输：上传校验本地文件、下载、列目录、删除、递归建目录。"""
import os
import stat
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.ssh import transfer as t

pytestmark = pytest.mark.unit


def _ssh(sftp):
    client = MagicMock()
    client.open_sftp.return_value = sftp
    return client


def test_upload_file_requires_existing_file(tmp_path):
    missing = str(tmp_path / "nope.txt")
    with pytest.raises(FileNotFoundError, match="本地文件不存在"):
        t.upload_file.invoke({"host": "h", "username": "u", "local_path": missing, "remote_path": "/r/a.txt", "password": "p"})
    with pytest.raises(ValueError, match="路径不是文件"):
        t.upload_file.invoke({"host": "h", "username": "u", "local_path": str(tmp_path), "remote_path": "/r/a.txt", "password": "p"})


def test_upload_file_creates_remote_dir_and_puts(tmp_path):
    local = tmp_path / "a.txt"
    local.write_text("hello")
    sftp = MagicMock()
    sftp.stat.side_effect = IOError("missing")
    with patch.object(t, "create_ssh_client", return_value=_ssh(sftp)):
        out = t.upload_file.invoke(
            {
                "host": "h",
                "username": "u",
                "local_path": str(local),
                "remote_path": "/opt/app/a.txt",
                "password": "p",
                "create_directories": True,
            }
        )
    assert out["success"] is True
    assert out["bytes_transferred"] == 5
    sftp.put.assert_called_once_with(str(local), "/opt/app/a.txt")
    sftp.mkdir.assert_called()
    sftp.close.assert_called()


def test_download_file_creates_local_dir(tmp_path):
    dest = tmp_path / "nested" / "b.txt"
    sftp = MagicMock()

    def _get(remote, local):
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "w") as fh:
            fh.write("data")

    sftp.get.side_effect = _get
    with patch.object(t, "create_ssh_client", return_value=_ssh(sftp)):
        out = t.download_file.invoke(
            {
                "host": "h",
                "username": "u",
                "remote_path": "/r/b.txt",
                "local_path": str(dest),
                "password": "p",
            }
        )
    assert out["success"] is True
    assert dest.read_text() == "data"
    assert out["bytes_transferred"] == 4


def test_list_remote_directory_skips_hidden_and_splits_dirs():
    file_item = SimpleNamespace(filename="a.txt", st_size=10, st_mode=stat.S_IFREG | 0o644, st_mtime=1)
    dir_item = SimpleNamespace(filename="sub", st_size=0, st_mode=stat.S_IFDIR | 0o755, st_mtime=2)
    hidden = SimpleNamespace(filename=".secret", st_size=1, st_mode=stat.S_IFREG | 0o600, st_mtime=3)
    sftp = MagicMock()
    sftp.listdir_attr.return_value = [file_item, dir_item, hidden]
    with patch.object(t, "create_ssh_client", return_value=_ssh(sftp)):
        out = t.list_remote_directory.invoke({"host": "h", "username": "u", "remote_path": "/opt", "password": "p"})
    assert out["total_items"] == 2
    assert [i["name"] for i in out["files"]] == ["a.txt"]
    assert [i["name"] for i in out["directories"]] == ["sub"]


def test_delete_remote_file_success_and_error():
    sftp = MagicMock()
    with patch.object(t, "create_ssh_client", return_value=_ssh(sftp)):
        out = t.delete_remote_file.invoke({"host": "h", "username": "u", "remote_path": "/tmp/x", "password": "p"})
    assert out["success"] is True
    sftp.remove.assert_called_once_with("/tmp/x")

    sftp.remove.side_effect = IOError("denied")
    with patch.object(t, "create_ssh_client", return_value=_ssh(sftp)):
        with pytest.raises(Exception, match="删除文件失败"):
            t.delete_remote_file.invoke({"host": "h", "username": "u", "remote_path": "/tmp/x", "password": "p"})
