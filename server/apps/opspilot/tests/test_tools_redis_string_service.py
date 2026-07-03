"""Redis string @tool 单元测试 (redis/string)。

通过 patch redis 连接获取函数返回 mock client(driver 边界),断言工具产出的
结构化成功/错误响应、值编码与二进制规整、过期参数转发。不连接真实 Redis。
"""

from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import string as rs

# 单实例 legacy 配置,使 build_redis_normalized_from_runnable 产生单个 item
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


@pytest.fixture
def fake_client():
    client = MagicMock()
    with patch.object(rs, "get_redis_connection_from_item", return_value=client), patch.object(
        rs, "get_binary_redis_connection_from_item", return_value=client
    ):
        yield client


class TestRedisSet:
    def test_plain_set(self, fake_client):
        out = rs.redis_set.invoke({"key": "k", "value": "v", "config": CONFIG})
        assert out["success"] is True
        assert out["data"] == {"key": "k", "expiration": None}
        fake_client.set.assert_called_once_with("k", "v")

    def test_setex_with_expiration(self, fake_client):
        out = rs.redis_set.invoke({"key": "k", "value": "v", "expiration": 60, "config": CONFIG})
        assert out["data"]["expiration"] == 60
        fake_client.setex.assert_called_once_with("k", 60, "v")

    def test_dict_value_json_encoded(self, fake_client):
        rs.redis_set.invoke({"key": "k", "value": {"a": 1}, "config": CONFIG})
        args = fake_client.set.call_args.args
        assert args[1] == '{"a": 1}'

    def test_redis_error_wrapped(self, fake_client):
        fake_client.set.side_effect = RedisError("conn lost")
        out = rs.redis_set.invoke({"key": "k", "value": "v", "config": CONFIG})
        assert out["success"] is False
        assert out["error"] == "conn lost"
        assert out["error_type"] == "redis_error"


class TestRedisGet:
    def test_utf8_value(self, fake_client):
        fake_client.get.return_value = b"hello"
        out = rs.redis_get.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["value"] == "hello"
        assert out["data"]["encoding"] == "utf-8"
        assert out["data"]["is_binary"] is False
        assert out["data"]["byte_length"] == 5

    def test_binary_value_hex(self, fake_client):
        fake_client.get.return_value = b"\xff\xfe"
        out = rs.redis_get.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["value"] == "fffe"
        assert out["data"]["encoding"] == "hex"
        assert out["data"]["is_binary"] is True

    def test_missing_key_none(self, fake_client):
        fake_client.get.return_value = None
        out = rs.redis_get.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["value"] is None
        assert out["data"]["byte_length"] == 0


class TestRedisMget:
    def test_multiple_values(self, fake_client):
        fake_client.mget.return_value = [b"a", None]
        out = rs.redis_mget.invoke({"keys": ["k1", "k2"], "config": CONFIG})
        assert out["data"]["keys"] == ["k1", "k2"]
        assert out["data"]["values"][0]["value"] == "a"
        assert out["data"]["values"][1]["value"] is None


class TestRedisAppendStrlen:
    def test_append_returns_length(self, fake_client):
        fake_client.append.return_value = 8
        out = rs.redis_append.invoke({"key": "k", "value": "xyz", "config": CONFIG})
        assert out["data"] == {"key": "k", "length": 8}
        fake_client.append.assert_called_once_with("k", "xyz")

    def test_strlen(self, fake_client):
        fake_client.strlen.return_value = 3
        out = rs.redis_strlen.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["length"] == 3


class TestRedisGetdel:
    def test_returns_value_and_deletes(self, fake_client):
        fake_client.getdel.return_value = b"bye"
        out = rs.redis_getdel.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["value"] == "bye"
        fake_client.getdel.assert_called_once_with("k")


class TestNormalizeStringValueHelper:
    def test_str_value(self):
        out = rs._normalize_string_value("abc")
        assert out["value"] == "abc"
        assert out["byte_length"] == 3

    def test_encode_value_passthrough(self):
        assert rs._encode_value("x") == "x"
        assert rs._encode_value([1, 2]) == "[1, 2]"
