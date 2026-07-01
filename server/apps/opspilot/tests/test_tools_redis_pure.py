"""Redis 工具纯函数单元测试 (redis/utils + redis/connection)。

覆盖 JSON 安全序列化、截断、确认护栏,以及连接配置的解析/归一化/实例解析。
不连接真实 Redis;仅测纯逻辑与配置构造。
"""

import pytest

from apps.opspilot.metis.llm.tools.redis import connection as conn
from apps.opspilot.metis.llm.tools.redis import utils


class TestEnsureJsonSerializable:
    def test_primitives_passthrough(self):
        assert utils.ensure_json_serializable(1) == 1
        assert utils.ensure_json_serializable("x") == "x"
        assert utils.ensure_json_serializable(None) is None
        assert utils.ensure_json_serializable(True) is True

    def test_bytes_utf8_decoded(self):
        assert utils.ensure_json_serializable(b"hello") == "hello"

    def test_bytes_invalid_utf8_hex(self):
        assert utils.ensure_json_serializable(b"\xff\xfe") == "fffe"

    def test_nested_dict_keys_stringified(self):
        out = utils.ensure_json_serializable({1: b"v", "a": [b"x"]})
        assert out == {"1": "v", "a": ["x"]}

    def test_set_and_tuple_become_lists(self):
        assert utils.ensure_json_serializable((1, 2)) == [1, 2]
        assert sorted(utils.ensure_json_serializable({1, 2})) == [1, 2]

    def test_unknown_object_str_fallback(self):
        class C:
            def __str__(self):
                return "C-obj"

        assert utils.ensure_json_serializable(C()) == "C-obj"


class TestResponses:
    def test_safe_json_dumps_roundtrip(self):
        assert utils.safe_json_dumps({"a": b"x"}) == '{"a": "x"}'

    def test_build_success_response_with_extra(self):
        out = utils.build_success_response([b"a"], count=2)
        assert out == {"success": True, "data": ["a"], "count": 2}

    def test_build_error_response_default_type(self):
        out = utils.build_error_response(ValueError("boom"))
        assert out == {"success": False, "error": "boom", "error_type": "redis_error"}

    def test_build_error_response_custom_type(self):
        out = utils.build_error_response("x", error_type="timeout")
        assert out["error_type"] == "timeout"


class TestTruncate:
    def test_truncate_sequence_under_limit(self):
        out = utils.truncate_sequence([1, 2, 3], max_items=10)
        assert out["truncated"] is False
        assert out["returned_count"] == 3
        assert out["total_count"] == 3
        assert out["items"] == [1, 2, 3]

    def test_truncate_sequence_over_limit(self):
        out = utils.truncate_sequence(list(range(5)), max_items=2)
        assert out["truncated"] is True
        assert out["returned_count"] == 2
        assert out["total_count"] == 5
        assert out["items"] == [0, 1]

    def test_truncate_mapping_over_limit(self):
        data = {str(i): i for i in range(5)}
        out = utils.truncate_mapping(data, max_items=3)
        assert out["truncated"] is True
        assert out["returned_count"] == 3
        assert out["total_count"] == 5


class TestRequireConfirm:
    def test_confirmed_returns_none(self):
        assert utils.require_confirm(True, "DEL") is None

    def test_unconfirmed_returns_error(self):
        out = utils.require_confirm(False, "FLUSHDB")
        assert out["success"] is False
        assert out["error_type"] == "confirmation_required"
        assert "FLUSHDB" in out["error"]


class TestParseRedisUrl:
    def test_basic_url(self):
        out = conn.parse_redis_url("redis://user:pass@host:6380/2")
        assert out["host"] == "host"
        assert out["port"] == 6380
        assert out["db"] == 2
        assert out["username"] == "user"
        assert out["password"] == "pass"
        assert out["ssl"] is False

    def test_rediss_scheme_enables_ssl(self):
        out = conn.parse_redis_url("rediss://host:6379/0")
        assert out["ssl"] is True

    def test_defaults_when_missing(self):
        out = conn.parse_redis_url("redis://localhost")
        assert out["host"] == "localhost"
        assert out["port"] == 6379
        assert out["db"] == 0

    def test_invalid_db_path_defaults_to_zero(self):
        out = conn.parse_redis_url("redis://host:6379/notanumber")
        assert out["db"] == 0


class TestNormalizeRedisInstance:
    def test_fallbacks_applied(self):
        out = conn.normalize_redis_instance({})
        assert out["id"] == "redis-1"
        assert out["name"] == "Redis - 1"
        assert out["ssl"] is False
        assert out["cluster_mode"] is False

    def test_bool_coercion_from_string(self):
        out = conn.normalize_redis_instance({"ssl": "true", "cluster_mode": "no"})
        assert out["ssl"] is True
        assert out["cluster_mode"] is False

    def test_custom_fallback_ids(self):
        out = conn.normalize_redis_instance({}, fallback_name="N", fallback_id="abc")
        assert out["id"] == "abc"
        assert out["name"] == "N"


class TestParseRedisInstances:
    def test_empty_returns_empty(self):
        assert conn.parse_redis_instances(None) == []
        assert conn.parse_redis_instances([]) == []

    def test_json_string_parsed(self):
        out = conn.parse_redis_instances('[{"name": "A", "url": "redis://h"}]')
        assert len(out) == 1
        assert out[0]["name"] == "A"

    def test_invalid_json_returns_empty(self):
        assert conn.parse_redis_instances("{not json") == []

    def test_non_list_returns_empty(self):
        assert conn.parse_redis_instances('{"a": 1}') == []

    def test_non_dict_items_skipped(self):
        out = conn.parse_redis_instances([{"name": "A"}, "bad", 5])
        assert len(out) == 1


class TestResolveRedisInstance:
    @pytest.fixture
    def instances(self):
        return [
            {"id": "i1", "name": "Alpha"},
            {"id": "i2", "name": "Beta"},
        ]

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No Redis instances"):
            conn.resolve_redis_instance([])

    def test_by_id(self, instances):
        assert conn.resolve_redis_instance(instances, instance_id="i2")["name"] == "Beta"

    def test_by_id_not_found_raises(self, instances):
        with pytest.raises(ValueError, match="not found"):
            conn.resolve_redis_instance(instances, instance_id="zzz")

    def test_by_name(self, instances):
        assert conn.resolve_redis_instance(instances, instance_name="Alpha")["id"] == "i1"

    def test_by_name_not_found_raises(self, instances):
        with pytest.raises(ValueError, match="not found"):
            conn.resolve_redis_instance(instances, instance_name="Gamma")

    def test_default_id_used(self, instances):
        assert conn.resolve_redis_instance(instances, default_instance_id="i2")["name"] == "Beta"

    def test_fallback_first(self, instances):
        assert conn.resolve_redis_instance(instances)["id"] == "i1"


class TestBuildRedisConfigFromInstance:
    def test_from_url(self):
        out = conn.build_redis_config_from_instance({"url": "redis://h:6390/1", "name": "X"})
        assert out["host"] == "h"
        assert out["port"] == 6390
        assert out["db"] == 1

    def test_without_url_defaults(self):
        out = conn.build_redis_config_from_instance({"name": "X"})
        assert out["host"] == "127.0.0.1"
        assert out["port"] == 6379

    def test_username_password_override(self):
        out = conn.build_redis_config_from_instance({"url": "redis://h", "username": "u", "password": "p"})
        assert out["username"] == "u"
        assert out["password"] == "p"


class TestBuildRedisConfigFromRunnable:
    def test_legacy_flat_config(self):
        cfg = {"configurable": {"host": "myhost", "port": 6399, "db": 3}}
        out = conn.build_redis_config_from_runnable(cfg)
        assert out["host"] == "myhost"
        assert out["port"] == 6399
        assert out["db"] == 3

    def test_legacy_url_config(self):
        cfg = {"configurable": {"url": "redis://uh:6380/4"}}
        out = conn.build_redis_config_from_runnable(cfg)
        assert out["host"] == "uh"
        assert out["db"] == 4

    def test_instances_selected_by_name(self):
        cfg = {"configurable": {"redis_instances": [{"id": "a", "name": "A", "url": "redis://ha"}, {"id": "b", "name": "B", "url": "redis://hb"}]}}
        out = conn.build_redis_config_from_runnable(cfg, instance_name="B")
        assert out["host"] == "hb"

    def test_instance_selection_unavailable_for_legacy_raises(self):
        cfg = {"configurable": {"host": "x"}}
        with pytest.raises(ValueError, match="unavailable"):
            conn.build_redis_config_from_runnable(cfg, instance_name="B")


class TestGetRedisInstancesPrompt:
    def test_no_instances_empty_string(self):
        assert conn.get_redis_instances_prompt({}) == ""

    def test_prompt_mentions_default_and_names(self):
        configurable = {
            "redis_instances": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "redis_default_instance_id": "b",
        }
        prompt = conn.get_redis_instances_prompt(configurable)
        assert "「B」" in prompt
        assert "A" in prompt and "B" in prompt
        assert "2 个 Redis 实例" in prompt
