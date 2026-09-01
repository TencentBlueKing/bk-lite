"""PackageService 路径解析 / 流式下载契约。

仅 mock JetStream / S3 异步边界。钉死候选路径去重、404 回退与流式分块。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.js.errors import ObjectNotFoundError

from apps.node_mgmt.services.package import PackageService

pytestmark = pytest.mark.django_db


def _pkg(**over):
    data = dict(cpu_architecture="x86_64", os="linux", object="telegraf", version="1.0.0", name="t.tar.gz")
    data.update(over)
    return SimpleNamespace(**data)


# --------------------------------------------------------------------------
# build_candidate_file_paths 去重
# --------------------------------------------------------------------------


def test_candidate_paths_dedup_when_primary_equals_legacy():
    obj = _pkg()
    with (
        patch.object(PackageService, "build_file_path", return_value="linux/telegraf/1.0.0/t.tar.gz"),
        patch.object(PackageService, "build_legacy_file_path", return_value="linux/telegraf/1.0.0/t.tar.gz"),
    ):
        assert PackageService.build_candidate_file_paths(obj) == ["linux/telegraf/1.0.0/t.tar.gz"]


# --------------------------------------------------------------------------
# resolve_existing_file_path
# --------------------------------------------------------------------------


class _FakeJetStream:
    def __init__(self, existing=None, raise_on=None):
        self.existing = set(existing or [])
        self.raise_on = raise_on
        self.closed = False
        self.object_store = self

    async def connect(self):
        return None

    async def close(self):
        self.closed = True

    async def get_info(self, path):
        if self.raise_on and path == self.raise_on:
            raise RuntimeError("js down")
        if path in self.existing:
            return SimpleNamespace(description="ok")
        raise ObjectNotFoundError()


def test_resolve_existing_file_path_returns_first_hit():
    obj = _pkg()
    js = _FakeJetStream(existing={PackageService.build_file_path(obj)})
    with patch("apps.rpc.jetstream.JetStreamService", return_value=js):
        assert PackageService.resolve_existing_file_path(obj) == PackageService.build_file_path(obj)
    assert js.closed is True


def test_resolve_existing_file_path_falls_back_to_legacy():
    obj = _pkg()
    js = _FakeJetStream(existing={PackageService.build_legacy_file_path(obj)})
    with patch("apps.rpc.jetstream.JetStreamService", return_value=js):
        assert PackageService.resolve_existing_file_path(obj) == PackageService.build_legacy_file_path(obj)


def test_resolve_existing_file_path_all_missing_raises():
    obj = _pkg()
    js = _FakeJetStream(existing=set())
    with patch("apps.rpc.jetstream.JetStreamService", return_value=js):
        with pytest.raises(ObjectNotFoundError):
            PackageService.resolve_existing_file_path(obj)


def test_resolve_existing_file_path_empty_candidates_raises():
    obj = _pkg()
    js = _FakeJetStream(existing=set())
    with (
        patch.object(PackageService, "build_candidate_file_paths", return_value=[]),
        patch("apps.rpc.jetstream.JetStreamService", return_value=js),
    ):
        with pytest.raises(ObjectNotFoundError):
            PackageService.resolve_existing_file_path(obj)


# --------------------------------------------------------------------------
# _download_file_async 空候选
# --------------------------------------------------------------------------


def test_download_file_empty_candidates_raises():
    obj = _pkg()
    with patch.object(PackageService, "build_candidate_file_paths", return_value=[]):
        with pytest.raises(ObjectNotFoundError):
            PackageService.download_file(obj)


# --------------------------------------------------------------------------
# stream_download_file
# --------------------------------------------------------------------------


def test_stream_download_file_yields_chunks_from_first_hit():
    obj = _pkg()

    async def fake_stream(path):
        assert path == PackageService.build_file_path(obj)
        yield b"abc", "t.tar.gz", 3
        yield b"def", "t.tar.gz", 3

    async def collect():
        items = []
        async for item in PackageService.stream_download_file(obj):
            items.append(item)
        return items

    with patch("apps.node_mgmt.services.package.stream_download_file_by_s3", fake_stream):
        items = asyncio.run(collect())
    assert items == [(b"abc", "t.tar.gz", 3), (b"def", "t.tar.gz", 3)]


def test_stream_download_file_falls_back_then_raises():
    obj = _pkg()
    seen = []

    async def fake_stream(path):
        seen.append(path)
        raise ObjectNotFoundError()
        yield  # make it an async generator  # noqa: B901

    async def collect():
        async for _ in PackageService.stream_download_file(obj):
            pass

    with patch("apps.node_mgmt.services.package.stream_download_file_by_s3", fake_stream):
        with pytest.raises(ObjectNotFoundError):
            asyncio.run(collect())
    assert seen == PackageService.build_candidate_file_paths(obj)


def test_stream_download_file_empty_candidates_raises():
    async def collect():
        async for _ in PackageService.stream_download_file(_pkg()):
            pass

    with patch.object(PackageService, "build_candidate_file_paths", return_value=[]):
        with pytest.raises(ObjectNotFoundError):
            asyncio.run(collect())


# --------------------------------------------------------------------------
# download_file_streaming
# --------------------------------------------------------------------------


def test_download_file_streaming_reads_tempfile_and_unlinks(tmp_path):
    obj = _pkg()
    primary = PackageService.build_file_path(obj)
    tmp = tmp_path / "pkg.bin"
    tmp.write_bytes(b"hello-world")

    class Store:
        async def get_info(self, path):
            if path != primary:
                raise ObjectNotFoundError()
            return SimpleNamespace(description="display-name.bin")

        async def get(self, path, writeinto=None):
            writeinto.write(b"hello-world")

    js = SimpleNamespace(object_store=Store(), closed=False)

    async def connect():
        return None

    async def close():
        js.closed = True

    js.connect = connect
    js.close = close

    with (
        patch("apps.rpc.jetstream.JetStreamService", return_value=js),
        patch("tempfile.NamedTemporaryFile", return_value=open(tmp, "w+b")),
    ):
        gen, filename = PackageService.download_file_streaming(obj)

    assert filename == "display-name.bin"
    assert b"".join(gen) == b"hello-world"
    assert not tmp.exists()
    assert js.closed is True


def test_download_file_streaming_all_missing_raises():
    obj = _pkg()

    class Store:
        async def get_info(self, path):
            raise ObjectNotFoundError()

        async def get(self, path, writeinto=None):
            raise ObjectNotFoundError()

    js = SimpleNamespace(object_store=Store())
    js.connect = AsyncMock()
    js.close = AsyncMock()
    with patch("apps.rpc.jetstream.JetStreamService", return_value=js):
        with pytest.raises(ObjectNotFoundError):
            PackageService.download_file_streaming(obj)


def test_download_file_streaming_empty_candidates_raises():
    js = SimpleNamespace(object_store=MagicMock())
    js.connect = AsyncMock()
    js.close = AsyncMock()
    with (
        patch.object(PackageService, "build_candidate_file_paths", return_value=[]),
        patch("apps.rpc.jetstream.JetStreamService", return_value=js),
    ):
        with pytest.raises(ObjectNotFoundError):
            PackageService.download_file_streaming(_pkg())
