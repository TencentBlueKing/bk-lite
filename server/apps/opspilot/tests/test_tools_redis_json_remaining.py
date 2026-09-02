"""Redis JSON 工具：写入/读取/删除/数组追加成功与 unsupported_feature。"""
from unittest.mock import patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import json as rjson

pytestmark = pytest.mark.unit
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


class _JsonCmd:
    def __init__(self, **returns):
        self._returns = returns

    def set(self, *a, **k):
        val = self._returns.get("set")
        if isinstance(val, Exception):
            raise val
        return True

    def get(self, *a, **k):
        val = self._returns.get("get", {"a": 1})
        if isinstance(val, Exception):
            raise val
        return val

    def delete(self, *a, **k):
        val = self._returns.get("delete", 1)
        if isinstance(val, Exception):
            raise val
        return val

    def arrappend(self, *a, **k):
        val = self._returns.get("arrappend", 3)
        if isinstance(val, Exception):
            raise val
        return val

    def objkeys(self, *a, **k):
        val = self._returns.get("objkeys", ["a"])
        if isinstance(val, Exception):
            raise val
        return val


class FakeRedis:
    def __init__(self, json_cmd, expire_result=True, expire_error=None):
        self._json_cmd = json_cmd
        self._expire_result = expire_result
        self._expire_error = expire_error

    def json(self):
        return self._json_cmd

    def expire(self, *a, **k):
        if self._expire_error:
            raise self._expire_error
        return self._expire_result


def _patch(fake):
    return patch.object(rjson, "get_redis_connection_from_item", return_value=fake)


def test_redis_json_set_parses_json_and_raw_string():
    fake = FakeRedis(_JsonCmd())
    with _patch(fake):
        ok = rjson.redis_json_set.invoke({"name": "doc", "path": "$", "value": '{"a": 1}', "expire_seconds": 10, "config": CONFIG})
        raw = rjson.redis_json_set.invoke({"name": "doc", "path": "$.x", "value": "not-json", "config": CONFIG})
    assert ok == {"success": True, "data": {"name": "doc", "path": "$", "expire_seconds": 10}}
    assert raw["success"] is True


def test_redis_json_get_del_arrappend_objkeys_success():
    fake = FakeRedis(_JsonCmd(get={"a": 1}, delete=1, arrappend=4, objkeys=["a", "b"]))
    with _patch(fake):
        got = rjson.redis_json_get.invoke({"name": "doc", "path": "$", "config": CONFIG})
        deleted = rjson.redis_json_del.invoke({"name": "doc", "path": "$.a", "config": CONFIG})
        appended = rjson.redis_json_arrappend.invoke({"name": "doc", "path": "$.arr", "values": [1, 2], "config": CONFIG})
        keys = rjson.redis_json_objkeys.invoke({"name": "doc", "config": CONFIG})
    assert got == {"success": True, "data": {"a": 1}}
    assert deleted["data"]["deleted"] == 1
    assert appended["success"] is True
    assert keys["data"] == ["a", "b"]


def test_redis_json_commands_wrap_unsupported_feature():
    err = RedisError("no json")
    fake = FakeRedis(_JsonCmd(set=err, get=err, delete=err, arrappend=err, objkeys=err))
    with _patch(fake):
        for result in (
            rjson.redis_json_set.invoke({"name": "doc", "path": "$", "value": "{}", "config": CONFIG}),
            rjson.redis_json_get.invoke({"name": "doc", "config": CONFIG}),
            rjson.redis_json_del.invoke({"name": "doc", "config": CONFIG}),
            rjson.redis_json_arrappend.invoke({"name": "doc", "path": "$.a", "values": [1], "config": CONFIG}),
            rjson.redis_json_objkeys.invoke({"name": "doc", "config": CONFIG}),
        ):
            assert result == {"success": False, "error": "no json", "error_type": "unsupported_feature"}
