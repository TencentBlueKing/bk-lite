"""Renderer registry 单元测试。

锁定行为:
- RENDERER_REGISTRY 必须按 capability 名查表
- 渲染器对无效输入返回 None(dispatcher 据此跳过)
- 模块加载时已注册 config_analysis_report / repair_diff_report
- 不在白名单里的 capability 名不会命中任何渲染器
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from apps.opspilot.metis.llm.chain.k8s_report_tools import (
    RENDERER_REGISTRY,
    render_config_analysis_report,
    render_repair_diff_report,
)


pytestmark = pytest.mark.unit


def test_registry_contains_expected_capabilities():
    """模块加载时,config_analysis_report 和 repair_diff_report 必须已注册。"""
    assert "config_analysis_report" in RENDERER_REGISTRY
    assert "repair_diff_report" in RENDERER_REGISTRY


def test_registry_unknown_capability_returns_none():
    """未注册的 capability 名查不到任何渲染器,调用方应跳过。"""
    assert RENDERER_REGISTRY.get("nonexistent_capability") is None
    assert RENDERER_REGISTRY.get("config_analysis_reports") is None  # 注意复数


def test_render_config_analysis_report_returns_payload_for_valid_parsed():
    """analyze_deployment_configurations 返回的典型 issues_detail JSON 应产出非空 payload。"""
    parsed: Dict[str, Any] = {
        "cluster_name": "Kubernetes - 1",
        "total": 9,
        "problematic": 9,
        "issues_detail": [
            {
                "severity": "high",
                "issue": "未配置存活探针",
                "count": 7,
                "workloads": ["admin-panel (production)", "api-gateway (production)"],
            }
        ],
    }
    package = {"name": "kubernetes-specialist", "id": 21}
    payload = render_config_analysis_report(parsed, package)

    assert payload is not None
    assert payload["title"].startswith("配置检查报告")
    assert payload["cluster_name"] == "Kubernetes - 1"
    assert "severity_sections" in payload
    assert payload["severity_sections"][0]["severity"] == "high"
    # package 信息可用于 a2ui 契约(扩展时用,目前只断言不报错)
    assert payload is not None


def test_render_config_analysis_report_returns_none_for_invalid_input():
    """无效输入(没有 issues_detail 且无 total/problematic)必须返回 None。"""
    # 没有 issues_detail,没有统计字段
    assert render_config_analysis_report({"cluster_name": "x"}, {}) is None
    # 不是 dict
    assert render_config_analysis_report("not a dict", {}) is None
    assert render_config_analysis_report(None, {}) is None
    # error 字段
    assert render_config_analysis_report({"error": "scope_too_large"}, {}) is None


def test_render_repair_diff_report_returns_payload_for_items():
    """items 列表(或带 items 键的 dict)应产出 diff payload。"""
    items = [
        {
            "workload_name": "admin-panel",
            "workload_type": "Deployment",
            "namespace": "production",
            "severity": "high",
            "summary": "缺少资源限制 | 使用latest标签",
            "before_yaml": "replicas: 1\nimage: nginx:latest",
            "after_yaml": "replicas: 2\nimage: nginx:1.25.3",
        }
    ]
    package = {"name": "kubernetes-specialist", "id": 21}
    payload = render_repair_diff_report(items, package)

    assert payload is not None
    assert payload["title"].startswith("修复对比")
    assert "items" in payload
    assert len(payload["items"]) == 1
    assert payload["items"][0]["workload_name"] == "admin-panel"


def test_render_repair_diff_report_accepts_dict_with_items_key():
    """调用方也可以传 {'items': [...], 'cluster_name': 'X', 'title': 'Y'},renderer 抽出 items。"""
    parsed = {
        "title": "K8S 工作负载配置修复对比",
        "cluster_name": "Kubernetes - 1",
        "items": [
            {
                "workload_name": "api-gateway",
                "workload_type": "Deployment",
                "namespace": "production",
                "severity": "warning",
                "summary": "镜像 latest 标签",
                "before_yaml": "image: nginx:latest",
                "after_yaml": "image: nginx:1.25.3",
            }
        ],
    }
    payload = render_repair_diff_report(parsed, {})

    assert payload is not None
    assert payload["title"] == "K8S 工作负载配置修复对比"
    assert payload["cluster_name"] == "Kubernetes - 1"
    assert len(payload["items"]) == 1


def test_render_repair_diff_report_returns_none_for_empty_items():
    """空 items 列表应返回 None(没有 diff 就不发卡)。"""
    assert render_repair_diff_report([], {}) is None
    assert render_repair_diff_report(None, {}) is None
    assert render_repair_diff_report("not a list", {}) is None
    assert render_repair_diff_report({"items": []}, {}) is None


def test_merge_analysis_results_concatenates_issues_detail():
    """LLM 分多次调分析工具时,issues_detail 必须串接成一份,而不是各发各的卡。"""
    from apps.opspilot.metis.llm.chain.k8s_report_tools import merge_analysis_results

    r1 = {
        "cluster_name": "Kubernetes - 1",
        "total": 9,
        "problematic": 9,
        "issues_detail": [
            {"severity": "high", "issue": "缺探针", "count": 7, "workloads": ["admin-panel"]},
        ],
    }
    r2 = {
        "cluster_name": "Kubernetes - 1",
        "total": 10,
        "problematic": 10,
        "issues_detail": [
            {"severity": "medium", "issue": "latest 标签", "count": 5, "workloads": ["foo"]},
        ],
    }
    merged = merge_analysis_results([r1, r2])

    assert merged["total"] == 19
    assert merged["problematic"] == 19
    assert merged["cluster_name"] == "Kubernetes - 1"
    assert len(merged["issues_detail"]) == 2
    severities = {item["severity"] for item in merged["issues_detail"]}
    assert severities == {"high", "medium"}


def test_merge_analysis_results_dedup_same_issue_across_calls():
    """多次调分析时,同一 (severity, issue) 必须合并成一行(否则前端同 issue 出 N 行)。

    用户反馈:7 个 namespace 的"未配置存活探针"被列成 3~4 行重复。
    """
    from apps.opspilot.metis.llm.chain.k8s_report_tools import merge_analysis_results

    r1 = {
        "cluster_name": "Kubernetes - 1",
        "issues_detail": [
            {"severity": "high", "issue": "未配置存活探针", "count": 7,
             "workloads": ["admin-panel (production)", "api-gateway (production)", "frontend (production)"]},
        ],
    }
    r2 = {
        "cluster_name": "Kubernetes - 1",
        "issues_detail": [
            {"severity": "high", "issue": "未配置存活探针", "count": 9,
             "workloads": ["cronjob-worker (staging)", "debug-tool (staging)"]},
        ],
    }
    r3 = {
        "cluster_name": "Kubernetes - 1",
        "issues_detail": [
            {"severity": "high", "issue": "未配置存活探针", "count": 1,
             "workloads": ["frontend (production)"]},  # 重复,应去重
            {"severity": "medium", "issue": "latest 标签", "count": 4, "workloads": ["a"]},
        ],
    }
    merged = merge_analysis_results([r1, r2, r3])

    # 同 issue 合并成 1 行
    probe = next(i for i in merged["issues_detail"] if i["issue"] == "未配置存活探针")
    assert probe["count"] == 7 + 9 + 1
    # workloads 去重(frontend 出现 2 次,只留 1 个)
    assert probe["workloads"].count("frontend (production)") == 1
    assert set(probe["workloads"]) == {
        "admin-panel (production)", "api-gateway (production)", "frontend (production)",
        "cronjob-worker (staging)", "debug-tool (staging)",
    }
    # 不同 issue 仍然独立列出
    assert sum(1 for i in merged["issues_detail"] if i["issue"] == "未配置存活探针") == 1
    assert any(i["issue"] == "latest 标签" for i in merged["issues_detail"])


def test_merge_analysis_results_dedup_keeps_order_by_first_appearance():
    """去重不重排:同 issue 在合并后保留首次出现的位置。"""
    from apps.opspilot.metis.llm.chain.k8s_report_tools import merge_analysis_results

    r1 = {"issues_detail": [{"severity": "high", "issue": "A", "count": 1, "workloads": []}]}
    r2 = {"issues_detail": [{"severity": "high", "issue": "B", "count": 1, "workloads": []}]}
    r3 = {"issues_detail": [{"severity": "high", "issue": "A", "count": 1, "workloads": []}]}  # 重复
    r4 = {"issues_detail": [{"severity": "medium", "issue": "C", "count": 1, "workloads": []}]}

    merged = merge_analysis_results([r1, r2, r3, r4])
    issue_order = [i["issue"] for i in merged["issues_detail"]]
    assert issue_order == ["A", "B", "C"]  # A 不重复,顺序保留


def test_merge_analysis_results_handles_different_clusters():
    """多次扫描跨集群时,cluster_name 收不到唯一值,改用 cluster_names 列表。"""
    from apps.opspilot.metis.llm.chain.k8s_report_tools import merge_analysis_results

    r1 = {"cluster_name": "cluster-a", "total": 5, "issues_detail": [{"severity": "high", "issue": "x", "count": 1, "workloads": []}]}
    r2 = {"cluster_name": "cluster-b", "total": 3, "issues_detail": [{"severity": "low", "issue": "y", "count": 1, "workloads": []}]}
    merged = merge_analysis_results([r1, r2])

    # 跨多集群时,把 cluster_name 删了,改用 cluster_names 列表
    assert "cluster_name" not in merged
    assert merged["cluster_names"] == ["cluster-a", "cluster-b"]
    assert merged["total"] == 8


def test_merge_analysis_results_single_passthrough():
    """只有一份结果时,原样返回(不要无谓深拷贝或重组)。"""
    from apps.opspilot.metis.llm.chain.k8s_report_tools import merge_analysis_results

    r1 = {"cluster_name": "x", "total": 1, "issues_detail": [{"severity": "high", "issue": "i", "count": 1, "workloads": []}]}
    merged = merge_analysis_results([r1])

    # 同一对象,不是拷贝(节省分配;但不强求,只要字段一致即可)
    assert merged["total"] == 1
    assert merged["issues_detail"][0]["issue"] == "i"


def test_merge_analysis_results_empty_list_returns_empty():
    """空列表边界,不应抛异常。"""
    from apps.opspilot.metis.llm.chain.k8s_report_tools import merge_analysis_results

    assert merge_analysis_results([]) == {}
    # 全是非 dict 也安全
    assert merge_analysis_results([None, "x", 1]) == {}
