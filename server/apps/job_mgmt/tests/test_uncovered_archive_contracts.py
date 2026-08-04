"""补齐 playbook 归档探测和资源上限契约。"""

import io
import tarfile

import pytest

from apps.job_mgmt.utils import playbook_archive
from apps.job_mgmt.utils.playbook_archive import ArchiveInfo


pytestmark = pytest.mark.unit


def _tar_upload():
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        directory = tarfile.TarInfo("roles/")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        content = b"- debug: msg=hello"
        member = tarfile.TarInfo("roles/main.yml")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    payload.name = "playbook.tgz"
    payload.seek(3)
    return payload


def test_archive_size_fallback_preserves_cursor_and_tar_inspection_skips_dirs():
    upload = _tar_upload()
    cursor = upload.tell()
    assert playbook_archive.get_archive_file_size(upload) > 0
    assert upload.tell() == cursor

    info = playbook_archive.inspect_archive(upload)
    assert info.archive_type == "tar"
    assert info.member_count == 1
    assert info.max_member_size == len(b"- debug: msg=hello")
    assert upload.tell() == 0


def test_archive_helpers_reject_unknown_or_unmeasurable_inputs():
    with pytest.raises(ValueError, match="无法确定"):
        playbook_archive.get_archive_file_size(object())
    unnamed = io.BytesIO(b"not an archive")
    unnamed.name = "playbook.rar"
    with pytest.raises(ValueError, match="仅支持"):
        with playbook_archive.open_archive(unnamed):
            pass


@pytest.mark.parametrize(
    ("info", "message"),
    [
        (
            ArchiveInfo(
                "zip",
                1,
                1,
                playbook_archive.PLAYBOOK_ARCHIVE_MAX_MEMBER_SIZE_BYTES + 1,
                1,
            ),
            "单文件过大",
        ),
        (
            ArchiveInfo(
                "zip",
                1,
                1,
                1,
                playbook_archive.PLAYBOOK_ARCHIVE_MAX_EXPANDED_SIZE_BYTES + 1,
            ),
            "解压总量过大",
        ),
    ],
)
def test_archive_limits_report_the_specific_unsafe_expansion(
    monkeypatch, info, message
):
    monkeypatch.setattr(playbook_archive, "inspect_archive", lambda _file: info)
    with pytest.raises(ValueError, match=message):
        playbook_archive.enforce_archive_limits(object())
