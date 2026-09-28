import io
from unittest.mock import Mock

import pytest

from apps.cmdb.services.transfer_files import TransferFiles
from apps.cmdb.services.transfer_service import TransferError


def test_storage_reuses_private_bucket_and_restricts_cleanup_prefix():
    client = Mock()
    files = TransferFiles(client=client)
    key = "transfer/1/abc/attempt/result.xlsx"
    result = files.put(key, io.BytesIO(b"example"))
    assert result == {"key": key, "size": 7}
    assert client.put_object.call_args.kwargs["bucket_name"] == "cmdb-config-file"
    assert client.put_object.call_args.kwargs["length"] == 7
    files.delete(key)
    client.remove_object.assert_called_once_with("cmdb-config-file", key)
    with pytest.raises(TransferError):
        files.delete("tmp/config-file/a.txt")
    with pytest.raises(TransferError):
        files.delete("transfer/../../configuration.txt")
    assert client.remove_object.call_count == 1


def test_output_budget_stops_zip_writes_before_exceeding_disk_limit():
    from apps.cmdb.services.transfer_files import BoundedWriter

    stream = io.BytesIO()
    bounded = BoundedWriter(stream, 8)
    bounded.write(b"12345678")
    with pytest.raises(TransferError):
        bounded.write(b"9")
    assert stream.getvalue() == b"12345678"
    bounded.seek(0)
    bounded.write(b"XY")
    assert stream.getvalue() == b"XY345678"


def test_streaming_copy_closes_remote_even_when_budget_exceeded():
    from types import SimpleNamespace

    client = Mock()
    source = io.BytesIO(b"12345")
    remote = SimpleNamespace(read=source.read, close=Mock(), release_conn=Mock())
    client.get_object.return_value = remote
    files = TransferFiles(client)
    with files.local_copy("transfer/tmp/source.xlsx", max_bytes=5) as copied:
        assert copied.read() == b"12345"
    remote.close.assert_called_once()
    remote.release_conn.assert_called_once()
    source.seek(0)
    with pytest.raises(TransferError):
        with files.local_copy("transfer/tmp/source.xlsx", max_bytes=4):
            pytest.fail("Oversized file must not be exposed")
    assert remote.close.call_count == 2
    assert remote.release_conn.call_count == 2
    client.list_objects.return_value = [SimpleNamespace(object_name=str(i)) for i in range(5)]
    assert [item.object_name for item in files.scan(cursor="prior", limit=2)] == ["0", "1"]


def test_first_upload_initializes_only_configured_bucket_when_save_check_enabled(settings):
    from minio.error import S3Error

    settings.MINIO_BUCKET_CHECK_ON_SAVE = True
    client = Mock()
    exists = False

    def create_bucket(bucket_name):
        nonlocal exists
        assert bucket_name == "cmdb-config-file"
        exists = True

    def upload(**kwargs):
        if not exists:
            raise S3Error("NoSuchBucket", "PRIVATE-STORAGE-SENTINEL", "resource", "request", "host", None)

    client.bucket_exists.side_effect = lambda bucket: exists
    client.make_bucket.side_effect = create_bucket
    client.put_object.side_effect = upload
    files = TransferFiles(client)
    for name in ("result.xlsx", "manifest.jsonl"):
        files.put(f"transfer/owner/task/attempt/{name}", io.BytesIO(b"data"))
    client.make_bucket.assert_called_once_with(bucket_name="cmdb-config-file")
    assert client.put_object.call_count == 2


@pytest.mark.parametrize("code", ["BucketAlreadyOwnedByYou", "AccessDenied"])
def test_bucket_initialization_race_only_accepts_existing_owned_bucket(settings, code):
    from minio.error import S3Error

    settings.MINIO_BUCKET_CHECK_ON_SAVE = True
    client = Mock()
    client.bucket_exists.return_value = False
    error = S3Error(code, "PRIVATE-SENTINEL", "resource", "request", "host", None)
    client.make_bucket.side_effect = error
    files = TransferFiles(client)
    if code == "BucketAlreadyOwnedByYou":
        files.put("transfer/tmp/test/result.xlsx", io.BytesIO(b"data"))
        client.put_object.assert_called_once()
    else:
        with pytest.raises(S3Error) as caught:
            files.put("transfer/tmp/test/result.xlsx", io.BytesIO(b"data"))
        assert caught.value is error
        client.put_object.assert_not_called()
        client.make_bucket.side_effect = None
        files.put("transfer/tmp/test/result.xlsx", io.BytesIO(b"data"))
        assert client.make_bucket.call_count == 2


def test_disabled_bucket_save_check_never_creates_bucket(settings):
    settings.MINIO_BUCKET_CHECK_ON_SAVE = False
    client = Mock()
    TransferFiles(client).put("transfer/tmp/test/result.xlsx", io.BytesIO(b"data"))
    client.bucket_exists.assert_not_called()
    client.make_bucket.assert_not_called()
    client.put_object.assert_called_once()
