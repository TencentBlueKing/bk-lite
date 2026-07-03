"""opspilot.utils.verification 执行后验证模块测试。

规格（操作类工具执行后自动验证是否生效）：
- get_verification_spec：优先级 overrides > tool.metadata > VERIFICATION_REGISTRY
- build_verify_args：按 args_mapping 从操作工具参数提取验证工具参数
- run_verification：找不到验证工具→skip；ainvoke/invoke 调用；异常重试；
  delay/retry 用 asyncio.sleep（mock 掉避免真实等待）。
只在真实外部边界处 mock（工具 ainvoke/invoke、asyncio.sleep）。
"""

import pytest

from apps.opspilot.metis.llm.chain.entity import (
    ToolVerificationSpec,
    VerificationConfig,
)
from apps.opspilot.utils import verification
from apps.opspilot.utils.verification import (
    VERIFICATION_REGISTRY,
    build_verify_args,
    get_verification_spec,
    run_verification,
)

pytestmark = pytest.mark.unit


class _FakeTool:
    def __init__(self, name, ainvoke_result=None, invoke_result=None, ainvoke_exc=None, metadata=None):
        self.name = name
        self.metadata = metadata if metadata is not None else {}
        self._ainvoke_result = ainvoke_result
        self._invoke_result = invoke_result
        self._ainvoke_exc = ainvoke_exc
        self.ainvoke_calls = []
        self.invoke_calls = []

    async def ainvoke(self, args, config=None):
        self.ainvoke_calls.append((args, config))
        if self._ainvoke_exc is not None:
            raise self._ainvoke_exc
        return self._ainvoke_result

    def invoke(self, args, config=None):
        self.invoke_calls.append((args, config))
        return self._invoke_result


class _SyncOnlyTool:
    """无 ainvoke 属性的工具，强制 run_verification 走同步 invoke 分支。"""

    def __init__(self, name, invoke_result=None):
        self.name = name
        self.metadata = {}
        self._invoke_result = invoke_result
        self.invoke_calls = []

    def invoke(self, args, config=None):
        self.invoke_calls.append((args, config))
        return self._invoke_result


# ---------------------------------------------------------------------------
# get_verification_spec 优先级
# ---------------------------------------------------------------------------


class TestGetVerificationSpec:
    def test_overrides_优先级最高(self):
        override = ToolVerificationSpec(verify_tool="custom_verify")
        config = VerificationConfig(overrides={"restart_pod": override})
        tool = _FakeTool("restart_pod", metadata={"verification": ToolVerificationSpec(verify_tool="meta_verify")})

        spec = get_verification_spec("restart_pod", tool, config)
        assert spec is override
        assert spec.verify_tool == "custom_verify"

    def test_tool_metadata_次优先_对象形态(self):
        meta_spec = ToolVerificationSpec(verify_tool="meta_verify")
        tool = _FakeTool("some_tool", metadata={"verification": meta_spec})
        config = VerificationConfig()

        spec = get_verification_spec("some_tool", tool, config)
        assert spec is meta_spec

    def test_tool_metadata_dict_形态被构造为_spec(self):
        tool = _FakeTool("some_tool", metadata={"verification": {"verify_tool": "from_dict", "delay_seconds": 2.0}})
        config = VerificationConfig()

        spec = get_verification_spec("some_tool", tool, config)
        assert isinstance(spec, ToolVerificationSpec)
        assert spec.verify_tool == "from_dict"
        assert spec.delay_seconds == 2.0

    def test_回退到全局注册表(self):
        tool = _FakeTool("restart_pod")  # metadata 为空 dict，无 verification
        config = VerificationConfig()

        spec = get_verification_spec("restart_pod", tool, config)
        assert spec is VERIFICATION_REGISTRY["restart_pod"]
        assert spec.verify_tool == "get_pod_details"

    def test_注册表无匹配返回_none(self):
        config = VerificationConfig()
        assert get_verification_spec("unknown_tool", None, config) is None

    def test_tool_为_none_时安全回退注册表(self):
        config = VerificationConfig()
        spec = get_verification_spec("scale_resource", None, config)
        assert spec.verify_tool == "get_resource_details"


# ---------------------------------------------------------------------------
# build_verify_args 参数映射
# ---------------------------------------------------------------------------


class TestBuildVerifyArgs:
    def test_按映射提取存在的参数(self):
        spec = ToolVerificationSpec(
            verify_tool="get_pod_details",
            args_mapping={"pod_name": "pod_name", "namespace": "namespace"},
        )
        action_args = {"pod_name": "web-1", "namespace": "prod", "extra": "ignored"}
        assert build_verify_args(spec, action_args) == {"pod_name": "web-1", "namespace": "prod"}

    def test_缺失的源参数被跳过(self):
        spec = ToolVerificationSpec(verify_tool="v", args_mapping={"a": "src_a", "b": "src_b"})
        assert build_verify_args(spec, {"src_a": 1}) == {"a": 1}

    def test_支持重命名映射(self):
        spec = ToolVerificationSpec(verify_tool="v", args_mapping={"target": "name"})
        assert build_verify_args(spec, {"name": "deploy-x"}) == {"target": "deploy-x"}

    def test_空映射返回空(self):
        spec = ToolVerificationSpec(verify_tool="v")
        assert build_verify_args(spec, {"a": 1}) == {}


# ---------------------------------------------------------------------------
# run_verification 主流程
# ---------------------------------------------------------------------------


class TestRunVerification:
    async def test_验证工具不可用时跳过(self):
        spec = ToolVerificationSpec(verify_tool="missing_tool")
        config = VerificationConfig()

        result = await run_verification(
            spec,
            action_tool_name="restart_pod",
            action_tool_args={},
            action_tool_result="ok",
            available_tools=[_FakeTool("other_tool")],
            config=config,
        )
        assert result["verified"] is None
        assert result["attempts"] == 0
        assert "不可用" in result["verify_result"]
        assert result["verify_tool"] == "missing_tool"

    async def test_异步验证成功返回结果_无延迟(self, mocker):
        sleep = mocker.patch("apps.opspilot.utils.verification.asyncio.sleep")
        verify_tool = _FakeTool("get_pod_details", ainvoke_result={"phase": "Running"})
        spec = ToolVerificationSpec(
            verify_tool="get_pod_details",
            args_mapping={"pod_name": "pod_name"},
            delay_seconds=0.0,
            description="验证 Pod",
        )
        config = VerificationConfig(max_verify_retries=2)

        result = await run_verification(
            spec,
            action_tool_name="restart_pod",
            action_tool_args={"pod_name": "web-1", "namespace": "prod"},
            action_tool_result="restarted",
            available_tools=[verify_tool],
            config=config,
            runnable_config={"cfg": 1},
        )

        assert result["verified"] is None  # 交给 LLM 判断
        assert result["attempts"] == 1
        assert result["description"] == "验证 Pod"
        # ainvoke 收到映射后的参数与 runnable_config
        assert verify_tool.ainvoke_calls == [({"pod_name": "web-1"}, {"cfg": 1})]
        # delay_seconds=0 时不应 sleep
        sleep.assert_not_called()

    async def test_有延迟时调用_sleep(self, mocker):
        sleep = mocker.patch("apps.opspilot.utils.verification.asyncio.sleep")
        verify_tool = _FakeTool("get_pod_details", ainvoke_result="running")
        spec = ToolVerificationSpec(verify_tool="get_pod_details", delay_seconds=5.0)
        config = VerificationConfig()

        await run_verification(
            spec, "restart_pod", {}, "ok", [verify_tool], config,
        )
        sleep.assert_any_call(5.0)

    async def test_无_ainvoke_时走同步_invoke(self, mocker):
        mocker.patch("apps.opspilot.utils.verification.asyncio.sleep")
        verify_tool = _SyncOnlyTool("get_pod_details", invoke_result="sync-result")
        spec = ToolVerificationSpec(verify_tool="get_pod_details")
        config = VerificationConfig()

        result = await run_verification(spec, "restart_pod", {}, "ok", [verify_tool], config)
        assert result["verify_result"] == "sync-result"
        assert verify_tool.invoke_calls

    async def test_非字符串结果被转为字符串(self, mocker):
        mocker.patch("apps.opspilot.utils.verification.asyncio.sleep")
        verify_tool = _FakeTool("get_pod_details", ainvoke_result={"a": 1})
        spec = ToolVerificationSpec(verify_tool="get_pod_details")
        config = VerificationConfig()

        result = await run_verification(spec, "restart_pod", {}, "ok", [verify_tool], config)
        assert result["verify_result"] == str({"a": 1})

    async def test_异常重试后返回失败结果(self, mocker):
        sleep = mocker.patch("apps.opspilot.utils.verification.asyncio.sleep")
        verify_tool = _FakeTool("get_pod_details", ainvoke_exc=RuntimeError("boom"))
        spec = ToolVerificationSpec(verify_tool="get_pod_details")
        config = VerificationConfig(max_verify_retries=3, retry_delay_seconds=2.0)

        result = await run_verification(spec, "restart_pod", {}, "ok", [verify_tool], config)

        assert result["verified"] is None
        assert result["attempts"] == 3  # 用尽重试次数
        assert "验证工具执行失败" in result["verify_result"]
        assert "boom" in result["verify_result"]
        # 3 次尝试，失败后重试间隔 sleep 调用 2 次（最后一次不再 sleep）
        retry_sleeps = [c for c in sleep.call_args_list if c.args == (2.0,)]
        assert len(retry_sleeps) == 2
        assert len(verify_tool.ainvoke_calls) == 3


class TestVerificationRegistryContents:
    def test_注册表包含核心_k8s_操作工具(self):
        for name in ["restart_pod", "scale_resource", "update_resource", "delete_resource", "create_resource"]:
            assert name in VERIFICATION_REGISTRY
            assert isinstance(VERIFICATION_REGISTRY[name], ToolVerificationSpec)

    def test_restart_pod_映射到_get_pod_details(self):
        spec = VERIFICATION_REGISTRY["restart_pod"]
        assert spec.verify_tool == "get_pod_details"
        assert spec.args_mapping == {"pod_name": "pod_name", "namespace": "namespace"}
        assert spec.delay_seconds == 5.0

    def test_模块_logger_名称(self):
        assert verification.logger.name == "opspilot"
