"""
回归测试：PromQL/MetricsQL 注入防护 — format_to_vm_filter

测试策略：Django-free，直接 import 被测函数，无需 ORM/settings。
revert-fail 准则：将 format_to_vm_filter 中的 _escape_label_value 调用还原为原始
拼接（直接 f'{name}{method}"{value}"'），测试中的注入断言将立即失败。
"""
import importlib.util
import sys
import types

import pytest

# ---------------------------------------------------------------------------
# 最小化 Django-free 加载机制（无需 settings/ORM）
# ---------------------------------------------------------------------------

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# 加载被测模块
_MQ = _load_module(
    "apps.monitor.tasks.utils.metric_query",
    __file__.replace(
        "tests/test_metric_query_injection.py",
        "tasks/utils/metric_query.py",
    ),
)
format_to_vm_filter = _MQ.format_to_vm_filter


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------

class TestFormatToVmFilterNormal:
    def test_single_condition(self):
        result = format_to_vm_filter([{"name": "host", "value": "web-01", "method": "="}])
        assert result == 'host="web-01"'

    def test_multiple_conditions_joined_by_comma(self):
        result = format_to_vm_filter([
            {"name": "host", "value": "web-01", "method": "="},
            {"name": "env", "value": "prod", "method": "!="},
        ])
        assert result == 'host="web-01",env!="prod"'

    def test_empty_conditions_returns_empty_string(self):
        assert format_to_vm_filter([]) == ""

    def test_regex_operator_accepted(self):
        result = format_to_vm_filter([{"name": "job", "value": "node.*", "method": "=~"}])
        assert result == 'job=~"node.*"'

    def test_negative_regex_operator_accepted(self):
        result = format_to_vm_filter([{"name": "job", "value": "ignore.*", "method": "!~"}])
        assert result == 'job!~"ignore.*"'

    def test_none_value_treated_as_empty_string(self):
        result = format_to_vm_filter([{"name": "tag", "value": None, "method": "="}])
        assert result == 'tag=""'


# ---------------------------------------------------------------------------
# 转义：revert 修复后这些断言必然失败
# ---------------------------------------------------------------------------

class TestValueEscaping:
    def test_double_quote_in_value_is_escaped(self):
        """核心：双引号必须被转义，否则会跳出 label value 边界造成注入。"""
        result = format_to_vm_filter([{"name": "host", "value": 'foo"bar', "method": "="}])
        # 正确结果：foo\"bar
        assert '\\"' in result, f"双引号未转义，实际结果：{result!r}"
        assert result == r'host="foo\"bar"'

    def test_backslash_in_value_is_escaped(self):
        result = format_to_vm_filter([{"name": "path", "value": "C:\\Users", "method": "="}])
        assert result == r'path="C:\\Users"'

    def test_injection_payload_is_neutralized(self):
        """
        经典注入串：} or vector(1) #
        未转义时会闭合 label selector 并注入额外查询；
        转义后 " 变成 \\"，PromQL 解析器不会将其视为关闭 label value 的引号。
        """
        payload = 'foo"} or vector(1) #'
        result = format_to_vm_filter([{"name": "host", "value": payload, "method": "="}])
        # 确保 " 被转义为 \" （即字符串中含 \\"）
        assert '\\"' in result, f"双引号未被转义：{result!r}"
        # 确保整体结果正确：host="foo\"} or vector(1) #"
        expected = 'host="foo\\"} or vector(1) #"'
        assert result == expected, f"期望 {expected!r}，实际 {result!r}"

    def test_combined_backslash_and_quote(self):
        result = format_to_vm_filter([{"name": "x", "value": 'a\\"b', "method": "="}])
        # 原始值 a\"b → 先转义 \ → a\\"b → 再转义 " → a\\\"b
        assert result == r'x="a\\\"b"'


# ---------------------------------------------------------------------------
# name 校验：revert 后这些 ValueError 不再被抛出，断言失败
# ---------------------------------------------------------------------------

class TestNameValidation:
    def test_name_with_special_char_raises(self):
        with pytest.raises(ValueError, match="非法的 label name"):
            format_to_vm_filter([{"name": "bad-name", "value": "v", "method": "="}])

    def test_name_starting_with_digit_raises(self):
        with pytest.raises(ValueError, match="非法的 label name"):
            format_to_vm_filter([{"name": "1bad", "value": "v", "method": "="}])

    def test_name_with_dot_raises(self):
        with pytest.raises(ValueError, match="非法的 label name"):
            format_to_vm_filter([{"name": "a.b", "value": "v", "method": "="}])

    def test_valid_name_with_underscore_passes(self):
        result = format_to_vm_filter([{"name": "_internal_label", "value": "v", "method": "="}])
        assert result.startswith("_internal_label=")

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="非法的 label name"):
            format_to_vm_filter([{"name": "", "value": "v", "method": "="}])


# ---------------------------------------------------------------------------
# method 白名单：revert 后 ValueError 不再抛出，断言失败
# ---------------------------------------------------------------------------

class TestMethodValidation:
    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="非法的运算符"):
            format_to_vm_filter([{"name": "host", "value": "v", "method": "LIKE"}])

    def test_gt_operator_raises(self):
        with pytest.raises(ValueError, match="非法的运算符"):
            format_to_vm_filter([{"name": "host", "value": "v", "method": ">"}])

    def test_injection_via_method_raises(self):
        """攻击者尝试通过 method 字段注入额外查询片段。"""
        with pytest.raises(ValueError, match="非法的运算符"):
            format_to_vm_filter([{"name": "host", "value": "v", "method": '="x"} or vector(1) #'}])

    @pytest.mark.parametrize("method", ["=", "!=", "=~", "!~"])
    def test_all_valid_methods_pass(self, method):
        result = format_to_vm_filter([{"name": "host", "value": "v", "method": method}])
        assert f'host{method}"v"' == result
