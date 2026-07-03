"""CMDB 工具纯函数单元测试 (cmdb/utils)。

覆盖配置提取、用户组 id 解析、查询条件归一化、响应包装、写权限护栏、JSON 序列化。
不触 DB(使用轻量假 user 对象,仅访问属性)。
"""

from types import SimpleNamespace

import pytest

from apps.opspilot.metis.llm.tools.cmdb import utils as cu


class TestGetConfigurable:
    def test_none_returns_empty(self):
        assert cu._get_configurable(None) == {}

    def test_dict_config(self):
        assert cu._get_configurable({"configurable": {"a": 1}}) == {"a": 1}

    def test_object_config(self):
        cfg = SimpleNamespace(configurable={"b": 2})
        assert cu._get_configurable(cfg) == {"b": 2}


class TestGetUserGroupIds:
    def test_empty(self):
        assert cu._get_user_group_ids(SimpleNamespace(group_list=[])) == []

    def test_list_of_dicts(self):
        user = SimpleNamespace(group_list=[{"id": "1"}, {"id": 2}, {"name": "no-id"}])
        assert cu._get_user_group_ids(user) == [1, 2]

    def test_list_of_ints(self):
        user = SimpleNamespace(group_list=[3, "4"])
        assert cu._get_user_group_ids(user) == [3, 4]

    def test_missing_attr(self):
        assert cu._get_user_group_ids(SimpleNamespace()) == []


class TestNormalizeQueryList:
    def test_none(self):
        assert cu.normalize_query_list(None) == []

    def test_single_dict_wrapped(self):
        out = cu.normalize_query_list({"field": "name", "type": "str=", "value": "x"})
        assert out == [{"field": "name", "type": "str=", "value": "x"}]

    def test_non_list_non_dict(self):
        assert cu.normalize_query_list("string") == []

    def test_missing_field_or_type_dropped(self):
        out = cu.normalize_query_list([{"field": "a"}, {"type": "str="}])
        assert out == []

    def test_time_type_needs_start_end(self):
        ok = {"field": "t", "type": "time", "start": "s", "end": "e"}
        assert cu.normalize_query_list([ok]) == [ok]
        bad = {"field": "t", "type": "time", "start": "s"}
        assert cu.normalize_query_list([bad]) == []

    def test_empty_string_value_dropped(self):
        assert cu.normalize_query_list([{"field": "a", "type": "str=", "value": ""}]) == []

    def test_empty_list_value_dropped(self):
        assert cu.normalize_query_list([{"field": "a", "type": "in", "value": []}]) == []

    def test_none_value_dropped(self):
        assert cu.normalize_query_list([{"field": "a", "type": "str=", "value": None}]) == []

    def test_nested_lists_walked(self):
        nested = [[{"field": "a", "type": "str=", "value": "1"}], {"field": "b", "type": "str=", "value": "2"}]
        out = cu.normalize_query_list(nested)
        assert {c["field"] for c in out} == {"a", "b"}

    def test_value_zero_kept(self):
        out = cu.normalize_query_list([{"field": "a", "type": "int=", "value": 0}])
        assert out == [{"field": "a", "type": "int=", "value": 0}]


class TestWrappers:
    def test_wrap_success(self):
        assert cu.wrap_success([1, 2]) == {"success": True, "data": [1, 2]}

    def test_wrap_error(self):
        assert cu.wrap_error("nope") == {"success": False, "error": "nope"}

    def test_to_json_safe_unicode(self):
        assert cu.to_json_safe({"名": "值"}) == '{"名": "值"}'


class TestEnsureWriteAllowed:
    def test_disabled_raises(self):
        with pytest.raises(ValueError, match="disabled"):
            cu.ensure_write_allowed(SimpleNamespace(is_superuser=True), allow_write=False)

    def test_non_superuser_raises(self):
        with pytest.raises(ValueError, match="superuser"):
            cu.ensure_write_allowed(SimpleNamespace(is_superuser=False), allow_write=True)

    def test_superuser_with_write_ok(self):
        # 不应抛异常
        cu.ensure_write_allowed(SimpleNamespace(is_superuser=True), allow_write=True)


class TestResolveAllowWrite:
    def test_explicit_overrides(self):
        assert cu._resolve_allow_write({"configurable": {"allow_write": True}}, allow_write=False) is False

    def test_from_configurable(self):
        assert cu._resolve_allow_write({"configurable": {"allow_write": True}}, allow_write=None) is True

    def test_default_false(self):
        assert cu._resolve_allow_write({}, allow_write=None) is False
