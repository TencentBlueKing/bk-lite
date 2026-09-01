"""Redis server_management 剩余：错误包装、set/zset/json 分派、flushdb 失败。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import hash as rh
from apps.opspilot.metis.llm.tools.redis import json as rjson
from apps.opspilot.metis.llm.tools.redis import server_management as sm
from apps.opspilot.metis.llm.tools.redis import set as rset
from apps.opspilot.metis.llm.tools.redis import sorted_set as rzset

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


def test_redis_server_commands_wrap_connection_errors():
    fake = FakeRedis(
        ping=RedisError("down"),
        dbsize=RedisError("down"),
        info=RedisError("down"),
        client_list=RedisError("down"),
        scan=RedisError("down"),
        type=RedisError("down"),
        exists=RedisError("down"),
        expire=RedisError("down"),
        ttl=RedisError("down"),
        delete=RedisError("down"),
        rename=RedisError("down"),
        flushdb=RedisError("down"),
    )
    with _patch(sm, fake):
        assert sm.redis_ping.invoke({"config": CONFIG}) == {
            "success": False,
            "error": "down",
            "error_type": "connection_error",
        }
        assert sm.redis_dbsize.invoke({"config": CONFIG})["error_type"] == "redis_error"
        assert sm.redis_info.invoke({"section": "memory", "config": CONFIG})["success"] is False
        assert sm.redis_client_list.invoke({"config": CONFIG})["success"] is False
        assert sm.redis_scan_keys.invoke({"config": CONFIG})["success"] is False
        assert sm.redis_key_type.invoke({"key": "k", "config": CONFIG})["success"] is False
        assert sm.redis_exists.invoke({"key": "k", "config": CONFIG})["success"] is False
        assert sm.redis_expire.invoke({"key": "k", "seconds": 1, "config": CONFIG})["success"] is False
        assert sm.redis_ttl.invoke({"key": "k", "config": CONFIG})["success"] is False
        assert sm.redis_delete.invoke({"key": "k", "config": CONFIG})["success"] is False
        assert sm.redis_rename.invoke({"old_key": "a", "new_key": "b", "config": CONFIG})["success"] is False
        flush = sm.redis_flushdb.invoke({"confirm": True, "config": CONFIG})
        assert flush == {"success": False, "error": "down", "error_type": "redis_error"}


def test_redis_get_key_value_set_zset_json_and_summary():
    sm_client = FakeRedis(exists=1, type="set", ttl=9)
    set_client = FakeRedis(scard=3, smembers=["a", "b", "c"])
    with _patch(sm, sm_client), _patch(rset, set_client):
        out = sm.redis_get_key_value.invoke({"key": "s", "max_items": 2, "config": CONFIG})
    assert out == {
        "success": True,
        "data": {
            "key": "s",
            "exists": True,
            "type": "set",
            "ttl": 9,
            "count": 3,
            "truncated": True,
            "value": ["a", "b"],
        },
    }

    sm_client = FakeRedis(exists=1, type="zset", ttl=4)
    z_client = FakeRedis(zcard=1, zrange=[{"member": "m", "score": 1.0}])
    with _patch(sm, sm_client), _patch(rzset, z_client):
        zout = sm.redis_get_key_value.invoke({"key": "z", "config": CONFIG})
    assert zout["data"]["type"] == "zset"
    assert zout["data"]["count"] == 1
    assert zout["data"]["value"] == [{"member": "m", "score": 1.0}]

    sm_client = FakeRedis(exists=1, type="json", ttl=-1)
    json_client = FakeRedis()
    json_client.json = MagicMock(return_value=SimpleNamespace(get=lambda *a, **k: {"n": 1}))
    with _patch(sm, sm_client), _patch(rjson, json_client):
        jout = sm.redis_get_key_value.invoke({"key": "j", "config": CONFIG})
    assert jout["data"]["type"] == "json"
    assert jout["data"]["value"] == {"n": 1}

    sm_client = FakeRedis(exists=1, type="hash", ttl=1)
    hash_client = FakeRedis(hgetall={"f": "1"})

    with _patch(sm, sm_client), _patch(rh, hash_client):
        summary = sm.redis_get_key_summary.invoke({"key": "h", "config": CONFIG})
    assert summary["data"]["count"] == 1
    assert summary["data"]["preview"] == {"f": "1"}
    assert summary["data"]["truncated"] is False
