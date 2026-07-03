"""Redis @tool 类型工具单元测试 (redis/set|sorted_set|json|stream|pub_sub|query_engine)。

mock 边界为各模块导入的 get_redis_connection_from_item(driver client 获取),返回
MagicMock client;断言 build_success_response/build_error_response 结构、入参契约
(命令参数转发)、JSON 值解析、bytes 规整与 RedisError 翻译。不连真实 Redis,
不做真实向量检索(仅断言索引列表/info 等命令型工具)。
"""

import pydantic.root_model  # noqa
import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import json as rjson
from apps.opspilot.metis.llm.tools.redis import pub_sub as rps
from apps.opspilot.metis.llm.tools.redis import query_engine as rqe
from apps.opspilot.metis.llm.tools.redis import set as rset
from apps.opspilot.metis.llm.tools.redis import sorted_set as rzset
from apps.opspilot.metis.llm.tools.redis import stream as rstream

from unittest.mock import MagicMock, patch

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


@pytest.fixture
def client():
    return MagicMock()


def _patch(module, client):
    return patch.object(module, "get_redis_connection_from_item", return_value=client)


# ---------------- set ----------------
class TestRedisSet:
    def test_sadd_forwards_and_reports_added(self, client):
        client.sadd.return_value = 1
        with _patch(rset, client):
            out = rset.redis_sadd.invoke({"key": "s", "member": "m", "config": CONFIG})
        assert out["success"] is True
        assert out["data"] == {"added": 1}
        assert out["key"] == "s"
        client.sadd.assert_called_once_with("s", "m")

    def test_smembers_normalizes_bytes(self, client):
        client.smembers.return_value = {b"a", b"b"}
        with _patch(rset, client):
            out = rset.redis_smembers.invoke({"key": "s", "config": CONFIG})
        assert out["success"] is True
        assert set(out["data"]) == {"a", "b"}

    def test_sismember_bool(self, client):
        client.sismember.return_value = 1
        with _patch(rset, client):
            out = rset.redis_sismember.invoke({"key": "s", "member": "m", "config": CONFIG})
        assert out["data"]["is_member"] is True

    def test_sinter_list(self, client):
        client.sinter.return_value = {b"x"}
        with _patch(rset, client):
            out = rset.redis_sinter.invoke({"keys": ["a", "b"], "config": CONFIG})
        assert out["data"] == ["x"]
        client.sinter.assert_called_once_with(["a", "b"])

    def test_scard_error_translated(self, client):
        client.scard.side_effect = RedisError("WRONGTYPE")
        with _patch(rset, client):
            out = rset.redis_scard.invoke({"key": "s", "config": CONFIG})
        assert out["success"] is False
        assert out["error"] == "WRONGTYPE"
        assert out["error_type"] == "redis_error"


# ---------------- sorted_set ----------------
class TestRedisSortedSet:
    def test_zadd(self, client):
        client.zadd.return_value = 2
        with _patch(rzset, client):
            out = rzset.redis_zadd.invoke({"key": "z", "members": {"a": 1.0, "b": 2.0}, "config": CONFIG})
        assert out["data"] == {"added": 2}
        client.zadd.assert_called_once_with("z", {"a": 1.0, "b": 2.0})

    def test_zrange_withscores(self, client):
        client.zrange.return_value = [(b"a", 1.0), (b"b", 2.0)]
        with _patch(rzset, client):
            out = rzset.redis_zrange.invoke({"key": "z", "start": 0, "end": -1, "withscores": True, "config": CONFIG})
        assert out["data"] == [["a", 1.0], ["b", 2.0]]
        client.zrange.assert_called_once_with("z", 0, -1, withscores=True)

    def test_zscore(self, client):
        client.zscore.return_value = 3.5
        with _patch(rzset, client):
            out = rzset.redis_zscore.invoke({"key": "z", "member": "m", "config": CONFIG})
        assert out["data"]["score"] == 3.5

    def test_zrank_none_when_absent(self, client):
        client.zrank.return_value = None
        with _patch(rzset, client):
            out = rzset.redis_zrank.invoke({"key": "z", "member": "x", "config": CONFIG})
        assert out["data"]["rank"] is None

    def test_zrangebyscore(self, client):
        client.zrangebyscore.return_value = [b"a"]
        with _patch(rzset, client):
            out = rzset.redis_zrangebyscore.invoke(
                {"key": "z", "min_score": 0, "max_score": 10, "config": CONFIG})
        assert out["data"] == ["a"]
        client.zrangebyscore.assert_called_once_with("z", 0, 10, withscores=False)


# ---------------- json ----------------
class TestRedisJson:
    def test_json_set_parses_json_value(self, client):
        json_mod = MagicMock()
        client.json.return_value = json_mod
        with _patch(rjson, client):
            out = rjson.redis_json_set.invoke(
                {"name": "doc", "path": "$", "value": '{"a": 1}', "config": CONFIG})
        assert out["success"] is True
        json_mod.set.assert_called_once_with("doc", "$", {"a": 1})

    def test_json_set_non_json_value_kept_as_str(self, client):
        json_mod = MagicMock()
        client.json.return_value = json_mod
        with _patch(rjson, client):
            rjson.redis_json_set.invoke({"name": "doc", "path": "$.s", "value": "plain", "config": CONFIG})
        json_mod.set.assert_called_once_with("doc", "$.s", "plain")

    def test_json_set_with_expire(self, client):
        json_mod = MagicMock()
        client.json.return_value = json_mod
        with _patch(rjson, client):
            out = rjson.redis_json_set.invoke(
                {"name": "doc", "path": "$", "value": "1", "expire_seconds": 60, "config": CONFIG})
        client.expire.assert_called_once_with("doc", 60)
        assert out["data"]["expire_seconds"] == 60

    def test_json_get(self, client):
        json_mod = MagicMock()
        json_mod.get.return_value = {"a": 1}
        client.json.return_value = json_mod
        with _patch(rjson, client):
            out = rjson.redis_json_get.invoke({"name": "doc", "path": "$.a", "config": CONFIG})
        assert out["data"] == {"a": 1}
        json_mod.get.assert_called_once_with("doc", "$.a")

    def test_json_unsupported_feature_error(self, client):
        json_mod = MagicMock()
        json_mod.get.side_effect = RedisError("unknown command JSON.GET")
        client.json.return_value = json_mod
        with _patch(rjson, client):
            out = rjson.redis_json_get.invoke({"name": "doc", "config": CONFIG})
        assert out["success"] is False
        assert out["error_type"] == "unsupported_feature"


# ---------------- stream ----------------
class TestRedisStream:
    def test_xadd(self, client):
        client.xadd.return_value = b"1-0"
        with _patch(rstream, client):
            out = rstream.redis_xadd.invoke({"key": "st", "fields": {"f": "v"}, "config": CONFIG})
        assert out["data"]["entry_id"] == "1-0"
        client.xadd.assert_called_once_with("st", {"f": "v"})

    def test_xadd_with_expiration(self, client):
        client.xadd.return_value = b"2-0"
        with _patch(rstream, client):
            rstream.redis_xadd.invoke({"key": "st", "fields": {"f": "v"}, "expiration": 30, "config": CONFIG})
        client.expire.assert_called_once_with("st", 30)

    def test_xdel(self, client):
        client.xdel.return_value = 1
        with _patch(rstream, client):
            out = rstream.redis_xdel.invoke({"key": "st", "entry_id": "1-0", "config": CONFIG})
        assert out["data"]["deleted"] == 1
        client.xdel.assert_called_once_with("st", "1-0")

    def test_xgroup_create(self, client):
        client.xgroup_create.return_value = True
        with _patch(rstream, client):
            out = rstream.redis_xgroup_create.invoke(
                {"key": "st", "group_name": "g", "config": CONFIG})
        assert out["data"]["created"] is True
        assert out["data"]["group_name"] == "g"

    def test_xack(self, client):
        client.xack.return_value = 2
        with _patch(rstream, client):
            out = rstream.redis_xack.invoke(
                {"key": "st", "group_name": "g", "entry_ids": ["1-0", "2-0"], "config": CONFIG})
        assert out["data"]["acked"] == 2
        client.xack.assert_called_once_with("st", "g", "1-0", "2-0")

    def test_xrange_error(self, client):
        client.xrange.side_effect = RedisError("boom")
        with _patch(rstream, client):
            out = rstream.redis_xrange.invoke({"key": "st", "config": CONFIG})
        assert out["success"] is False
        assert out["error"] == "boom"


# ---------------- pub_sub ----------------
class TestRedisPubSub:
    def test_publish_reports_receivers(self, client):
        client.publish.return_value = 3
        with _patch(rps, client):
            out = rps.redis_publish.invoke({"channel": "c", "message": "hi", "config": CONFIG})
        assert out["data"] == {"channel": "c", "receivers": 3}
        client.publish.assert_called_once_with("c", "hi")

    def test_pubsub_channels_normalizes_bytes(self, client):
        client.pubsub_channels.return_value = [b"c1", b"c2"]
        with _patch(rps, client):
            out = rps.redis_pubsub_channels.invoke({"pattern": "c*", "config": CONFIG})
        assert out["data"] == ["c1", "c2"]
        client.pubsub_channels.assert_called_once_with("c*")

    def test_subscribe_invokes_pubsub(self, client):
        pubsub = MagicMock()
        client.pubsub.return_value = pubsub
        with _patch(rps, client):
            out = rps.redis_subscribe.invoke({"channel": "c", "config": CONFIG})
        assert out["data"]["subscribed"] is True
        pubsub.subscribe.assert_called_once_with("c")

    def test_unsubscribe(self, client):
        pubsub = MagicMock()
        client.pubsub.return_value = pubsub
        with _patch(rps, client):
            out = rps.redis_unsubscribe.invoke({"channel": "c", "config": CONFIG})
        assert out["data"]["unsubscribed"] is True
        pubsub.unsubscribe.assert_called_once_with("c")

    def test_publish_error(self, client):
        client.publish.side_effect = RedisError("down")
        with _patch(rps, client):
            out = rps.redis_publish.invoke({"channel": "c", "message": "m", "config": CONFIG})
        assert out["success"] is False
        assert out["error"] == "down"


# ---------------- query_engine (索引命令型,非向量检索) ----------------
class TestRedisQueryEngine:
    def test_get_indexes(self, client):
        client.execute_command.return_value = [b"idx1", b"idx2"]
        with _patch(rqe, client):
            out = rqe.redis_get_indexes.invoke({"config": CONFIG})
        assert out["data"] == ["idx1", "idx2"]
        client.execute_command.assert_called_once_with("FT._LIST")

    def test_get_index_info(self, client):
        ft = MagicMock()
        ft.info.return_value = {"num_docs": 10}
        client.ft.return_value = ft
        with _patch(rqe, client):
            out = rqe.redis_get_index_info.invoke({"index_name": "idx", "config": CONFIG})
        assert out["data"] == {"num_docs": 10}
        client.ft.assert_called_once_with("idx")

    def test_indexed_keys_number(self, client):
        ft = MagicMock()
        search_result = MagicMock()
        search_result.total = 42
        ft.search.return_value = search_result
        client.ft.return_value = ft
        with _patch(rqe, client):
            out = rqe.redis_get_indexed_keys_number.invoke({"index_name": "idx", "config": CONFIG})
        assert out["data"]["total"] == 42
        assert out["data"]["index_name"] == "idx"

    def test_get_indexes_unsupported(self, client):
        client.execute_command.side_effect = RedisError("unknown command FT._LIST")
        with _patch(rqe, client):
            out = rqe.redis_get_indexes.invoke({"config": CONFIG})
        assert out["success"] is False
        assert out["error_type"] == "unsupported_feature"
