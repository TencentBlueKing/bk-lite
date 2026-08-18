"""Issue #4648：对象存储异常路径必须释放连接与临时文件。"""

import asyncio
import io
import os
import tempfile
from types import SimpleNamespace

import pytest
from django.http import StreamingHttpResponse
from nats.js.errors import ObjectNotFoundError

from apps.node_mgmt.services import package as package_service
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.utils import s3

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "operation",
    ["upload", "download", "delete", "list"],
)
@pytest.mark.asyncio
async def test_single_object_helpers_close_connection_when_operation_fails(
    monkeypatch,
    operation,
):
    instances = []

    class FailingJetStreamService:
        def __init__(self):
            self.nc = None
            self.close_count = 0
            instances.append(self)

        async def connect(self):
            self.nc = object()

        async def close(self):
            self.close_count += 1

        async def put(self, *args, **kwargs):
            raise RuntimeError("operation failed")

        async def get(self, *args, **kwargs):
            raise RuntimeError("operation failed")

        async def delete(self, *args, **kwargs):
            raise RuntimeError("operation failed")

        async def list_objects(self, *args, **kwargs):
            raise RuntimeError("operation failed")

    monkeypatch.setattr(s3, "JetStreamService", FailingJetStreamService)

    with pytest.raises(RuntimeError, match="operation failed"):
        if operation == "upload":
            await s3.upload_file_to_s3(
                SimpleNamespace(name="agent.tar.gz", file=io.BytesIO(b"payload")),
                "packages/agent.tar.gz",
            )
        elif operation == "download":
            await s3.download_file_by_s3("packages/agent.tar.gz")
        elif operation == "delete":
            await s3.delete_s3_file("packages/agent.tar.gz")
        else:
            await s3.list_s3_files()

    assert instances[0].close_count == 1


@pytest.mark.asyncio
async def test_single_object_helper_closes_partially_initialized_connection(
    monkeypatch,
):
    instances = []

    class FailingJetStreamService:
        def __init__(self):
            self.nc = None
            self.close_count = 0
            instances.append(self)

        async def connect(self):
            self.nc = object()
            raise RuntimeError("object store initialization failed")

        async def close(self):
            self.close_count += 1

    monkeypatch.setattr(s3, "JetStreamService", FailingJetStreamService)

    with pytest.raises(RuntimeError, match="object store initialization failed"):
        await s3.download_file_by_s3("packages/agent.tar.gz")

    assert instances[0].close_count == 1


@pytest.mark.asyncio
async def test_close_failure_does_not_replace_object_operation_failure(
    monkeypatch,
):
    class FailingJetStreamService:
        nc = object()

        async def connect(self):
            return None

        async def get(self, *args, **kwargs):
            raise RuntimeError("operation failed")

        async def close(self):
            raise RuntimeError("close failed")

    monkeypatch.setattr(s3, "JetStreamService", FailingJetStreamService)

    with pytest.raises(RuntimeError, match="operation failed"):
        await s3.download_file_by_s3("packages/agent.tar.gz")


@pytest.mark.asyncio
async def test_close_cancellation_does_not_replace_object_operation_failure(
    monkeypatch,
):
    class CancelledClosingJetStreamService:
        nc = object()

        async def connect(self):
            return None

        async def get(self, *args, **kwargs):
            raise RuntimeError("operation failed")

        async def close(self):
            raise asyncio.CancelledError

    monkeypatch.setattr(s3, "JetStreamService", CancelledClosingJetStreamService)

    with pytest.raises(RuntimeError, match="operation failed"):
        await s3.download_file_by_s3("packages/agent.tar.gz")


@pytest.mark.asyncio
async def test_cancellation_during_close_is_not_swallowed(monkeypatch):
    close_started = asyncio.Event()

    class SlowClosingJetStreamService:
        async def connect(self):
            return None

        async def get(self, *args, **kwargs):
            return b"payload", "agent.tar.gz"

        async def close(self):
            close_started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(s3, "JetStreamService", SlowClosingJetStreamService)

    download = asyncio.create_task(s3.download_file_by_s3("packages/agent.tar.gz"))
    await close_started.wait()
    download.cancel()

    with pytest.raises(asyncio.CancelledError):
        await download


@pytest.mark.asyncio
async def test_cancellation_during_operation_still_closes_connection(monkeypatch):
    operation_started = asyncio.Event()
    instances = []

    class CancelledJetStreamService:
        def __init__(self):
            self.close_count = 0
            instances.append(self)

        async def connect(self):
            return None

        async def get(self, *args, **kwargs):
            operation_started.set()
            await asyncio.Event().wait()

        async def close(self):
            self.close_count += 1

    monkeypatch.setattr(s3, "JetStreamService", CancelledJetStreamService)

    download = asyncio.create_task(s3.download_file_by_s3("packages/agent.tar.gz"))
    await operation_started.wait()
    download.cancel()

    with pytest.raises(asyncio.CancelledError):
        await download

    assert instances[0].close_count == 1


@pytest.mark.asyncio
async def test_close_timeout_is_bounded_and_does_not_replace_success(
    monkeypatch,
):
    close_started = asyncio.Event()

    class HangingCloseJetStreamService:
        async def connect(self):
            return None

        async def get(self, *args, **kwargs):
            return b"payload", "agent.tar.gz"

        async def close(self):
            close_started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(s3, "JetStreamService", HangingCloseJetStreamService)
    monkeypatch.setattr(s3, "JETSTREAM_CLOSE_TIMEOUT_SECONDS", 0.01)

    result = await asyncio.wait_for(
        s3.download_file_by_s3("packages/agent.tar.gz"),
        timeout=0.1,
    )

    assert close_started.is_set()
    assert result == (b"payload", "agent.tar.gz")


def _package():
    return SimpleNamespace(
        os="linux",
        cpu_architecture="x86_64",
        object="sidecar",
        version="1.0.0",
        name="sidecar.tar.gz",
    )


def _capture_named_tempfiles(monkeypatch, tmp_path):
    created_paths = []
    original = tempfile.NamedTemporaryFile

    def recording_named_temporary_file(*args, **kwargs):
        kwargs["dir"] = tmp_path
        value = original(*args, **kwargs)
        created_paths.append(value.name)
        return value

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", recording_named_temporary_file)
    return created_paths


def test_streaming_download_removes_tempfile_when_object_read_fails(
    monkeypatch,
    tmp_path,
):
    created_paths = _capture_named_tempfiles(monkeypatch, tmp_path)
    instances = []

    class ObjectStore:
        async def get_info(self, key):
            return SimpleNamespace(description="sidecar.tar.gz")

        async def get(self, key, writeinto):
            raise RuntimeError("object read interrupted")

    class FailingJetStreamService:
        def __init__(self):
            self.object_store = ObjectStore()
            self.close_count = 0
            instances.append(self)

        async def connect(self):
            return None

        async def close(self):
            self.close_count += 1
            raise RuntimeError("close failed")

    monkeypatch.setattr(
        "apps.rpc.jetstream.JetStreamService",
        FailingJetStreamService,
    )

    with pytest.raises(RuntimeError, match="object read interrupted"):
        PackageService.download_file_streaming(_package())

    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])
    assert instances[0].close_count == 1


def test_streaming_download_retries_unlink_after_object_read_failure(
    monkeypatch,
    tmp_path,
):
    created_paths = _capture_named_tempfiles(monkeypatch, tmp_path)
    unlink_calls = []
    original_unlink = package_service.os.unlink

    def flaky_unlink(path):
        unlink_calls.append(path)
        if len(unlink_calls) == 1:
            raise OSError("unlink failed")
        original_unlink(path)

    class ObjectStore:
        async def get_info(self, key):
            return SimpleNamespace(description="sidecar.tar.gz")

        async def get(self, key, writeinto):
            raise RuntimeError("object read interrupted")

    class JetStreamService:
        def __init__(self):
            self.object_store = ObjectStore()

        async def connect(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(package_service.os, "unlink", flaky_unlink)
    monkeypatch.setattr("apps.rpc.jetstream.JetStreamService", JetStreamService)

    with pytest.raises(RuntimeError, match="object read interrupted"):
        PackageService.download_file_streaming(_package())

    assert len(created_paths) == 1
    assert unlink_calls == [created_paths[0], created_paths[0]]
    assert not os.path.exists(created_paths[0])


def test_streaming_download_does_not_overwrite_tempfile_owner_during_fallback(
    monkeypatch,
    tmp_path,
):
    created_paths = _capture_named_tempfiles(monkeypatch, tmp_path)
    unlink_calls = []
    original_unlink = package_service.os.unlink

    def flaky_unlink(path):
        unlink_calls.append(path)
        if len(unlink_calls) == 1:
            raise OSError("unlink failed")
        original_unlink(path)

    class ObjectStore:
        get_count = 0

        async def get_info(self, key):
            return SimpleNamespace(description="sidecar.tar.gz")

        async def get(self, key, writeinto):
            self.get_count += 1
            if self.get_count == 1:
                raise ObjectNotFoundError
            writeinto.write(b"legacy payload")

    class JetStreamService:
        def __init__(self):
            self.object_store = ObjectStore()

        async def connect(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(package_service.os, "unlink", flaky_unlink)
    monkeypatch.setattr("apps.rpc.jetstream.JetStreamService", JetStreamService)

    with pytest.raises(ObjectNotFoundError):
        PackageService.download_file_streaming(_package())

    assert len(created_paths) == 1
    assert unlink_calls == [created_paths[0], created_paths[0]]
    assert not os.path.exists(created_paths[0])


def test_streaming_download_removes_tempfile_when_connection_close_is_cancelled(
    monkeypatch,
    tmp_path,
):
    created_paths = _capture_named_tempfiles(monkeypatch, tmp_path)

    class ObjectStore:
        async def get_info(self, key):
            return SimpleNamespace(description="sidecar.tar.gz")

        async def get(self, key, writeinto):
            writeinto.write(b"payload")

    class CancelledClosingJetStreamService:
        def __init__(self):
            self.object_store = ObjectStore()

        async def connect(self):
            return None

        async def close(self):
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "apps.rpc.jetstream.JetStreamService",
        CancelledClosingJetStreamService,
    )

    with pytest.raises(asyncio.CancelledError):
        PackageService.download_file_streaming(_package())

    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])


def test_tempfile_cleanup_preserves_read_error_and_retries_unlink(monkeypatch):
    class FailingFile:
        name = "/tmp/issue-4648-retry"

        def read(self, chunk_size):
            raise RuntimeError("read failed")

        def close(self):
            raise OSError("close failed")

    unlink_calls = []

    def unlink(path):
        unlink_calls.append(path)
        if len(unlink_calls) == 1:
            raise OSError("unlink failed")

    monkeypatch.setattr(package_service.os, "unlink", unlink)
    iterator = package_service._TemporaryFileChunkIterator(FailingFile())

    with pytest.raises(RuntimeError, match="read failed"):
        next(iterator)

    assert iterator.file is not None
    iterator.close()
    assert iterator.file is None
    assert unlink_calls == [FailingFile.name, FailingFile.name]


@pytest.mark.parametrize("consumption", ["none", "partial", "exhausted"])
@pytest.mark.django_db
def test_response_close_or_exhaustion_removes_tempfile(
    monkeypatch,
    tmp_path,
    consumption,
):
    created_paths = _capture_named_tempfiles(monkeypatch, tmp_path)

    class ObjectStore:
        async def get_info(self, key):
            return SimpleNamespace(description="sidecar.tar.gz")

        async def get(self, key, writeinto):
            writeinto.write(b"payload")

    class JetStreamService:
        def __init__(self):
            self.object_store = ObjectStore()

        async def connect(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(
        "apps.rpc.jetstream.JetStreamService",
        JetStreamService,
    )

    stream, filename = PackageService.download_file_streaming(_package())
    assert filename == "sidecar.tar.gz"
    assert os.path.exists(created_paths[0])

    response = StreamingHttpResponse(stream)
    if consumption == "partial":
        assert next(iter(response.streaming_content)) == b"payload"
    elif consumption == "exhausted":
        assert b"".join(response.streaming_content) == b"payload"
    response.close()

    assert not os.path.exists(created_paths[0])
