"""脚本库参数定义：枚举类型规范化与执行白名单。"""

import pytest
from rest_framework.exceptions import ValidationError

from apps.job_mgmt.services.script_param_definitions import assert_execution_value_allowed, normalize_script_param_definitions
from apps.job_mgmt.services.script_params_service import ScriptParamsService

pytestmark = pytest.mark.unit


class TestNormalizeScriptParamDefinitions:
    def test_缺省类型视为text并去掉options(self):
        params = [{"name": "host", "default": "1.1.1.1", "options": ["x"]}]
        normalize_script_param_definitions(params)
        assert params[0]["type"] == "text"
        assert "options" not in params[0]

    def test_枚举规范化去空去重且默认须在选项内(self):
        params = [
            {
                "name": "env",
                "type": "enum",
                "options": [" prod ", "staging", "prod", "", "dev"],
                "default": "prod",
                "is_encrypted": False,
            }
        ]
        normalize_script_param_definitions(params)
        assert params[0]["options"] == ["prod", "staging", "dev"]

    def test_枚举不能加密(self):
        with pytest.raises(ValidationError):
            normalize_script_param_definitions([{"name": "env", "type": "enum", "options": ["a"], "is_encrypted": True}])

    def test_枚举无选项拒绝(self):
        with pytest.raises(ValidationError):
            normalize_script_param_definitions([{"name": "env", "type": "enum", "options": ["", "  "]}])

    def test_枚举默认值不在选项内拒绝(self):
        with pytest.raises(ValidationError):
            normalize_script_param_definitions([{"name": "env", "type": "enum", "options": ["prod"], "default": "qa"}])


class TestEnumExecutionValue:
    def test_枚举值白名单(self):
        param_def = {"name": "env", "type": "enum", "options": ["prod", "dev"]}
        assert_execution_value_allowed(param_def, "prod")
        with pytest.raises(ValidationError):
            assert_execution_value_allowed(param_def, "qa")

    def test_resolve拒绝非法枚举值(self):
        script = type("S", (), {"params": [{"name": "env", "type": "enum", "options": ["prod", "dev"], "default": "prod"}]})()
        with pytest.raises(ValidationError):
            ScriptParamsService.resolve_params(
                [{"name": "env", "value": "qa", "is_modified": True}],
                script=script,
            )

    def test_resolve接受合法枚举值(self):
        script = type("S", (), {"params": [{"name": "env", "type": "enum", "options": ["prod", "dev"], "default": "prod"}]})()
        resolved = ScriptParamsService.resolve_params(
            [{"name": "env", "value": "dev", "is_modified": True}],
            script=script,
        )
        assert resolved[0]["value"] == "dev"
