import json
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

from apps.opspilot.metis.llm.chain.node import (
    ToolsNodes,
    build_a2ui_report_contract,
    build_config_analysis_report_payload,
    build_config_diff_report_payload,
    build_post_tool_directives,
    build_repair_mode_choice_args,
    downgrade_config_analysis_next_step_hint,
    should_emit_config_analysis_report,
)
from apps.opspilot.metis.llm.tools.kubernetes.analysis import (
    analyze_deployment_configurations,
    build_config_analysis_next_step_hint,
)


@pytest.fixture
def settings():
    return SimpleNamespace(MIDDLEWARE=(), CACHES={})


def _make_container(
    *,
    image="nginx:1.25.3",
    has_requests=True,
    has_limits=True,
    has_liveness=True,
    has_readiness=True,
    run_as_non_root=True,
):
    resources = SimpleNamespace(
        requests={"cpu": "100m"} if has_requests else None,
        limits={"memory": "256Mi"} if has_limits else None,
    )
    security_context = (
        SimpleNamespace(run_as_non_root=run_as_non_root)
        if run_as_non_root is not None
        else None
    )
    return SimpleNamespace(
        name="main",
        image=image,
        resources=resources,
        liveness_probe=object() if has_liveness else None,
        readiness_probe=object() if has_readiness else None,
        security_context=security_context,
    )


def _make_deployment(*, name="demo", namespace="default", replicas=2, containers=None, affinity=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=namespace),
        spec=SimpleNamespace(
            replicas=replicas,
            strategy=SimpleNamespace(type="RollingUpdate"),
            selector=SimpleNamespace(match_labels={"app": name}),
            template=SimpleNamespace(
                spec=SimpleNamespace(containers=containers or [_make_container()], affinity=affinity)
            ),
        ),
    )


def _make_pdb_for(deployment_name):
    return SimpleNamespace(
        spec=SimpleNamespace(selector=SimpleNamespace(match_labels={"app": deployment_name}))
    )


def _run_config_analysis(monkeypatch, deployments, pdbs_by_namespace=None, **invoke_kwargs):
    pdbs_by_namespace = pdbs_by_namespace or {}

    class _AppsV1Api:
        def list_deployment_for_all_namespaces(self):
            return SimpleNamespace(items=deployments)

        def list_namespaced_deployment(self, namespace):
            return SimpleNamespace(items=[d for d in deployments if d.metadata.namespace == namespace])

    class _CoreV1Api:
        def list_namespaced_pod_disruption_budget(self, namespace):
            return SimpleNamespace(items=pdbs_by_namespace.get(namespace, []))

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.kubernetes.analysis.prepare_context",
        lambda config: None,
    )
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.kubernetes.analysis.get_current_cluster_name",
        lambda: "Kubernetes - 1",
    )
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.kubernetes.analysis.client.AppsV1Api",
        _AppsV1Api,
    )
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.tools.kubernetes.analysis.client.CoreV1Api",
        _CoreV1Api,
    )

    return json.loads(analyze_deployment_configurations.invoke(invoke_kwargs))


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
        "结构化配置检查报告已经通过 AG-UI" in message.content
        and "不要再用 Markdown" in message.content
        and "最终文本最多只允许一句简短说明" in message.content
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
        "通过 AG-UI 交互卡片让用户选择修复展示方式" in message.content
        and "必须主动调用 request_user_choice" in message.content
        and "不要主动调用 generate_repair_report" in message.content
        and "输出完整配置检查报告后" not in message.content
        for message in directives
        if isinstance(message, SystemMessage)
    )


def test_build_post_tool_directives_skips_expert_workflow_without_skill_capability():
    directives = build_post_tool_directives(
        [
            ToolMessage(
                name="analyze_deployment_configurations",
                tool_call_id="call-1",
                content='{"cluster_name":"Kubernetes - 1","problematic":32,"issues_detail":[{"severity":"high","issue":"未配置存活探针","count":10,"workloads":["nginx-test (default)"]}]}',
            )
        ],
        enable_config_analysis_report=False,
        enable_repair_diff_report=False,
    )

    assert directives == []


def test_build_post_tool_directives_prevents_duplicate_summary_for_healthy_scan():
    directives = build_post_tool_directives(
        [
            ToolMessage(
                name="analyze_deployment_configurations",
                tool_call_id="call-1",
                content='{"cluster_name":"Kubernetes - 1","total":9,"problematic":0,"healthy":9,"issues_detail":[]}',
            )
        ]
    )

    assert any(isinstance(message, SystemMessage) for message in directives)
    assert any(
        "结构化配置检查报告已经通过 AG-UI" in message.content
        and "如果检查结果没有问题，则直接用一句话结束" in message.content
        for message in directives
        if isinstance(message, SystemMessage)
    )


def test_build_config_analysis_next_step_hint_requests_repair_mode_choice():
    hint = build_config_analysis_next_step_hint(problematic_count=32, target_name=None)

    assert "request_user_choice" in hint
    assert "修复展示方式" in hint
    assert "generate_repair_report" in hint


def test_downgrade_config_analysis_next_step_hint_removes_repair_workflow():
    parsed = {
        "problematic": 32,
        "_next_step_hint": build_config_analysis_next_step_hint(problematic_count=32, target_name=None),
    }

    downgraded = downgrade_config_analysis_next_step_hint(parsed)

    assert "修复展示方式" not in downgraded["_next_step_hint"]
    assert "generate_repair_report" in parsed["_next_step_hint"]
    assert "不要调用 request_user_choice" in downgraded["_next_step_hint"]
    assert "不要调用 generate_repair_report" in downgraded["_next_step_hint"]


def test_basic_k8s_analysis_filters_loop_prone_followup_tools():
    node = ToolsNodes()
    node._skill_package_capabilities = set()

    filtered, blocked = node._filter_basic_k8s_analysis_loop_calls(
        [
            {"name": "analyze_deployment_configurations"},
            {"name": "kubernetes_troubleshooting_guide"},
            {"name": "request_user_choice"},
        ],
        {"deployments": [{"name": "nginx-test"}]},
    )

    assert blocked is True
    assert filtered == []


def test_expert_k8s_analysis_keeps_repair_followup_tools():
    node = ToolsNodes()
    node._skill_package_capabilities = {"config_analysis_report", "repair_diff_report"}

    tool_calls = [
        {"name": "analyze_deployment_configurations"},
        {"name": "request_user_choice"},
    ]
    filtered, blocked = node._filter_basic_k8s_analysis_loop_calls(
        tool_calls,
        {"deployments": [{"name": "nginx-test"}]},
    )

    assert blocked is False
    assert filtered == tool_calls


def test_expert_k8s_analysis_sanitizes_duplicate_markdown_report_text():
    node = ToolsNodes()
    node._skill_package_capabilities = {"config_analysis_report", "repair_diff_report"}
    response = node._sanitize_duplicate_config_analysis_text(
        response=SimpleNamespace(
            content=(
                "## 配置检查报告\n\n"
                "### High Severity\n\n"
                "### Medium Severity\n\n"
                "## 修复建议\n"
            ),
            tool_calls=[{"name": "request_user_choice", "args": {}, "id": "choice-1"}],
            id="msg-1",
        ),
        analysis_cache={"deployments": [{"name": "nginx-test"}]},
    )

    assert response.content == "配置检查报告已通过上方结构化卡片展示，请查看卡片中的统计、风险分组和建议。"
    assert response.tool_calls[0]["name"] == "request_user_choice"


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
    assert payload["a2ui"] == {
        "version": "1.0",
        "component": "config-analysis-report",
        "event_name": "config_analysis_report",
        "render_mode": "card",
        "actions": [
            {"key": "expand_issue", "label": "展开问题"},
            {"key": "request_repair_mode", "label": "选择修复展示方式"},
        ],
    }
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
            "benefit": "降低容器逃逸后直接获得宿主机 root 权限的风险，收紧运行时权限边界。",
        },
        {
            "priority": "P1",
            "action": "添加 livenessProbe 配置（建议 httpGet 方式），设置合理的 initialDelaySeconds 和 periodSeconds。",
            "target": "nginx (default)",
            "benefit": "让 Kubernetes 能自动发现并重启异常容器，缩短故障持续时间。",
        },
    ]
    assert payload["fallback_markdown"] == payload["markdown"]
    assert payload["fallback_markdown"].startswith("# 配置检查报告 - Kubernetes - 1")


def test_build_config_diff_report_payload_declares_a2ui_component_contract():
    payload = build_config_diff_report_payload(
        title="配置修复对比",
        cluster_name="Kubernetes - 1",
        items=[
            {
                "workload_name": "api",
                "workload_type": "Deployment",
                "namespace": "default",
                "severity": "high",
                "summary": "未配置存活探针",
                "before_yaml": "containers: []",
                "after_yaml": "livenessProbe: {}",
            }
        ],
    )

    assert payload["title"] == "配置修复对比"
    assert payload["cluster_name"] == "Kubernetes - 1"
    assert payload["items"][0]["workload_name"] == "api"
    assert payload["a2ui"] == {
        "version": "1.0",
        "component": "config-diff-report",
        "event_name": "config_diff_report",
        "render_mode": "card",
        "actions": [
            {"key": "open_diff", "label": "查看差异"},
            {"key": "copy_after_yaml", "label": "复制修复配置"},
        ],
    }


def test_build_user_choice_a2ui_contract_uses_same_component_protocol():
    contract = build_a2ui_report_contract(
        component="user-choice",
        event_name="user_choice_request",
        actions=[{"key": "submit_choice", "label": "提交选择"}],
    )

    assert contract == {
        "version": "1.0",
        "component": "user-choice",
        "event_name": "user_choice_request",
        "render_mode": "card",
        "actions": [{"key": "submit_choice", "label": "提交选择"}],
    }


def test_build_repair_mode_choice_args_omits_low_value_grouping_for_single_issue():
    choice_args = build_repair_mode_choice_args(
        {
            "problematic": 1,
            "issues_detail": [
                {
                    "severity": "high",
                    "issue": "未配置存活探针",
                    "count": 1,
                    "workloads": ["api (default)"],
                }
            ],
        }
    )

    assert choice_args["question"] == "请选择修复展示方式"
    assert choice_args["question_type"] == "single_select"
    assert choice_args["options"] == ["直接展示单个修复对比（推荐）"]


def test_build_repair_mode_choice_args_recommends_category_for_broad_multi_issue_scan():
    choice_args = build_repair_mode_choice_args(
        {
            "problematic": 40,
            "issues_detail": [
                {
                    "severity": "high",
                    "issue": "未配置存活探针",
                    "count": 35,
                    "workloads": ["api (default)", "worker (prod)", "scheduler (prod)"],
                },
                {
                    "severity": "medium",
                    "issue": "未配置资源限制",
                    "count": 31,
                    "workloads": ["api (default)", "worker (prod)"],
                },
                {
                    "severity": "low",
                    "issue": "使用 latest 镜像",
                    "count": 24,
                    "workloads": ["api (default)"],
                },
            ],
        }
    )

    assert choice_args["options"][0] == "按问题类别聚合（推荐：多类问题覆盖面广）"
    assert "按工作负载聚合" in choice_args["options"]
    assert "全部一次性展示" not in choice_args["options"]


def test_normalize_repair_group_by_accepts_recommended_choice_label():
    node = ToolsNodes()

    assert node._normalize_repair_group_by("按问题类别聚合（推荐：多类问题覆盖面广）") == "category"
    assert node._normalize_repair_group_by("按工作负载聚合（推荐：目标数量较少）") == "target"
    assert node._normalize_repair_group_by("直接展示单个修复对比（推荐）") == "all"


def test_should_emit_config_analysis_report_for_summary_only_result():
    parsed = {
        "cluster_name": "Kubernetes - 1",
        "problematic": 0,
        "healthy": 9,
        "total": 9,
        "issues_detail": [],
    }

    assert should_emit_config_analysis_report(parsed) is True
    assert should_emit_config_analysis_report({"cluster_name": "Kubernetes - 1", "issues_detail": []}) is False
    assert should_emit_config_analysis_report({"error": "scope_too_large"}) is False


def test_build_config_analysis_report_payload_keeps_scan_context_for_healthy_scan():
    deployments_full = [{"name": f"deploy-{i}"} for i in range(25)]
    parsed = {
        "cluster_name": "Kubernetes - 1",
        "problematic": 0,
        "healthy": 25,
        "total": 100,
        "offset": 50,
        "limit": 25,
        "has_more": True,
        "issues_detail": [],
        "_deployments_full": deployments_full,
    }

    payload = build_config_analysis_report_payload(parsed)

    assert payload["scope"] == {"cluster_name": "Kubernetes - 1"}
    assert payload["scan_range"] == {"offset": 50, "limit": 25, "has_more": True}
    assert payload["summary"] == {"total": 25, "problematic": 0, "healthy": 25}
    assert payload["severity_sections"] == []
    assert payload["recommendations"] == []
    assert "未发现明显配置问题" in payload["fallback_markdown"]
    assert "总计 25 个工作负载" in payload["fallback_markdown"]
    assert "100" not in payload["fallback_markdown"]


def test_analyze_deployment_configurations_counts_container_only_issues_consistently(monkeypatch):
    result = _run_config_analysis(
        monkeypatch,
        deployments=[
            _make_deployment(
                name="api",
                containers=[_make_container(has_liveness=False)],
                affinity=object(),
            )
        ],
        pdbs_by_namespace={"default": [_make_pdb_for("api")]},
    )

    payload = build_config_analysis_report_payload(result)

    assert result["problematic"] == 1
    assert result["healthy"] == 0
    assert result["issues_detail"] == [
        {
            "severity": "high",
            "issue": "未配置存活探针",
            "count": 1,
            "workloads": ["api (default)"],
        }
    ]
    assert payload["summary"] == {"total": 1, "problematic": 1, "healthy": 0}
    assert payload["severity_sections"][0]["issues"][0]["issue"] == "未配置存活探针"
    assert "未发现明显配置问题" not in payload["fallback_markdown"]
    assert "request_user_choice" in result["_next_step_hint"]


def test_analyze_deployment_configurations_dedupes_workload_labels_per_issue(monkeypatch):
    result = _run_config_analysis(
        monkeypatch,
        deployments=[
            _make_deployment(
                name="api",
                containers=[
                    _make_container(has_liveness=False, has_readiness=False),
                    _make_container(has_liveness=False, has_readiness=False),
                ],
                affinity=object(),
            )
        ],
        pdbs_by_namespace={"default": [_make_pdb_for("api")]},
    )

    assert result["issues_detail"] == [
        {
            "severity": "high",
            "issue": "未配置存活探针",
            "count": 1,
            "workloads": ["api (default)"],
        },
        {
            "severity": "high",
            "issue": "未配置就绪探针",
            "count": 1,
            "workloads": ["api (default)"],
        },
    ]


def test_analyze_deployment_configurations_treats_recommendation_only_workload_as_healthy(monkeypatch):
    result = _run_config_analysis(
        monkeypatch,
        deployments=[_make_deployment(name="api")],
        pdbs_by_namespace={"default": []},
    )

    payload = build_config_analysis_report_payload(result)

    assert result["problematic"] == 0
    assert result["healthy"] == 1
    assert result["issues_detail"] == []
    assert payload["summary"] == {"total": 1, "problematic": 0, "healthy": 1}
    assert payload["severity_sections"] == []
    assert payload["recommendations"] == []
    assert "未发现明显配置问题" in payload["fallback_markdown"]
    assert "不要调用 request_user_choice" in result["_next_step_hint"]
    assert "不要调用 generate_repair_report" in result["_next_step_hint"]


def test_analyze_deployment_configurations_carries_scan_scope_into_payload(monkeypatch):
    result = _run_config_analysis(
        monkeypatch,
        deployments=[_make_deployment(name="api", namespace="payments")],
        pdbs_by_namespace={"payments": [_make_pdb_for("api")]},
        namespace="payments",
        instance_name="prod-cluster",
        name="api",
    )

    payload = build_config_analysis_report_payload(result)

    assert result["scope"] == {
        "namespace": "payments",
        "instance_name": "prod-cluster",
        "name": "api",
        "target_name": "api",
    }
    assert payload["scope"] == {
        "cluster_name": "Kubernetes - 1",
        "namespace": "payments",
        "instance_name": "prod-cluster",
        "name": "api",
        "target_name": "api",
    }


def test_analyze_deployment_configurations_marks_healthy_workload_consistently(monkeypatch):
    result = _run_config_analysis(
        monkeypatch,
        deployments=[_make_deployment(name="api", affinity=object())],
        pdbs_by_namespace={"default": [_make_pdb_for("api")]},
    )

    payload = build_config_analysis_report_payload(result)

    assert result["problematic"] == 0
    assert result["healthy"] == 1
    assert result["issues_detail"] == []
    assert payload["summary"] == {"total": 1, "problematic": 0, "healthy": 1}
    assert payload["severity_sections"] == []
    assert payload["recommendations"] == []
    assert "未发现明显配置问题" in payload["fallback_markdown"]
    assert "不要调用 request_user_choice" in result["_next_step_hint"]
    assert "不要调用 generate_repair_report" in result["_next_step_hint"]


def test_analyze_deployment_configurations_reports_missing_named_deployment(monkeypatch):
    result = _run_config_analysis(
        monkeypatch,
        deployments=[_make_deployment(name="nginx-test")],
        pdbs_by_namespace={"default": []},
        namespace="default",
        name="missing",
    )

    assert result == {
        "success": False,
        "error": "deployment_not_found",
        "code": "deployment_not_found",
        "message": "未找到名为 default/missing 的 Deployment",
        "target_name": "missing",
        "namespace": "default",
        "_next_step_hint": (
            "未找到名为 default/missing 的 Deployment。"
            "请先确认名称是否正确，必要时先调用 list_kubernetes_deployments 重新查看可用 Deployment。"
        ),
    }
