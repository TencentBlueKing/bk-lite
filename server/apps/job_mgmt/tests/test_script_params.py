"""脚本参数服务 / 执行端参数注入单元测试"""

import shlex

import pytest
from rest_framework import serializers

from apps.job_mgmt.constants import ScriptType
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.job_mgmt.services.script_params_service import ScriptParamsService


class FakeScript:
    """仅提供 params 属性，避免依赖 DB 的轻量替身。"""

    def __init__(self, params):
        self.params = params


def _merge(params_str, script_type, content="echo hi"):
    # merge_script_with_params 不使用 self，传 None 即可，避免实例化触发 DB 查询
    return ScriptExecutionRunner.merge_script_with_params(None, content, params_str, script_type)


@pytest.mark.unit
class TestParamsToString:
    def test_empty_value_keeps_position(self):
        """中间空值参数以 '' 占位，shlex 还原后位置不前移"""
        s = ScriptParamsService.params_to_string([{"value": "a"}, {"value": ""}, {"value": "c"}])
        assert shlex.split(s) == ["a", "", "c"]

    def test_value_with_space_quoted(self):
        """含空格的值保持为单个参数"""
        s = ScriptParamsService.params_to_string([{"value": "a b"}, {"value": "c"}])
        assert shlex.split(s) == ["a b", "c"]

    def test_empty_list(self):
        assert ScriptParamsService.params_to_string([]) == ""


@pytest.mark.unit
class TestMergeScriptWithParams:
    def test_shell_set_dashdash_preserves_empty(self):
        merged = _merge("a '' c", ScriptType.SHELL, "echo $2")
        assert merged.startswith("set -- a '' c\n")
        assert merged.endswith("echo $2")
        assert shlex.split(merged.split("\n", 1)[0][len("set -- ") :]) == ["a", "", "c"]

    def test_python_injects_sys_argv(self):
        merged = _merge("a '' c", ScriptType.PYTHON, "import sys; print(sys.argv)")
        assert '_sys.argv = ["script", "a", "", "c"]' in merged
        assert merged.strip().endswith("print(sys.argv)")

    def test_powershell_injects_args(self):
        merged = _merge("a '' c", ScriptType.POWERSHELL, "Write-Output $args")
        assert "$args = @('a', '', 'c')" in merged

    def test_bat_ignores_params(self):
        """bat 当前不支持参数注入，原样返回脚本内容"""
        merged = _merge("a b", ScriptType.BAT, "echo %1")
        assert merged == "echo %1"

    def test_no_params_returns_content(self):
        assert _merge("", ScriptType.SHELL, "echo hi") == "echo hi"

    def test_unbalanced_quote_falls_back_to_split(self):
        # shlex.split 遇到不闭合引号抛 ValueError，回退到 str.split
        merged = _merge("a 'b", ScriptType.SHELL, "echo hi")
        assert merged.startswith("set -- ")
        assert merged.endswith("echo hi")

    def test_whitespace_only_params_returns_content(self):
        # 非空但分词后无 token，原样返回脚本内容
        assert _merge("   ", ScriptType.SHELL, "echo hi") == "echo hi"


@pytest.mark.unit
class TestRequiredValidation:
    def test_required_empty_raises(self):
        script = FakeScript([{"name": "p1", "is_required": True, "default": ""}])
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.resolve_params([{"name": "p1", "value": "", "is_modified": True}], script=script)

    def test_required_filled_ok(self):
        script = FakeScript([{"name": "p1", "is_required": True, "default": ""}])
        out = ScriptParamsService.resolve_params([{"name": "p1", "value": "x", "is_modified": True}], script=script)
        assert out[0]["value"] == "x"

    def test_optional_empty_ok(self):
        script = FakeScript([{"name": "p1", "is_required": False, "default": ""}])
        out = ScriptParamsService.resolve_params([{"name": "p1", "value": "", "is_modified": True}], script=script)
        assert out[0]["value"] == ""


@pytest.mark.unit
class TestValidateParamsFormat:
    def test_non_list_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.validate_params_format("not-a-list")

    def test_non_dict_item_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.validate_params_format(["x"], require_is_modified=False)

    def test_missing_value_key_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.validate_params_format([{"name": "p"}], require_is_modified=False)

    def test_missing_is_modified_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.validate_params_format([{"value": "x"}], require_is_modified=True)

    def test_name_not_str_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.validate_params_format([{"value": "x", "name": 123}], require_is_modified=False)

    def test_is_modified_not_bool_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.validate_params_format([{"value": "x", "is_modified": "yes"}], require_is_modified=False)

    def test_valid_passes(self):
        # 合法格式不抛异常
        ScriptParamsService.validate_params_format([{"value": "x", "is_modified": True}], require_is_modified=True)


@pytest.mark.unit
class TestGetScriptDefaultParams:
    def test_none_script_returns_empty(self):
        assert ScriptParamsService.get_script_default_params(None) == []

    def test_script_without_params_returns_empty(self):
        assert ScriptParamsService.get_script_default_params(FakeScript([])) == []

    def test_returns_dict_defs(self):
        defs = [{"name": "p", "default": "1"}]
        assert ScriptParamsService.get_script_default_params(FakeScript(defs)) == defs


@pytest.mark.unit
class TestResolveParams:
    def test_empty_returns_empty(self):
        assert ScriptParamsService.resolve_params([]) == []

    def test_unmodified_backfills_script_default(self):
        script = FakeScript([{"name": "p1", "default": "D", "is_required": False}])
        out = ScriptParamsService.resolve_params([{"name": "p1", "value": "ignored", "is_modified": False}], script=script)
        assert out[0]["value"] == "D"

    def test_unmodified_index_out_of_range_raises(self):
        script = FakeScript([{"name": "p1", "default": "D"}])
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.resolve_params(
                [
                    {"name": "p1", "value": "", "is_modified": False},
                    {"name": "p2", "value": "", "is_modified": False},
                ],
                script=script,
            )

    def test_unmodified_without_script_disallowed_raises(self):
        with pytest.raises(serializers.ValidationError):
            ScriptParamsService.resolve_params(
                [{"name": "p", "value": "x", "is_modified": False}],
                script=None,
                allow_unmodified_without_script=False,
            )

    def test_unmodified_without_script_allowed_uses_value(self):
        out = ScriptParamsService.resolve_params(
            [{"name": "p", "value": "x", "is_modified": False}],
            script=None,
            allow_unmodified_without_script=True,
        )
        assert out[0]["value"] == "x"


@pytest.mark.unit
class TestParamsToDict:
    def test_empty_returns_empty_dict(self):
        assert ScriptParamsService.params_to_dict([]) == {}

    def test_maps_name_to_value(self):
        out = ScriptParamsService.params_to_dict([{"name": "a", "value": "1"}, {"key": "b", "value": "2"}])
        assert out == {"a": "1", "b": "2"}

    def test_skips_items_without_name(self):
        assert ScriptParamsService.params_to_dict([{"value": "x"}]) == {}
