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

from apps.opspilot.metis.llm.chain.node import build_config_analysis_report_payload, build_post_tool_directives
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


def test_build_config_analysis_report_payload_structures_k8s_report():
    parsed = {
        "cluster_name": "Kubernetes - 1",
        "problematic": 2,
        "healthy": 7,
        "total": 9,
        "issues_detail": [
            {
                "severity": "critical",
                "issue": "容器以 root 运行",
                "count": 1,
                "workloads": ["api (default)"],
            },
            {
                "severity": "high",
                "issue": "未配置存活探针",
                "count": 3,
                "workloads": ["nginx (default)", "worker (default)"],
            },
        ],
    }

    payload = build_config_analysis_report_payload(parsed)

    assert payload["title"] == "配置检查报告 - Kubernetes - 1"
    assert payload["cluster_name"] == "Kubernetes - 1"
    assert payload["summary"] == {"total": 9, "problematic": 2, "healthy": 7}
    assert [section["severity"] for section in payload["severity_sections"]] == ["critical", "high"]
    assert payload["severity_sections"][0]["issues"][0]["issue"] == "容器以 root 运行"
    assert payload["severity_sections"][0]["issues"][0]["risk"] == (
        "容器以 root 用户运行，容器逃逸后攻击者将获得宿主机 root 权限，安全风险极高。"
    )
    assert payload["severity_sections"][1]["issues"][0]["issue"] == "未配置存活探针"
    assert payload["severity_sections"][1]["issues"][0]["risk"] == (
        "无存活探针时 Kubernetes 无法自动检测和重启不健康的容器，故障容器将持续运行。"
    )
    assert payload["recommendations"] == [
        {
            "priority": "P0",
            "action": "配置 securityContext.runAsNonRoot: true 和 runAsUser: 1000，禁止容器以 root 运行。",
            "target": "api (default)",
            "benefit": "容器以 root 用户运行，容器逃逸后攻击者将获得宿主机 root 权限，安全风险极高。",
        },
        {
            "priority": "P1",
            "action": "添加 livenessProbe 配置（建议 httpGet 方式），设置合理的 initialDelaySeconds 和 periodSeconds。",
            "target": "nginx (default)",
            "benefit": "无存活探针时 Kubernetes 无法自动检测和重启不健康的容器，故障容器将持续运行。",
        },
    ]
    assert payload["fallback_markdown"] == payload["markdown"]
    assert payload["fallback_markdown"].startswith("# 配置检查报告 - Kubernetes - 1")
