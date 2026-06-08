import sys
import types
from types import SimpleNamespace

import pytest
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
setattr(_falkordb, "Graph", type("Graph", (), {}))
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
setattr(_falkordb_asyncio, "FalkorDB", type("FalkorDB", (), {}))
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from langchain_core.messages import SystemMessage, ToolMessage

from apps.opspilot.metis.llm.chain.node import build_post_tool_directives
from apps.opspilot.metis.llm.tools.kubernetes.analysis import build_config_analysis_next_step_hint


@pytest.fixture
def settings():
    return SimpleNamespace(MIDDLEWARE=(), CACHES={})


def test_build_post_tool_directives_prevents_duplicate_config_summary_and_report():
    directives = build_post_tool_directives(
        [
            ToolMessage(
                name="analyze_deployment_configurations",
                tool_call_id="call-1",
                content='{"cluster_name":"Kubernetes - 1","problematic":32,"issues_detail":[{"severity":"high","issue":"未配置存活探针","count":10,"workloads":["nginx-test (default)"]}]}',
            )
        ]
    )

    assert any(isinstance(message, SystemMessage) for message in directives)
    assert any(
        "不要同时输出“问题摘要”和“配置问题报告”两个重复板块" in message.content
        and "优先保留详细问题报告" in message.content
        for message in directives
        if isinstance(message, SystemMessage)
    )


def test_build_post_tool_directives_requests_repair_mode_choice_after_problem_report():
    directives = build_post_tool_directives(
        [
            ToolMessage(
                name="analyze_deployment_configurations",
                tool_call_id="call-1",
                content='{"cluster_name":"Kubernetes - 1","problematic":32,"issues_detail":[{"severity":"high","issue":"未配置存活探针","count":10,"workloads":["nginx-test (default)"]}]}',
            )
        ]
    )

    assert any(
        "输出完整配置检查报告后" in message.content
        and "必须主动调用 request_user_choice" in message.content
        and "不要主动调用 generate_repair_report" in message.content
        for message in directives
        if isinstance(message, SystemMessage)
    )


def test_build_config_analysis_next_step_hint_requests_repair_mode_choice():
    hint = build_config_analysis_next_step_hint(problematic_count=32, target_name=None)

    assert "request_user_choice" in hint
    assert "修复展示方式" in hint
    assert "generate_repair_report" in hint
