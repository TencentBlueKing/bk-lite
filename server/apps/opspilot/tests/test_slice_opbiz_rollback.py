"""opspilot-biz 切片: utils/rollback 真实测试。

被测函数=「查 spec/构建参数 → 调一次工具边界 → 解析结果/分支」。
唯一外部边界是工具对象的 invoke/ainvoke，用 AsyncMock/MagicMock 桩返回真实形态。
"""

import pydantic.root_model  # noqa

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.opspilot.metis.llm.chain.entity import RollbackConfig, ToolRollbackSpec
from apps.opspilot.utils.rollback import (
    ROLLBACK_REGISTRY,
    _extract_from_snapshot,
    execute_rollback,
    get_rollback_spec,
    take_snapshot,
)


def _make_tool(name, *, sync_result=None, async_result=None, raises=None):
    """构造一个仿 langchain Tool 的桩对象。"""
    tool = MagicMock()
    tool.name = name
    if async_result is not None or raises is not None:
        async def _ainvoke(args, config=None):
            if raises is not None:
                raise raises
            return async_result
        tool.ainvoke = AsyncMock(side_effect=_ainvoke)
    else:
        # 无 ainvoke 属性 → 走 sync invoke 分支
        del tool.ainvoke
        tool.invoke = MagicMock(return_value=sync_result)
    return tool


# ---------------------------------------------------------------------------
# get_rollback_spec 优先级
# ---------------------------------------------------------------------------


class TestGetRollbackSpec:
    def test_config_override_wins(self):
        override = ToolRollbackSpec(rollback_tool="custom", description="覆盖")
        cfg = RollbackConfig(enabled=True, overrides={"scale_deployment": override})
        spec = get_rollback_spec("scale_deployment", None, cfg)
        assert spec is override

    def test_tool_metadata_spec_instance(self):
        meta_spec = ToolRollbackSpec(rollback_tool="meta_tool")
        tool = MagicMock()
        tool.metadata = {"rollback": meta_spec}
        spec = get_rollback_spec("unknown_tool", tool, RollbackConfig())
        assert spec is meta_spec

    def test_tool_metadata_dict_built_into_spec(self):
        tool = MagicMock()
        tool.metadata = {"rollback": {"rollback_tool": "from_dict", "strategy": "auto"}}
        spec = get_rollback_spec("unknown_tool", tool, RollbackConfig())
        assert isinstance(spec, ToolRollbackSpec)
        assert spec.rollback_tool == "from_dict"
        assert spec.strategy == "auto"

    def test_registry_fallback(self):
        spec = get_rollback_spec("scale_deployment", None, RollbackConfig())
        assert spec is ROLLBACK_REGISTRY["scale_deployment"]

    def test_unknown_returns_none(self):
        assert get_rollback_spec("no_such_tool", None, RollbackConfig()) is None

    def test_metadata_not_dict_falls_through_to_registry(self):
        tool = MagicMock()
        tool.metadata = "not-a-dict"
        spec = get_rollback_spec("restart_pod", tool, RollbackConfig())
        assert spec is ROLLBACK_REGISTRY["restart_pod"]


# ---------------------------------------------------------------------------
# take_snapshot
# ---------------------------------------------------------------------------


class TestTakeSnapshot:
    async def test_no_snapshot_tool_returns_none(self):
        spec = ToolRollbackSpec(snapshot_tool=None)
        out = await take_snapshot(spec, "act", {}, [])
        assert out is None

    async def test_snapshot_tool_missing_returns_none(self):
        spec = ToolRollbackSpec(snapshot_tool="list_x")
        out = await take_snapshot(spec, "act", {"namespace": "ns"}, [_make_tool("other")])
        assert out is None

    async def test_snapshot_async_maps_args_and_returns_str(self):
        spec = ToolRollbackSpec(
            snapshot_tool="list_x",
            snapshot_args_mapping={"namespace": "namespace"},
        )
        tool = _make_tool("list_x", async_result={"spec": {"replicas": 3}})
        out = await take_snapshot(spec, "scale", {"namespace": "ns1", "extra": "ignored"}, [tool])
        # 结果被 str 化
        assert out == str({"spec": {"replicas": 3}})
        # 只映射 snapshot_args_mapping 中声明的参数
        tool.ainvoke.assert_awaited_once()
        called_args = tool.ainvoke.await_args.args[0]
        assert called_args == {"namespace": "ns1"}

    async def test_snapshot_sync_invoke_path(self):
        spec = ToolRollbackSpec(snapshot_tool="list_x", snapshot_args_mapping={})
        tool = _make_tool("list_x", sync_result="raw-snapshot-string")
        out = await take_snapshot(spec, "act", {}, [tool])
        assert out == "raw-snapshot-string"

    async def test_snapshot_exception_returns_none(self):
        spec = ToolRollbackSpec(snapshot_tool="list_x")
        tool = _make_tool("list_x", raises=RuntimeError("boom"))
        out = await take_snapshot(spec, "act", {}, [tool])
        assert out is None


# ---------------------------------------------------------------------------
# execute_rollback
# ---------------------------------------------------------------------------


class TestExecuteRollback:
    async def test_strategy_none(self):
        spec = ToolRollbackSpec(strategy="none", description="不可回滚")
        out = await execute_rollback(spec, "delete_x", {}, None, [])
        assert out["rolled_back"] is False
        assert out["strategy"] == "none"
        assert out["rollback_result"] == "不可回滚"

    async def test_prompt_without_rollback_tool_injects_context(self):
        spec = ToolRollbackSpec(strategy="prompt", rollback_tool=None, description="请手动处理")
        out = await execute_rollback(spec, "act", {}, "snapshot-data", [])
        assert out["rolled_back"] is False
        assert out["strategy"] == "prompt"
        assert "act" in out["rollback_result"]
        assert "snapshot-data" in out["rollback_result"]
        assert "请手动处理" in out["rollback_result"]

    async def test_no_rollback_tool_non_prompt(self):
        spec = ToolRollbackSpec(strategy="auto", rollback_tool=None)
        out = await execute_rollback(spec, "act", {}, None, [])
        assert out["rolled_back"] is False
        assert out["rollback_result"] == "未配置回滚工具"

    async def test_rollback_tool_not_available(self):
        spec = ToolRollbackSpec(strategy="auto", rollback_tool="scale_deployment")
        out = await execute_rollback(spec, "act", {}, None, [_make_tool("other")])
        assert out["rolled_back"] is False
        assert "不可用" in out["rollback_result"]
        assert out["rollback_tool"] == "scale_deployment"

    async def test_successful_rollback_maps_args_and_snapshot(self):
        spec = ToolRollbackSpec(
            strategy="auto",
            rollback_tool="scale_deployment",
            rollback_args_mapping={"deployment_name": "deployment_name", "namespace": "namespace"},
            rollback_snapshot_args={"replicas": "spec.replicas"},
        )
        tool = _make_tool("scale_deployment", async_result="scaled back ok")
        snapshot = '{"spec": {"replicas": 5}}'
        action_args = {"deployment_name": "web", "namespace": "ns", "replicas": 1}
        out = await execute_rollback(spec, "scale_deployment", action_args, snapshot, [tool])
        assert out["rolled_back"] is True
        assert out["rollback_result"] == "scaled back ok"
        # 参数既来自 action_args 映射，又来自 snapshot 提取
        passed = tool.ainvoke.await_args.args[0]
        assert passed == {"deployment_name": "web", "namespace": "ns", "replicas": 5}

    async def test_rollback_sync_invoke_path(self):
        spec = ToolRollbackSpec(strategy="auto", rollback_tool="rb")
        tool = _make_tool("rb", sync_result="done")
        out = await execute_rollback(spec, "act", {}, None, [tool])
        assert out["rolled_back"] is True
        assert out["rollback_result"] == "done"

    async def test_rollback_execution_failure(self):
        spec = ToolRollbackSpec(strategy="auto", rollback_tool="rb")
        tool = _make_tool("rb", raises=ValueError("nope"))
        out = await execute_rollback(spec, "act", {}, None, [tool])
        assert out["rolled_back"] is False
        assert "回滚执行失败" in out["rollback_result"]
        assert "nope" in out["rollback_result"]


# ---------------------------------------------------------------------------
# _extract_from_snapshot
# ---------------------------------------------------------------------------


class TestExtractFromSnapshot:
    def test_simple_dot_path(self):
        assert _extract_from_snapshot('{"spec": {"replicas": 3}}', "spec.replicas") == 3

    def test_list_index_path(self):
        assert _extract_from_snapshot('{"items": [{"name": "a"}, {"name": "b"}]}', "items.1.name") == "b"

    def test_missing_key_returns_none(self):
        assert _extract_from_snapshot('{"a": 1}', "a.b.c") is None

    def test_list_bad_index_returns_none(self):
        assert _extract_from_snapshot('{"items": [1]}', "items.99") is None

    def test_non_dict_traversal_returns_none(self):
        assert _extract_from_snapshot('{"a": 5}', "a.b") is None

    def test_json_repair_handles_loose_json(self):
        # json_repair 能修复非严格 JSON（尾逗号 / 单引号）
        assert _extract_from_snapshot("{'spec': {'replicas': 7,}}", "spec.replicas") == 7

    def test_unparseable_returns_none(self):
        # 完全无法解析为结构（纯字符串）→ json_repair 返回字符串，遍历首段即 None
        assert _extract_from_snapshot("totally not json at all", "spec.replicas") is None
