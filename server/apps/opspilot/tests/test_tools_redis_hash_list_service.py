"""Redis hash / list @tool 单元测试 (redis/hash, redis/list)。

patch 连接获取函数返回 mock client(driver 边界),断言结构化响应、入参转发、
过期设置与 RedisError 脱敏包装。不连接真实 Redis。
"""

from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import hash as rh
from apps.opspilot.metis.llm.tools.redis import list as rl

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


@pytest.fixture
def hash_client():
    client = MagicMock()
    with patch.object(rh, "get_redis_connection_from_item", return_value=client), patch.object(
        rh, "get_binary_redis_connection_from_item", return_value=client
    ):
        yield client


@pytest.fixture
def list_client():
    client = MagicMock()
    with patch.object(rl, "get_redis_connection_from_item", return_value=client):
        yield client


class TestRedisHash:
    def test_hset_basic(self, hash_client):
        out = rh.redis_hset.invoke({"name": "h", "key": "f", "value": "v", "config": CONFIG})
        assert out["success"] is True
        assert out["data"] == {"name": "h", "key": "f", "expire_seconds": None}
        hash_client.hset.assert_called_once_with("h", "f", "v")
        hash_client.expire.assert_not_called()

    def test_hset_with_expire(self, hash_client):
        rh.redis_hset.invoke({"name": "h", "key": "f", "value": "v", "expire_seconds": 30, "config": CONFIG})
        hash_client.expire.assert_called_once_with("h", 30)

    def test_hgetall(self, hash_client):
        hash_client.hgetall.return_value = {"a": "1", "b": "2"}
        out = rh.redis_hgetall.invoke({"name": "h", "config": CONFIG})
        assert out["data"] == {"a": "1", "b": "2"}
        assert out["name"] == "h"

    def test_hget(self, hash_client):
        hash_client.hget.return_value = "val"
        out = rh.redis_hget.invoke({"name": "h", "key": "f", "config": CONFIG})
        assert out["data"] == {"name": "h", "key": "f", "value": "val"}

    def test_hdel_returns_count(self, hash_client):
        hash_client.hdel.return_value = 1
        out = rh.redis_hdel.invoke({"name": "h", "key": "f", "config": CONFIG})
        assert out["data"]["deleted"] == 1

    def test_error_wrapped(self, hash_client):
        hash_client.hset.side_effect = RedisError("down")
        out = rh.redis_hset.invoke({"name": "h", "key": "f", "value": "v", "config": CONFIG})
        assert out["success"] is False
        assert out["error"] == "down"


class TestRedisList:
    def test_lpush(self, list_client):
        list_client.lpush.return_value = 3
        out = rl.redis_lpush.invoke({"key": "l", "value": "x", "config": CONFIG})
        assert out["data"]["length"] == 3
        assert out["key"] == "l"

    def test_rpush(self, list_client):
        list_client.rpush.return_value = 5
        out = rl.redis_rpush.invoke({"key": "l", "value": "x", "config": CONFIG})
        assert out["data"]["length"] == 5

    def test_lrange_forwards_range(self, list_client):
        list_client.lrange.return_value = ["a", "b"]
        out = rl.redis_lrange.invoke({"key": "l", "start": 0, "end": 5, "config": CONFIG})
        assert out["data"] == ["a", "b"]
        list_client.lrange.assert_called_once_with("l", 0, 5)

    def test_lrange_error_wrapped(self, list_client):
        list_client.lrange.side_effect = RedisError("boom")
        out = rl.redis_lrange.invoke({"key": "l", "config": CONFIG})
        assert out["success"] is False
        assert out["error_type"] == "redis_error"
