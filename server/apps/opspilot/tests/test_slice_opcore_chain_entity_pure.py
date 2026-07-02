"""opspilot-core 切片: metis/llm/chain/entity 纯模型/helper 真实测试。

无外部边界，全部 pydantic 模型与 normalize helper 的真实行为：
dict/对象两种 tool_call 形态归一、None 容忍、ExtraConfig 别名与 extra=allow、
typed_extra_config 视图、各配置默认值与字段约束。
"""

import pydantic.root_model  # noqa

import pytest

from apps.opspilot.metis.llm.chain.entity import (
    BasicLLMRequest,
    ExtraConfig,
    NormalizedToolCall,
    RollbackConfig,
    ToolRollbackSpec,
    VerificationConfig,
    normalize_tool_call,
    normalize_tool_calls,
)

pytestmark = pytest.mark.unit


class _ObjToolCall:
    def __init__(self, name=None, id=None, args=None):
        self.name = name
        self.id = id
        self.args = args


class TestNormalizeToolCall:
    def test_dict_form(self):
        n = normalize_tool_call({"name": "scale", "id": "c1", "args": {"x": 1}})
        assert isinstance(n, NormalizedToolCall)
        assert (n.name, n.id, n.args) == ("scale", "c1", {"x": 1})
        # raw 原样保留
        assert n.raw == {"name": "scale", "id": "c1", "args": {"x": 1}}

    def test_dict_missing_keys_default_empty(self):
        n = normalize_tool_call({})
        assert n.name == "" and n.id == "" and n.args == {}

    def test_dict_none_values_coerced(self):
        # None 值经 `or` 回退到空
        n = normalize_tool_call({"name": None, "id": None, "args": None})
        assert n.name == "" and n.id == "" and n.args == {}

    def test_object_form(self):
        n = normalize_tool_call(_ObjToolCall(name="restart", id="c2", args={"k": "v"}))
        assert (n.name, n.id, n.args) == ("restart", "c2", {"k": "v"})

    def test_object_missing_attrs_default(self):
        n = normalize_tool_call(_ObjToolCall())
        assert n.name == "" and n.id == "" and n.args == {}

    def test_normalize_list_and_none(self):
        out = normalize_tool_calls([{"name": "a"}, _ObjToolCall(name="b")])
        assert [x.name for x in out] == ["a", "b"]
        assert normalize_tool_calls(None) == []


class TestExtraConfig:
    def test_from_raw_none_yields_defaults(self):
        c = ExtraConfig.from_raw(None)
        assert c.execution_id is None
        assert c.require_choice_before_tools is False
        assert c.multi_instance_options == []

    def test_known_fields_typed(self):
        c = ExtraConfig.from_raw({"execution_id": "e1", "thread_id": "t1", "show_think": True})
        assert c.execution_id == "e1"
        assert c.thread_id == "t1"
        assert c.show_think is True

    def test_unknown_keys_tolerated(self):
        c = ExtraConfig.from_raw({"some_custom_key": 123})
        # extra=allow 保留未知键
        assert c.model_dump().get("some_custom_key") == 123

    def test_underscore_aliases(self):
        c = ExtraConfig.from_raw({
            "_require_choice_before_tools": True,
            "_multi_instance_options": [{"id": 1}],
        })
        assert c.require_choice_before_tools is True
        assert c.multi_instance_options == [{"id": 1}]


class TestBasicLLMRequest:
    def test_defaults(self):
        req = BasicLLMRequest()
        assert req.model == "gpt-4o"
        assert req.protocol_type == "openai"
        assert req.max_steps == 50
        assert req.compaction_enabled is True
        # 嵌套配置默认实例
        assert isinstance(req.rollback_config, RollbackConfig)
        assert req.rollback_config.enabled is False

    def test_typed_extra_config_view(self):
        req = BasicLLMRequest(extra_config={"execution_id": "abc", "instance_id": 7})
        view = req.typed_extra_config()
        assert isinstance(view, ExtraConfig)
        assert view.execution_id == "abc"
        assert view.instance_id == 7

    def test_typed_extra_config_empty(self):
        req = BasicLLMRequest(extra_config={})
        assert req.typed_extra_config().execution_id is None


class TestConfigModels:
    def test_rollback_spec_strategy_default_prompt(self):
        spec = ToolRollbackSpec()
        assert spec.strategy == "prompt"
        assert spec.snapshot_tool is None
        assert spec.snapshot_args_mapping == {}

    def test_verification_config_defaults(self):
        v = VerificationConfig()
        assert v.enabled is False
        assert v.inject_failure_context is True
        assert v.max_verify_retries == 1
        assert v.retry_delay_seconds == 5.0

    def test_rollback_config_overrides_typed(self):
        cfg = RollbackConfig(overrides={"scale_deployment": ToolRollbackSpec(strategy="auto")})
        assert cfg.overrides["scale_deployment"].strategy == "auto"
        assert cfg.auto_rollback_on_verify_fail is True
