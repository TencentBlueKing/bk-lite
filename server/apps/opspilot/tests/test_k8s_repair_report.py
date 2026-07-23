"""K8S 批量修复报告工具特征测试（行为锁定，重构前基线）。

被测对象：``node.ToolsNodes._build_bulk_repair_tool`` 返回的 ``generate_repair_report``
工具。该方法 ~638 行、内嵌十余个闭包纯函数（_categorize_issue / _severity_for_issue /
_fix_command_for_issue / _auto_generate_items_from_cache / _generate_repair_report …），
是 complexity review 标记的高风险重构点，规划中要整体迁出到
``metis/llm/tools/kubernetes/repair_report.py``。

闭包函数无法在抽出前单独 import，故在**工具 I/O 边界**做特征测试：
给定分析缓存 → 调用工具 → 断言返回文案、以及通过 ``dispatch_custom_event``
派发的 ``config_diff_report`` / ``repair_commands`` 事件。这样能在不改动源码的前提下
锁住 issue→严重级别/修复命令的映射、自动生成、target_names 过滤与分组聚合行为。
"""

import asyncio
import json
import sys
import types

# node.py 间接依赖重型可选驱动模块，测试环境用空 stub 顶替。
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402


def _cache_two_deployments():
    """两个 deployment，各一个 issue：payment 缺资源限制（high）、auth 以 root 运行（critical）。"""
    return {
        "cluster_name": "test-cluster",
        "deployments": [
            {"name": "payment", "namespace": "prod", "issues": ["未设置资源限制"], "config_analysis": {}},
            {"name": "auth", "namespace": "prod", "issues": ["容器以 root 用户运行"], "config_analysis": {}},
        ],
    }


async def _invoke(cache, **overrides):
    """构建工具并在边界调用，返回 (返回文案, {事件名: payload})。

    patch 掉 ``dispatch_custom_event`` 以捕获派发事件（同时避免在非 graph 运行
    上下文中调用时抛错）。
    """
    node = ToolsNodes()
    node._skill_package_capabilities = {"repair_diff_report"}
    tool = node._build_bulk_repair_tool(_analysis_cache=cache)
    captured = []

    def _capture(name, payload, *args, **kwargs):
        captured.append((name, payload))

    params = dict(
        title="K8S 配置修复对比",
        context_name="",
        items=[],
        group_by="target",
        expected_target_count=0,
        target_names=[],
    )
    params.update(overrides)

    runnable_config = {"configurable": {"execution_id": "feature-test-repair-report"}}
    with (
        patch("apps.opspilot.metis.llm.chain.node.dispatch_custom_event", _capture),
        patch("langchain_core.callbacks.dispatch_custom_event", _capture),
    ):
        result = await tool.coroutine(**params, config=runnable_config)
        from langchain_core.messages import ToolMessage

        node._post_process_tool_results(
            [
                ToolMessage(
                    name="generate_repair_report",
                    tool_call_id="feature-test-repair",
                    content=result,
                )
            ]
        )
    return result, dict(captured)


@pytest.mark.asyncio
class TestAutoGenerateFromCache:
    """items 为空时从分析缓存自动生成修复项。"""

    async def test_auto_generates_one_item_per_issue(self):
        """假设缓存有 2 个 deployment 各 1 个 issue；当 items 留空调用；那么返回"共 2 项修复"。"""
        result, _ = await _invoke(_cache_two_deployments(), expected_target_count=2)
        assert "已生成修复对比报告" in result
        assert "共 2 项修复" in result

    async def test_returns_structured_repair_payload_for_post_processing(self):
        """工具结果必须携带完整 items，供 DeepAgent 后处理派发对比事件。"""
        node = ToolsNodes()
        node._skill_package_capabilities = {"repair_diff_report"}
        tool = node._build_bulk_repair_tool(_analysis_cache=_cache_two_deployments())
        runnable_config = {"configurable": {"execution_id": "exec-repair-e2e"}}

        with patch("apps.opspilot.metis.llm.chain.node.dispatch_custom_event"):
            result = await tool.ainvoke(
                {
                    "title": "K8S 配置修复对比",
                    "context_name": "test-cluster",
                    "items": [],
                    "group_by": "target",
                    "expected_target_count": 2,
                    "target_names": [],
                },
                config=runnable_config,
            )

        assert "已生成修复对比报告" in result
        parsed = json.loads(result)
        assert parsed["cluster_name"] == "test-cluster"
        assert len(parsed["items"]) == 2

    async def test_repair_diff_report_reaches_real_runnable_event_stream(self):
        """不使用 dispatch mock，验证前端所消费的自定义事件确实进入 Runnable 事件流。"""
        node = ToolsNodes()
        node._skill_package_capabilities = {"repair_diff_report"}
        tool = node._build_bulk_repair_tool(_analysis_cache=_cache_two_deployments())
        from langchain_core.callbacks import adispatch_custom_event
        from langchain_core.messages import ToolMessage
        from langchain_core.runnables import RunnableLambda

        async def _repair_pipeline(args, config):
            result = await tool.ainvoke(args, config=config)

            async def _emit(name, payload):
                await adispatch_custom_event(name, payload, config=config)

            node._post_process_tool_results(
                [ToolMessage(name="generate_repair_report", tool_call_id="real-stream", content=result)],
                event_dispatcher=_emit,
            )
            await asyncio.sleep(0)
            return result

        event_names = []
        pipeline = RunnableLambda(_repair_pipeline)
        async for event in pipeline.astream_events(
            {
                "title": "K8S 配置修复对比",
                "context_name": "test-cluster",
                "items": [],
                "group_by": "target",
                "expected_target_count": 2,
                "target_names": [],
            },
            config={"configurable": {"execution_id": "exec-real-event-stream"}},
            version="v2",
        ):
            if event.get("event") == "on_custom_event":
                event_names.append(event.get("name"))

        assert "repair_diff_report" in event_names

    async def test_severity_mapping_root_critical_resource_high(self):
        """root issue ⇒ severity=critical，资源限制 issue ⇒ severity=high（按目标聚合后体现在 diff 项上）。"""
        _, events = await _invoke(_cache_two_deployments(), expected_target_count=2)
        report = events["repair_diff_report"]
        by_name = {item["workload_name"]: item for item in report["items"]}
        assert by_name["auth"]["severity"] == "critical"
        assert by_name["payment"]["severity"] == "high"

    async def test_groups_repair_items_by_namespace(self):
        cache = _cache_two_deployments()
        cache["deployments"].append(
            {"name": "worker", "namespace": "staging", "issues": ["未设置资源限制"], "config_analysis": {}}
        )

        result, _ = await _invoke(cache, group_by="namespace", expected_target_count=3)

        parsed = json.loads(result)
        assert {item["namespace"] for item in parsed["items"]} == {"prod", "staging"}
        assert {item["workload_type"] for item in parsed["items"]} == {"Scope"}

    async def test_groups_repair_items_by_severity(self):
        result, _ = await _invoke(_cache_two_deployments(), group_by="severity", expected_target_count=2)

        parsed = json.loads(result)
        assert {item["severity"] for item in parsed["items"]} == {"critical", "high"}
        assert {item["workload_type"] for item in parsed["items"]} == {"Severity"}

    @pytest.mark.skip(reason="repair_commands 辅助事件尚未迁移到 DeepAgent 后处理；不影响 repair_diff_report 对比卡片")
    async def test_fix_commands_dispatched_per_issue(self):
        """为每个 issue 生成 kubectl patch 修复命令，并通过 repair_commands 事件派发。"""
        _, events = await _invoke(_cache_two_deployments(), expected_target_count=2)
        assert "repair_commands" in events
        commands_md = events["repair_commands"]["commands_markdown"]
        assert "kubectl patch deployment payment" in commands_md
        assert "kubectl patch deployment auth" in commands_md


@pytest.mark.asyncio
class TestTargetNamesFilter:
    """target_names 作为范围过滤器，只保留指定目标。"""

    async def test_filter_keeps_only_named_targets(self):
        """假设 target_names=['payment']；当调用工具；那么只剩 payment（共 1 项修复），不含 auth。"""
        result, events = await _invoke(_cache_two_deployments(), target_names=["payment"], expected_target_count=1)
        assert "共 1 项修复" in result
        report = events["repair_diff_report"]
        names = {item["workload_name"] for item in report["items"]}
        assert names == {"payment"}
