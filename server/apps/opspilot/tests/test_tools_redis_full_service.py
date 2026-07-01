"""Redis @tool 工具集补充测试 (redis/connection|server_management|hash|list|string gaps + utils)。

mock 边界为 get_redis_connection_from_item / get_binary_redis_connection_from_item,返回
FakeRedis(按方法记录调用并返回真实形态值)。连接层通过打桩 redis.Redis/RedisCluster
捕获连接 kwargs。断言工具产出 success/error 响应结构、类型分派、确认护栏、TTL/扫描/
二进制向量还原、连接参数构造、敏感字段不入参契约。不连真实 Redis。
"""

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pydantic.root_model  # noqa
import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import connection as conn  # noqa: E402
from apps.opspilot.metis.llm.tools.redis import hash as rh  # noqa: E402
from apps.opspilot.metis.llm.tools.redis import list as rl  # noqa: E402
from apps.opspilot.metis.llm.tools.redis import server_management as sm  # noqa: E402
from apps.opspilot.metis.llm.tools.redis import string as rs  # noqa: E402
from apps.opspilot.metis.llm.tools.redis import utils as ru  # noqa: E402

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


class FakeRedis:
    """记录调用并返回 canned 值的假 Redis 客户端。"""

    def __init__(self, **returns):
        self._returns = returns
        self.calls = []

    def __getattr__(self, name):
        def _method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            val = self._returns.get(name)
            if isinstance(val, Exception):
                raise val
            return val
        return _method


def _patch(module, fake, binary=False):
    target = "get_binary_redis_connection_from_item" if binary else "get_redis_connection_from_item"
    return patch.object(module, target, return_value=fake)


# ============================ utils ============================
class TestRedisUtils:
    def test_ensure_json_serializable_bytes_utf8_and_hex(self):
        assert ru.ensure_json_serializable(b"hi") == "hi"
        # 非 utf8 -> hex
        assert ru.ensure_json_serializable(b"\xff\xfe") == "fffe"

    def test_ensure_json_serializable_nested(self):
        out = ru.ensure_json_serializable({1: [b"x", (2, 3)], "s": {4}})
        assert out["1"] == ["x", [2, 3]]
        assert out["s"] == [4]

    def test_ensure_json_serializable_fallback_str(self):
        class Foo:
            def __str__(self):
                return "foo"
        assert ru.ensure_json_serializable(Foo()) == "foo"

    def test_safe_json_dumps(self):
        assert json.loads(ru.safe_json_dumps({"a": b"x"})) == {"a": "x"}

    def test_build_responses(self):
        ok = ru.build_success_response({"k": 1}, extra="e")
        assert ok["success"] is True
        assert ok["extra"] == "e"
        err = ru.build_error_response(ValueError("bad"), error_type="t")
        assert err["success"] is False
        assert err["error"] == "bad"
        assert err["error_type"] == "t"

    def test_truncate_sequence(self):
        out = ru.truncate_sequence(list(range(150)), max_items=100)
        assert out["truncated"] is True
        assert out["returned_count"] == 100
        assert out["total_count"] == 150

    def test_truncate_mapping(self):
        data = {str(i): i for i in range(120)}
        out = ru.truncate_mapping(data, max_items=50)
        assert out["truncated"] is True
        assert out["returned_count"] == 50
        assert out["total_count"] == 120

    def test_require_confirm(self):
        assert ru.require_confirm(True, "flushdb") is None
        err = ru.require_confirm(False, "flushdb")
        assert err["error_type"] == "confirmation_required"


# ============================ hash gaps ============================
class TestRedisHashGaps:
    def test_hset_with_expire(self):
        fake = FakeRedis(hset=1, expire=True)
        with _patch(rh, fake):
            out = rh.redis_hset.invoke({"name": "h", "key": "f", "value": "v", "expire_seconds": 60, "config": CONFIG})
        assert out["success"] is True
        assert ("expire", ("h", 60), {}) in fake.calls

    def test_hset_error(self):
        fake = FakeRedis(hset=RedisError("conn lost"))
        with _patch(rh, fake):
            out = rh.redis_hset.invoke({"name": "h", "key": "f", "value": "v", "config": CONFIG})
        assert out["success"] is False
        assert out["error"] == "conn lost"

    def test_hexists(self):
        fake = FakeRedis(hexists=1)
        with _patch(rh, fake):
            out = rh.redis_hexists.invoke({"name": "h", "key": "f", "config": CONFIG})
        assert out["data"]["exists"] is True

    def test_hkeys_hvals_hlen(self):
        fake = FakeRedis(hkeys=["a", "b"], hvals=["1", "2"], hlen=2)
        with _patch(rh, fake):
            assert rh.redis_hkeys.invoke({"name": "h", "config": CONFIG})["data"] == ["a", "b"]
            assert rh.redis_hvals.invoke({"name": "h", "config": CONFIG})["data"] == ["1", "2"]
            assert rh.redis_hlen.invoke({"name": "h", "config": CONFIG})["data"]["length"] == 2

    def test_set_vector_in_hash(self):
        fake = FakeRedis(hset=1)
        with _patch(rh, fake):
            out = rh.redis_set_vector_in_hash.invoke({"name": "h", "vector": [1.0, 2.0, 3.0], "config": CONFIG})
        assert out["data"]["stored"] is True
        # 校验写入的是 float32 二进制
        _, args, _ = [c for c in fake.calls if c[0] == "hset"][0]
        assert args[2] == np.array([1.0, 2.0, 3.0], dtype=np.float32).tobytes()

    def test_get_vector_from_hash_roundtrip(self):
        blob = np.array([1.5, 2.5], dtype=np.float32).tobytes()
        fake = FakeRedis(hget=blob)
        with _patch(rh, fake, binary=True):
            out = rh.redis_get_vector_from_hash.invoke({"name": "h", "config": CONFIG})
        assert out["data"] == [1.5, 2.5]

    def test_get_vector_from_hash_empty(self):
        fake = FakeRedis(hget=None)
        with _patch(rh, fake, binary=True):
            out = rh.redis_get_vector_from_hash.invoke({"name": "h", "config": CONFIG})
        assert out["data"] == []


# ============================ list gaps ============================
class TestRedisListGaps:
    def test_lpop_rpop(self):
        fake = FakeRedis(lpop="a", rpop="z")
        with _patch(rl, fake):
            assert rl.redis_lpop.invoke({"key": "l", "config": CONFIG})["data"]["value"] == "a"
            assert rl.redis_rpop.invoke({"key": "l", "config": CONFIG})["data"]["value"] == "z"

    def test_llen_lindex(self):
        fake = FakeRedis(llen=3, lindex="b")
        with _patch(rl, fake):
            assert rl.redis_llen.invoke({"key": "l", "config": CONFIG})["data"]["length"] == 3
            assert rl.redis_lindex.invoke({"key": "l", "index": 1, "config": CONFIG})["data"]["value"] == "b"

    def test_list_error(self):
        fake = FakeRedis(llen=RedisError("nope"))
        with _patch(rl, fake):
            out = rl.redis_llen.invoke({"key": "l", "config": CONFIG})
        assert out["success"] is False


# ============================ string gaps ============================
class TestRedisStringGaps:
    def test_get_binary_value_hex(self):
        fake = FakeRedis(get=b"\xff\xfe")
        with _patch(rs, fake, binary=True):
            out = rs.redis_get.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["encoding"] == "hex"
        assert out["data"]["is_binary"] is True

    def test_set_with_expiration_uses_setex(self):
        fake = FakeRedis(setex=True)
        with _patch(rs, fake):
            out = rs.redis_set.invoke({"key": "k", "value": "v", "expiration": 30, "config": CONFIG})
        assert out["success"] is True
        assert any(c[0] == "setex" for c in fake.calls)

    def test_set_encodes_dict(self):
        fake = FakeRedis(set=True)
        with _patch(rs, fake):
            rs.redis_set.invoke({"key": "k", "value": {"a": 1}, "config": CONFIG})
        _, args, _ = [c for c in fake.calls if c[0] == "set"][0]
        assert args[1] == json.dumps({"a": 1}, ensure_ascii=False)

    def test_getdel(self):
        fake = FakeRedis(getdel=b"bye")
        with _patch(rs, fake, binary=True):
            out = rs.redis_getdel.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["value"] == "bye"

    def test_string_error(self):
        fake = FakeRedis(strlen=RedisError("x"))
        with _patch(rs, fake):
            out = rs.redis_strlen.invoke({"key": "k", "config": CONFIG})
        assert out["success"] is False


# ============================ server_management ============================
class TestRedisServerManagement:
    def test_ping_and_dbsize(self):
        fake = FakeRedis(ping=True, dbsize=42)
        with _patch(sm, fake):
            assert sm.redis_ping.invoke({"config": CONFIG})["data"]["pong"] is True
            assert sm.redis_dbsize.invoke({"config": CONFIG})["data"]["dbsize"] == 42

    def test_ping_connection_error(self):
        fake = FakeRedis(ping=RedisError("refused"))
        with _patch(sm, fake):
            out = sm.redis_ping.invoke({"config": CONFIG})
        assert out["error_type"] == "connection_error"

    def test_info(self):
        fake = FakeRedis(info={"redis_version": "7.0", "used_memory": 1024})
        with _patch(sm, fake):
            out = sm.redis_info.invoke({"section": "memory", "config": CONFIG})
        assert out["section"] == "memory"
        assert out["data"]["redis_version"] == "7.0"

    def test_client_list(self):
        fake = FakeRedis(client_list=[{"id": "1", "addr": "127.0.0.1:1"}])
        with _patch(sm, fake):
            out = sm.redis_client_list.invoke({"config": CONFIG})
        assert out["data"][0]["id"] == "1"

    def test_scan_keys(self):
        fake = FakeRedis(scan=(0, ["k1", "k2"]))
        with _patch(sm, fake):
            out = sm.redis_scan_keys.invoke({"pattern": "k*", "config": CONFIG})
        assert out["cursor"] == 0
        assert out["data"]["returned_count"] == 2

    def test_key_type_exists(self):
        fake = FakeRedis(type="string", exists=1)
        with _patch(sm, fake):
            assert sm.redis_key_type.invoke({"key": "k", "config": CONFIG})["data"]["type"] == "string"
            assert sm.redis_exists.invoke({"key": "k", "config": CONFIG})["data"]["exists"] is True

    def test_expire_ttl(self):
        fake = FakeRedis(expire=True, ttl=120)
        with _patch(sm, fake):
            assert sm.redis_expire.invoke({"key": "k", "seconds": 120, "config": CONFIG})["data"]["expire_set"] is True
            assert sm.redis_ttl.invoke({"key": "k", "config": CONFIG})["data"]["ttl"] == 120

    def test_delete_rename(self):
        fake = FakeRedis(delete=1, rename=True)
        with _patch(sm, fake):
            assert sm.redis_delete.invoke({"key": "k", "config": CONFIG})["data"]["deleted"] == 1
            out = sm.redis_rename.invoke({"old_key": "a", "new_key": "b", "config": CONFIG})
            assert out["data"]["new_key"] == "b"

    def test_get_key_value_not_exists(self):
        fake = FakeRedis(exists=0)
        with _patch(sm, fake):
            out = sm.redis_get_key_value.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["exists"] is False
        assert out["data"]["type"] == "none"

    def test_get_key_value_string_dispatch(self):
        # exists/type/ttl 走 sm 的 client; redis_get 内部走 string 模块的 binary client
        sm_client = FakeRedis(exists=1, type="string", ttl=100)
        str_client = FakeRedis(get=b"hello")
        with _patch(sm, sm_client), _patch(rs, str_client, binary=True):
            out = sm.redis_get_key_value.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["type"] == "string"
        assert out["data"]["value"] == "hello"
        assert out["data"]["ttl"] == 100

    def test_get_key_value_hash_dispatch(self):
        sm_client = FakeRedis(exists=1, type="hash", ttl=50)
        hash_client = FakeRedis(hgetall={"f1": "v1", "f2": "v2"})
        with _patch(sm, sm_client), _patch(rh, hash_client):
            out = sm.redis_get_key_value.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["type"] == "hash"
        assert out["data"]["count"] == 2
        assert out["data"]["value"] == {"f1": "v1", "f2": "v2"}

    def test_get_key_value_list_dispatch(self):
        sm_client = FakeRedis(exists=1, type="list", ttl=-1)
        list_client = FakeRedis(llen=2, lrange=["a", "b"])
        with _patch(sm, sm_client), _patch(rl, list_client):
            out = sm.redis_get_key_value.invoke({"key": "k", "max_items": 100, "config": CONFIG})
        assert out["data"]["type"] == "list"
        assert out["data"]["count"] == 2
        assert out["data"]["value"] == ["a", "b"]

    def test_get_key_value_unsupported_type(self):
        sm_client = FakeRedis(exists=1, type="stream", ttl=10)
        with _patch(sm, sm_client):
            out = sm.redis_get_key_value.invoke({"key": "k", "config": CONFIG})
        assert "Unsupported key type" in out["data"]["message"]

    def test_get_key_summary_string(self):
        sm_client = FakeRedis(exists=1, type="string", ttl=100)
        str_client = FakeRedis(get=b"hello world")
        with _patch(sm, sm_client), _patch(rs, str_client, binary=True):
            out = sm.redis_get_key_summary.invoke({"key": "k", "preview_limit": 5, "config": CONFIG})
        assert out["data"]["preview"] == "hello"
        assert out["data"]["truncated"] is True

    def test_get_key_summary_not_exists(self):
        sm_client = FakeRedis(exists=0)
        with _patch(sm, sm_client):
            out = sm.redis_get_key_summary.invoke({"key": "k", "config": CONFIG})
        assert out["data"]["preview"] is None

    def test_flushdb_requires_confirm(self):
        out = sm.redis_flushdb.invoke({"config": CONFIG})
        assert out["error_type"] == "confirmation_required"

    def test_flushdb_confirmed(self):
        fake = FakeRedis(flushdb=True)
        # connection_pool 属性使 getattr 链可用
        fake.connection_pool = MagicMock()
        fake.connection_pool.connection_kwargs = {"host": "h", "port": 6379, "db": 0}
        with _patch(sm, fake):
            out = sm.redis_flushdb.invoke({"confirm": True, "config": CONFIG})
        assert out["success"] is True
        assert out["operation"] == "flushdb"


# ============================ connection gaps ============================
class TestRedisConnection:
    def test_create_client_standalone_drops_none(self):
        with patch.object(conn.redis, "Redis", return_value=MagicMock()) as m:
            conn._create_redis_client({"host": "h", "port": 6379, "db": 0, "username": None,
                                       "password": "p", "cluster_mode": False})
        kwargs = m.call_args.kwargs
        assert kwargs["host"] == "h"
        assert "username" not in kwargs  # None 被过滤
        assert kwargs["decode_responses"] is True

    def test_create_client_cluster_drops_db(self):
        with patch.object(conn, "RedisCluster", return_value=MagicMock()) as m:
            conn._create_redis_client({"host": "h", "port": 6379, "db": 0, "cluster_mode": True})
        kwargs = m.call_args.kwargs
        assert "db" not in kwargs

    def test_build_legacy_config_from_url(self):
        cfg = conn._build_legacy_redis_config({"url": "rediss://user:pass@host:6380/2"})
        assert cfg["host"] == "host"
        assert cfg["port"] == 6380
        assert cfg["db"] == 2
        assert cfg["ssl"] is True

    def test_build_legacy_config_flat(self):
        cfg = conn._build_legacy_redis_config({"host": "h", "port": 6379})
        assert cfg["host"] == "h"
        assert cfg["cluster_mode"] is False

    def test_build_config_from_runnable_legacy_selection_raises(self):
        with pytest.raises(ValueError):
            conn.build_redis_config_from_runnable(CONFIG, instance_name="X")

    def test_build_config_from_runnable_instance(self):
        cfg = {"configurable": {"redis_instances": json.dumps([
            {"id": "a", "name": "A", "url": "redis://h:6379/1"}])}}
        out = conn.build_redis_config_from_runnable(cfg, instance_name="A")
        assert out["host"] == "h"
        assert out["db"] == 1

    def test_get_redis_connection_calls_create(self):
        with patch.object(conn, "_create_redis_client", return_value=MagicMock()) as m:
            conn.get_redis_connection(config=CONFIG)
        assert m.call_args.kwargs["decode_responses"] is True

    def test_get_binary_redis_connection(self):
        with patch.object(conn, "_create_redis_client", return_value=MagicMock()) as m:
            conn.get_binary_redis_connection(config=CONFIG)
        assert m.call_args.kwargs["decode_responses"] is False

    def test_get_connection_from_item(self):
        item = {"config": {"host": "h", "port": 6379, "db": 0, "cluster_mode": False}}
        with patch.object(conn, "_create_redis_client", return_value=MagicMock()) as m:
            conn.get_redis_connection_from_item(item)
        m.assert_called_once()

    def test_get_binary_connection_from_item(self):
        item = {"config": {"host": "h", "port": 6379, "db": 0, "cluster_mode": False}}
        with patch.object(conn, "_create_redis_client", return_value=MagicMock()) as m:
            conn.get_binary_redis_connection_from_item(item)
        assert m.call_args.kwargs["decode_responses"] is False

    def test_adapter_validate(self):
        a = conn.RedisCredentialAdapter()
        a.validate({"host": "h"})
        a.validate({"url": "redis://h"})
        with pytest.raises(conn.CredentialValidationError):
            a.validate({})
        assert a.get_display_name({}, 0) == "Redis - 1"

    def test_build_normalized_multi(self):
        cfg = {"configurable": {"redis_instances": json.dumps([
            {"id": "a", "name": "A", "url": "redis://h1"}, {"id": "b", "name": "B", "url": "redis://h2"}])}}
        n = conn.build_redis_normalized_from_runnable(cfg)
        assert n["mode"] == "multi"
        assert len(n["items"]) == 2

    def test_build_normalized_single_select(self):
        cfg = {"configurable": {"redis_instances": json.dumps([
            {"id": "a", "name": "A", "url": "redis://h1"}, {"id": "b", "name": "B", "url": "redis://h2"}])}}
        n = conn.build_redis_normalized_from_runnable(cfg, instance_id="b")
        assert n["mode"] == "single"
        assert n["items"][0]["name"] == "B"

    def test_test_redis_instance_ping(self):
        from redis import Redis
        fake = MagicMock(spec=Redis)
        fake.ping.return_value = True
        with patch.object(conn, "_create_redis_client", return_value=fake):
            ok = conn.test_redis_instance({"url": "redis://h:6379/0"})
        assert ok is True
        fake.close.assert_called_once()

    def test_test_redis_instance_no_url(self):
        with pytest.raises(ValueError):
            conn.test_redis_instance({"url": ""})
