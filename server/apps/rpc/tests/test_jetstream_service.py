"""rpc.jetstream.JetStreamService 单元测试。

JetStreamService 封装 NATS object_store。本测试只 mock object_store 这一外部边界，
断言 put/get/delete/list_objects/get_streaming 的解析、组装与异常分支。
不连接真实 NATS。
"""
import pydantic.root_model  # noqa

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.rpc.jetstream import JetStreamService

pytestmark = pytest.mark.unit


@pytest.fixture
def svc():
    s = JetStreamService(bucket_name="mybucket")
    s.object_store = MagicMock()
    return s


def test_init_默认bucket():
    from config.components.nats import NATS_NAMESPACE
    s = JetStreamService()
    assert s.bucket_name == NATS_NAMESPACE
    assert s.nc is None
    assert s.js is None
    assert s.object_store is None


async def test_put_带description构造meta(svc):
    info = SimpleNamespace(name="k", size=10)
    svc.object_store.put = AsyncMock(return_value=info)
    out = await svc.put("k", b"data", description="desc")
    assert out is info
    # 校验 meta.description 被传入
    _, kwargs = svc.object_store.put.call_args
    assert kwargs["meta"].description == "desc"


async def test_put_无description传meta为None(svc):
    info = SimpleNamespace(name="k", size=3)
    svc.object_store.put = AsyncMock(return_value=info)
    await svc.put("k", b"abc")
    assert svc.object_store.put.call_args.kwargs["meta"] is None


async def test_get_返回data与description(svc):
    result = SimpleNamespace(
        data=b"payload",
        info=SimpleNamespace(name="k", size=7, description="my-desc"),
    )
    svc.object_store.get = AsyncMock(return_value=result)
    data, desc = await svc.get("k")
    assert data == b"payload"
    assert desc == "my-desc"


async def test_delete_调用object_store_delete(svc):
    svc.object_store.delete = AsyncMock()
    await svc.delete("k")
    svc.object_store.delete.assert_awaited_once_with("k")


async def test_list_objects_返回条目(svc):
    entries = [SimpleNamespace(name="a"), SimpleNamespace(name="b")]
    svc.object_store.list = AsyncMock(return_value=entries)
    out = await svc.list_objects()
    assert out == entries


async def test_list_objects_异常时返回空列表(svc):
    svc.object_store.list = AsyncMock(side_effect=RuntimeError("empty"))
    out = await svc.list_objects()
    assert out == []


async def test_close_关闭连接(svc):
    svc.nc = MagicMock()
    svc.nc.close = AsyncMock()
    await svc.close()
    svc.nc.close.assert_awaited_once()


async def test_get_streaming_分块产出(svc):
    info = SimpleNamespace(description="file.bin", size=5)
    svc.object_store.get_info = AsyncMock(return_value=info)

    # get(key, writeinto=tmp) 把内容写入临时文件
    async def fake_get(key, writeinto=None):
        writeinto.write(b"hello")

    svc.object_store.get = AsyncMock(side_effect=fake_get)

    chunks = []
    async for chunk, filename, total in svc.get_streaming("k", chunk_size=2):
        chunks.append((chunk, filename, total))

    # chunk_size=2，hello -> b"he", b"ll", b"o"
    assert [c[0] for c in chunks] == [b"he", b"ll", b"o"]
    assert all(c[1] == "file.bin" for c in chunks)
    assert all(c[2] == 5 for c in chunks)


async def test_get_streaming_description为空用key末段做文件名(svc):
    info = SimpleNamespace(description=None, size=0)
    svc.object_store.get_info = AsyncMock(return_value=info)

    async def fake_get(key, writeinto=None):
        writeinto.write(b"x")

    svc.object_store.get = AsyncMock(side_effect=fake_get)

    names = []
    async for _chunk, filename, _total in svc.get_streaming("path/to/myfile.dat", chunk_size=10):
        names.append(filename)
    assert names == ["myfile.dat"]
