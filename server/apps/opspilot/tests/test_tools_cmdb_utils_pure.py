"""CMDB 工具仍保留的纯函数契约：查询条件归一化与响应包装。

身份与权限传递由 test_tools_cmdb_service.py 验证当前 RPC 边界。
"""

from apps.opspilot.metis.llm.tools.cmdb import utils as cu


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

    def test_wrap_error_missing_params_asks_user_choice(self):
        out = cu.wrap_error("search is required")
        assert out["success"] is False
        assert out["error"] == "search is required"
        assert "request_user_choice" in out["_next_step_hint"]
