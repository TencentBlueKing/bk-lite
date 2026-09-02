"""Redis stream / set 工具：成功契约与 RedisError 包装。"""
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import set as rset
from apps.opspilot.metis.llm.tools.redis import stream as rstream

pytestmark = pytest.mark.unit
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


class FakeRedis:
    def __init__(self, **returns):
        self._returns = returns
        self.connection_pool = MagicMock()
        self.connection_pool.connection_kwargs = {"host": "h", "port": 6379, "db": 0}

    def __getattr__(self, name):
        def _method(*args, **kwargs):
            val = self._returns.get(name)
            if isinstance(val, Exception):
                raise val
            return val

        return _method


def _patch(module, fake):
    return patch.object(module, "get_redis_connection_from_item", return_value=fake)


def test_redis_stream_commands_success_and_expire():
    fake = FakeRedis(
        xadd="1-0",
        expire=True,
        xread=[["s", [["1-0", {"a": "1"}]]]],
        xrange=[["1-0", {"a": "1"}]],
        xrevrange=[["2-0", {"b": "2"}]],
        xdel=1,
        xgroup_create=True,
        xreadgroup=[["s", []]],
        xack=1,
    )
    with _patch(rstream, fake):
        added = rstream.redis_xadd.invoke({"key": "s", "fields": {"a": "1"}, "expiration": 30, "config": CONFIG})
        read = rstream.redis_xread.invoke({"streams": {"s": "0-0"}, "config": CONFIG})
        rng = rstream.redis_xrange.invoke({"key": "s", "config": CONFIG})
        rev = rstream.redis_xrevrange.invoke({"key": "s", "config": CONFIG})
        deleted = rstream.redis_xdel.invoke({"key": "s", "entry_id": "1-0", "config": CONFIG})
        group = rstream.redis_xgroup_create.invoke({"key": "s", "group_name": "g", "config": CONFIG})
        grouped = rstream.redis_xreadgroup.invoke({"group_name": "g", "consumer_name": "c", "streams": {"s": ">"}, "config": CONFIG})
        acked = rstream.redis_xack.invoke({"key": "s", "group_name": "g", "entry_ids": ["1-0"], "config": CONFIG})
    assert added == {"success": True, "data": {"key": "s", "entry_id": "1-0", "expiration": 30}}
    assert read["success"] is True
    assert rng["key"] == "s"
    assert rev["success"] is True
    assert deleted == {"success": True, "data": {"key": "s", "deleted": 1, "entry_id": "1-0"}}
    assert group["data"]["created"] is True
    assert grouped["success"] is True
    assert acked["data"]["acked"] == 1


def test_redis_stream_commands_wrap_redis_error():
    fake = FakeRedis(
        xadd=RedisError("stream down"),
        xread=RedisError("stream down"),
        xrange=RedisError("stream down"),
        xrevrange=RedisError("stream down"),
        xdel=RedisError("stream down"),
        xgroup_create=RedisError("stream down"),
        xreadgroup=RedisError("stream down"),
        xack=RedisError("stream down"),
    )
    with _patch(rstream, fake):
        for result in (
            rstream.redis_xadd.invoke({"key": "s", "fields": {"a": "1"}, "config": CONFIG}),
            rstream.redis_xread.invoke({"streams": {"s": "0-0"}, "config": CONFIG}),
            rstream.redis_xrange.invoke({"key": "s", "config": CONFIG}),
            rstream.redis_xrevrange.invoke({"key": "s", "config": CONFIG}),
            rstream.redis_xdel.invoke({"key": "s", "entry_id": "1-0", "config": CONFIG}),
            rstream.redis_xgroup_create.invoke({"key": "s", "group_name": "g", "config": CONFIG}),
            rstream.redis_xreadgroup.invoke({"group_name": "g", "consumer_name": "c", "streams": {"s": ">"}, "config": CONFIG}),
            rstream.redis_xack.invoke({"key": "s", "group_name": "g", "entry_ids": ["1-0"], "config": CONFIG}),
        ):
            assert result == {"success": False, "error": "stream down", "error_type": "redis_error"}


def test_redis_set_commands_success():
    fake = FakeRedis(
        sadd=1,
        smembers={"a", "b"},
        srem=1,
        sismember=True,
        scard=2,
        sinter={"a"},
        sunion={"a", "b"},
        sdiff={"b"},
    )
    with _patch(rset, fake):
        assert rset.redis_sadd.invoke({"key": "s", "member": "a", "config": CONFIG})["data"]["added"] == 1
        members = rset.redis_smembers.invoke({"key": "s", "config": CONFIG})
        assert members["success"] is True
        assert sorted(members["data"]) == ["a", "b"]
        assert rset.redis_srem.invoke({"key": "s", "member": "a", "config": CONFIG})["data"]["removed"] == 1
        assert rset.redis_sismember.invoke({"key": "s", "member": "a", "config": CONFIG})["data"]["is_member"] is True
        assert rset.redis_scard.invoke({"key": "s", "config": CONFIG})["data"]["count"] == 2
        inter = rset.redis_sinter.invoke({"keys": ["s1", "s2"], "config": CONFIG})
        assert inter["data"] == ["a"]
        union = rset.redis_sunion.invoke({"keys": ["s1", "s2"], "config": CONFIG})
        assert sorted(union["data"]) == ["a", "b"]
        diff = rset.redis_sdiff.invoke({"keys": ["s1", "s2"], "config": CONFIG})
        assert diff["data"] == ["b"]


def test_redis_set_commands_wrap_redis_error():
    fake = FakeRedis(
        sadd=RedisError("set down"),
        smembers=RedisError("set down"),
        srem=RedisError("set down"),
        sismember=RedisError("set down"),
        scard=RedisError("set down"),
        sinter=RedisError("set down"),
        sunion=RedisError("set down"),
        sdiff=RedisError("set down"),
    )
    with _patch(rset, fake):
        for result in (
            rset.redis_sadd.invoke({"key": "s", "member": "a", "config": CONFIG}),
            rset.redis_smembers.invoke({"key": "s", "config": CONFIG}),
            rset.redis_srem.invoke({"key": "s", "member": "a", "config": CONFIG}),
            rset.redis_sismember.invoke({"key": "s", "member": "a", "config": CONFIG}),
            rset.redis_scard.invoke({"key": "s", "config": CONFIG}),
            rset.redis_sinter.invoke({"keys": ["s1"], "config": CONFIG}),
            rset.redis_sunion.invoke({"keys": ["s1"], "config": CONFIG}),
            rset.redis_sdiff.invoke({"keys": ["s1"], "config": CONFIG}),
        ):
            assert result == {"success": False, "error": "set down", "error_type": "redis_error"}
