"""WorkflowObjectStore：覆盖 put/get/delete 与下载体积分支。"""

from io import BytesIO
from types import SimpleNamespace

import pytest

from apps.workflow_orchestration.services.object_store import MAX_ARTIFACT_DOWNLOAD_BYTES, ArtifactTooLarge, WorkflowObjectStore


def _patch_store_io(mocker, *, download_return=None):
    """Make async_to_sync return a sync callable backed by mocks."""
    upload = mocker.Mock()
    delete = mocker.Mock()
    download = mocker.Mock(return_value=download_return)

    def async_to_sync(fn):
        name = getattr(fn, "__name__", "")
        if name == "upload_file_to_s3" or fn is upload:
            return upload
        if name == "delete_s3_file" or fn is delete:
            return delete
        return download

    mocker.patch("apps.workflow_orchestration.services.object_store.async_to_sync", side_effect=async_to_sync)
    mocker.patch("apps.workflow_orchestration.services.object_store.upload_file_to_s3", upload)
    mocker.patch("apps.workflow_orchestration.services.object_store.delete_s3_file", delete)
    mocker.patch("apps.workflow_orchestration.services.object_store.download_file_by_s3", download)
    return upload, delete, download


def test_put_and_delete_delegate_to_s3(mocker):
    upload, delete, _ = _patch_store_io(mocker)
    store = WorkflowObjectStore()

    store.put("reports/a.docx", b"content")
    upload.assert_called_once_with(b"content", "reports/a.docx")

    store.delete("reports/a.docx")
    delete.assert_called_once_with("reports/a.docx")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ((b"abc", "file.docx", 3), (b"abc", "file.docx", 3)),
        ((b"abc", "file.docx", 0), (b"abc", "file.docx", 3)),
        ((b"xyz", "named.bin"), (b"xyz", "named.bin", 3)),
        ((b"xyz", ""), (b"xyz", "key.bin", 3)),
        (b"raw-bytes", (b"raw-bytes", "key.bin", 9)),
        (SimpleNamespace(data=b"from-attr"), (b"from-attr", "key.bin", 9)),
        (SimpleNamespace(data=BytesIO(b"streamed")), (b"streamed", "key.bin", 8)),
    ],
)
def test_get_normalizes_payload_shapes(mocker, payload, expected):
    _, _, download = _patch_store_io(mocker, download_return=payload)

    content, filename, size = WorkflowObjectStore().get("path/to/key.bin")

    assert (content, filename, size) == expected
    download.assert_called_once_with("path/to/key.bin")


def test_get_raises_when_content_exceeds_limit(mocker):
    oversized = b"x" * (MAX_ARTIFACT_DOWNLOAD_BYTES + 1)
    store = WorkflowObjectStore()

    for payload in (
        (oversized, "big.bin", len(oversized)),
        (oversized, "big.bin"),
        oversized,
    ):
        _patch_store_io(mocker, download_return=payload)
        with pytest.raises(ArtifactTooLarge, match="超过下载大小限制"):
            store.get("reports/big.bin")

    _patch_store_io(mocker, download_return=oversized)
    content, filename, size = store.get("reports/big.bin", max_bytes=None)
    assert content == oversized
    assert filename == "big.bin"
    assert size == len(oversized)
