"""端到端场景验证：使用 gpt-4o 调用数据采集 agent，验证 incident evidence package 输出。

运行方式（使用真实数据库，非 test DB）：
    D:\\app\\venv\\bkliteserver\\Scripts\\python.exe apps/opspilot/tests/test_k8s_scenario_e2e.py

需要：
    1. 数据库中存在 name 包含 'gpt-4o' 的 LLMModel
    2. D:\\app\\github\\bk-lite\\server\\apps\\opspilot\\tests\\k8s_config 可连通真实集群
"""

import json
import logging
import os
import sys
import traceback
from pathlib import Path

import yaml
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

# ---------------------------------------------------------------------------
# Django setup（直接使用真实 DB）
# ---------------------------------------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # server/

import django  # noqa: E402

django.setup()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("opspilot.tests.k8s_scenario_e2e")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

K8S_CONFIG_PATH = Path(__file__).parent / "k8s_config"
CHECK_PROMPT_PATH = Path(__file__).resolve().parents[1] / "management" / "chatflow_data" / "k8s" / "check.txt"

_BASELINE = None


def _load_kubeconfig_data() -> str:
    return K8S_CONFIG_PATH.read_text(encoding="utf-8")


def _load_check_prompt() -> str:
    return CHECK_PROMPT_PATH.read_text(encoding="utf-8")


def _get_gpt4o_model():
    from apps.opspilot.models import LLMModel

    model = LLMModel.objects.filter(name__icontains="gpt-4o", enabled=True).first()
    if not model:
        logger.error("数据库中未找到 enabled=True 且 name 包含 'gpt-4o' 的 LLMModel")
        all_models = list(LLMModel.objects.values_list("id", "name", "enabled")[:20])
        logger.info("数据库中现有模型（前 20）: %s", all_models)
        sys.exit(1)
    return model


def _get_skill_tool_id() -> int:
    from apps.opspilot.models import SkillTools

    st = SkillTools.objects.filter(name="kubernetes_data_collection").first()
    if not st:
        logger.error("数据库中未找到 kubernetes_data_collection SkillTools 记录")
        sys.exit(1)
    return st.id


def _build_invoke_params(llm_model, user_message: str, skill_tool_id: int) -> dict:
    kubeconfig_data = _load_kubeconfig_data()
    check_prompt = _load_check_prompt()

    return {
        "llm_model": llm_model.id,
        "user_message": user_message,
        "skill_prompt": check_prompt,
        "temperature": 0.1,
        "user_id": "scenario-tester",
        "chat_history": [],
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "skill_type": 1,  # BASIC_TOOL 配置值，运行时统一进入 DeepAgent
        "locale": "zh-Hans",
        "tools": [{"id": skill_tool_id, "name": "kubernetes_data_collection", "kwargs": [{"key": "kubeconfig_data", "value": kubeconfig_data}]}],
        "show_think": False,
    }


def _load_k8s_apis():
    from apps.opspilot.metis.llm.tools.kubernetes.utils import _preprocess_kubeconfig

    kubeconfig_data = _load_kubeconfig_data()
    processed = _preprocess_kubeconfig(kubeconfig_data)
    kubeconfig_dict = yaml.safe_load(processed)
    k8s_config.load_kube_config_from_dict(kubeconfig_dict)
    return k8s_client.CoreV1Api(), k8s_client.AppsV1Api()


def _find_crashloop_pod(core_v1):
    for pod in core_v1.list_pod_for_all_namespaces().items:
        statuses = pod.status.container_statuses or []
        for status in statuses:
            waiting = getattr(status.state, "waiting", None)
            if waiting and waiting.reason == "CrashLoopBackOff":
                return {
                    "namespace": pod.metadata.namespace,
                    "pod": pod.metadata.name,
                    "container": status.name,
                    "node": pod.spec.node_name,
                }
    return None


def _find_pending_pod(core_v1):
    for pod in core_v1.list_pod_for_all_namespaces(field_selector="status.phase=Pending").items:
        return {
            "namespace": pod.metadata.namespace,
            "pod": pod.metadata.name,
            "container": (pod.spec.containers[0].name if pod.spec.containers else None),
            "node": pod.spec.node_name,
        }
    return None


def _find_service_baseline(core_v1, apps_v1):
    svc = core_v1.read_namespaced_service("nginx-v1-25", "nginx")
    deploy = apps_v1.read_namespaced_deployment("nginx-v1-25", "nginx")
    selector = ",".join([f"{k}={v}" for k, v in (svc.spec.selector or {}).items()])
    pods = core_v1.list_namespaced_pod("nginx", label_selector=selector).items
    pod = pods[0] if pods else None
    return {
        "namespace": "nginx",
        "service": svc.metadata.name,
        "deployment": deploy.metadata.name,
        "pod": pod.metadata.name if pod else None,
        "container": (pod.spec.containers[0].name if pod and pod.spec.containers else None),
        "node": pod.spec.node_name if pod else None,
    }


def _find_multi_revision_deployment(apps_v1):
    for deploy in apps_v1.list_deployment_for_all_namespaces().items:
        selector = ",".join([f"{k}={v}" for k, v in (deploy.spec.selector.match_labels or {}).items()])
        rs_list = apps_v1.list_namespaced_replica_set(deploy.metadata.namespace, label_selector=selector).items
        revisions = []
        for rs in rs_list:
            annotations = rs.metadata.annotations or {}
            revision = annotations.get("deployment.kubernetes.io/revision")
            if revision:
                revisions.append(int(revision))
        if len(set(revisions)) >= 2:
            return {
                "namespace": deploy.metadata.namespace,
                "deployment": deploy.metadata.name,
                "current_revision": max(revisions),
                "revision_count": len(set(revisions)),
            }
    return None


def _get_baseline():
    global _BASELINE
    if _BASELINE is not None:
        return _BASELINE

    core_v1, apps_v1 = _load_k8s_apis()
    crashloop = _find_crashloop_pod(core_v1)
    pending = _find_pending_pod(core_v1)
    service = _find_service_baseline(core_v1, apps_v1)
    deployment = _find_multi_revision_deployment(apps_v1)

    if not crashloop:
        logger.error("集群中未找到可用于 4.1 的 CrashLoopBackOff Pod")
        sys.exit(1)
    if not service.get("pod"):
        logger.error("集群中未找到 nginx-v1-25 对应 Pod，无法执行 4.4/4.5 强断言")
        sys.exit(1)
    if not deployment:
        logger.error("集群中未找到具备 2 个以上 revision 的 Deployment，无法执行 4.5 强断言")
        sys.exit(1)

    _BASELINE = {
        "crashloop": crashloop,
        "pending": pending,
        "service": service,
        "node": {"node": crashloop["node"]},
        "deployment": deployment,
    }
    return _BASELINE


def _make_alert(*, alert_id, title, message, severity, labels, summary):
    return json.dumps(
        {
            "source": "prometheus-alertmanager",
            "alert_id": alert_id,
            "title": title,
            "message": message,
            "severity": severity,
            "status": "firing",
            "firing_time": "2026-04-29T10:00:00Z",
            "labels": labels,
            "annotations": {"summary": summary},
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_TOP_KEYS = {
    "schema_version",
    "alert",
    "target",
    "resource_snapshot",
    "events_timeline",
    "pod_logs",
    "missing_data",
    "ready_for_analysis",
}


def _validate_evidence_package(raw_message: str, scenario_name: str) -> dict:
    content = raw_message.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        content = "\n".join(lines).strip()

    try:
        pkg = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("[%s] FAIL: 返回内容不是合法 JSON: %s\n前 2000 字符:\n%s", scenario_name, e, raw_message[:2000])
        return None

    # Support wrapped format: {"incident_evidence_package": {...}}
    if "incident_evidence_package" in pkg and len(pkg) == 1:
        pkg = pkg["incident_evidence_package"]

    missing_keys = _REQUIRED_TOP_KEYS - set(pkg.keys())
    if missing_keys:
        logger.error("[%s] FAIL: evidence package 缺少顶层字段: %s", scenario_name, missing_keys)
        logger.error("[%s] 实际返回 keys: %s", scenario_name, list(pkg.keys()))
        return None

    if pkg.get("schema_version") != "1.0":
        logger.warning("[%s] schema_version=%s (期望 1.0)", scenario_name, pkg.get("schema_version"))

    target = pkg.get("target", {})
    if isinstance(target, dict):
        logger.info(
            "[%s] target: resolved=%s, type=%s, name=%s, namespace=%s",
            scenario_name,
            target.get("resolved"),
            target.get("resource_type"),
            target.get("resource_name"),
            target.get("namespace"),
        )

    logger.info("[%s] ready_for_analysis=%s, missing_data=%s", scenario_name, pkg.get("ready_for_analysis"), pkg.get("missing_data"))

    return pkg


def _assert_block_success(pkg, block_name, scenario_name):
    block = pkg.get(block_name) or {}
    status = block.get("status")
    assert status == "success", f"[{scenario_name}] {block_name}.status 应为 success，实际: {status}; block={block}"
    return block.get("data")


def _assert_non_empty_text(value, field_name, scenario_name):
    assert isinstance(value, str) and value.strip(), f"[{scenario_name}] {field_name} 应为非空字符串"


def _assert_scenario_content(pkg, scenario):
    name = scenario["name"]
    baseline = _get_baseline()
    target = pkg.get("target", {})

    assert pkg.get("schema_version") == "1.0", f"[{name}] schema_version 异常"
    assert pkg.get("ready_for_analysis") is True, f"[{name}] ready_for_analysis 应为 True"
    assert target.get("resolved") is True, f"[{name}] target.resolved 应为 True"
    assert target.get("resource_type") == scenario["expected_type"], f"[{name}] target.resource_type 异常"

    if name == "4.1 Pod CrashLoop":
        pod = baseline["crashloop"]
        assert target.get("namespace") == pod["namespace"]
        assert target.get("resource_name") == pod["pod"]
        resource = _assert_block_success(pkg, "resource_snapshot", name)
        assert resource.get("name") == pod["pod"]
        assert resource.get("namespace") == pod["namespace"]
        assert resource.get("status", {}).get("phase") == "Running"
        waiting_reason = ((((resource.get("status") or {}).get("containerStatuses") or [{}])[0].get("state") or {}).get("waiting") or {}).get(
            "reason"
        )
        assert waiting_reason == "CrashLoopBackOff", f"[{name}] waiting.reason 应为 CrashLoopBackOff，实际: {waiting_reason}"
        events = _assert_block_success(pkg, "events_timeline", name)
        assert events.get("resource_name") == pod["pod"]
        logs = _assert_block_success(pkg, "pod_logs", name)
        _assert_non_empty_text(logs.get("current", {}).get("content"), "pod_logs.current.content", name)
        _assert_non_empty_text(logs.get("previous", {}).get("content"), "pod_logs.previous.content", name)
        assert "RuntimeError: synthetic startup failure" in logs.get("previous", {}).get("content", "")
        node_ctx = _assert_block_success(pkg, "node_context", name)
        assert node_ctx.get("node_name") == pod["node"]

    elif name == "4.2 Pod Pending":
        pod = baseline["pending"]
        assert pod is not None, f"[{name}] baseline pending pod 不应为空"
        assert target.get("namespace") == pod["namespace"]
        assert target.get("resource_name") == pod["pod"]
        resource = _assert_block_success(pkg, "resource_snapshot", name)
        assert resource.get("name") == pod["pod"]
        assert resource.get("status", {}).get("phase") == "Pending"
        _assert_block_success(pkg, "events_timeline", name)

    elif name == "4.3 Node Alert":
        node = baseline["node"]
        assert target.get("resource_name") == node["node"]
        resource = _assert_block_success(pkg, "resource_snapshot", name)
        assert resource.get("name") == node["node"]
        node_ctx = _assert_block_success(pkg, "node_context", name)
        assert node_ctx.get("node_name") == node["node"]
        assert node_ctx.get("health_status") in {"healthy", "warning", "critical"}
        assert isinstance(node_ctx.get("conditions"), list) and node_ctx.get("conditions")

    elif name == "4.4 Service Abnormal":
        service = baseline["service"]
        assert target.get("namespace") == service["namespace"]
        assert target.get("resource_name") == service["service"]
        resource = _assert_block_success(pkg, "resource_snapshot", name)
        assert resource.get("name") == service["service"]
        assert resource.get("namespace") == service["namespace"]
        topology = _assert_block_success(pkg, "service_topology", name)
        assert topology.get("service_name") == service["service"]
        assert topology.get("chain", {}).get("service", {}).get("exists") is True
        assert topology.get("chain", {}).get("endpoints", {}).get("ready_count", 0) >= 1
        assert topology.get("chain", {}).get("pods", {}).get("count", 0) >= 1

    elif name == "4.5 Post-Deployment Abnormal":
        deploy = baseline["deployment"]
        assert target.get("namespace") == deploy["namespace"]
        assert target.get("resource_name") == deploy["deployment"]
        resource = _assert_block_success(pkg, "resource_snapshot", name)
        assert resource.get("name") == deploy["deployment"]
        assert resource.get("namespace") == deploy["namespace"]
        events = _assert_block_success(pkg, "events_timeline", name)
        assert events.get("resource_name") == deploy["deployment"]
        change = _assert_block_success(pkg, "change_context", name)
        history = change.get("deployment_revision_history") or {}
        assert history.get("deployment_name") == deploy["deployment"]
        assert history.get("total_revisions", 0) >= 2
        diff = change.get("revision_diff")
        assert diff is not None, f"[{name}] revision_diff 不应为空"
        assert diff.get("has_changes") is True or diff.get("differences_count", 0) >= 0


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _build_scenarios():
    baseline = _get_baseline()

    crashloop = baseline["crashloop"]
    pending = baseline["pending"]
    service = baseline["service"]
    node = baseline["node"]
    deployment = baseline["deployment"]

    scenarios = [
        {
            "name": "4.1 Pod CrashLoop",
            "expected_type": "pod",
            "mode": "assert",
            "alert": _make_alert(
                alert_id="alert-crashloop-real-001",
                title="KubePodCrashLooping",
                message="Pod is restarting frequently, possible CrashLoopBackOff",
                severity="critical",
                labels={
                    "cluster": "cluster1",
                    "namespace": crashloop["namespace"],
                    "pod": crashloop["pod"],
                    "container": crashloop["container"],
                    "node": crashloop["node"],
                },
                summary=f"Pod {crashloop['pod']} is in CrashLoopBackOff",
            ),
        },
        {
            "name": "4.2 Pod Pending",
            "expected_type": "pod",
            "mode": "assert" if pending else "skip",
            "skip_reason": "集群当前无 Pending Pod，无法执行真实强断言",
            "alert": _make_alert(
                alert_id="alert-pending-real-002",
                title="KubePodNotReady",
                message="Pod has been in Pending state for more than 15 minutes",
                severity="warning",
                labels={
                    "cluster": "cluster1",
                    "namespace": pending["namespace"] if pending else "default",
                    "pod": pending["pod"] if pending else "pending-pod-not-found",
                    **({"container": pending["container"]} if pending and pending.get("container") else {}),
                    **({"node": pending["node"]} if pending and pending.get("node") else {}),
                },
                summary="Pod is stuck in Pending, possible resource or scheduling issue",
            ),
        },
        {
            "name": "4.3 Node Alert",
            "expected_type": "node",
            "mode": "assert",
            "alert": _make_alert(
                alert_id="alert-node-real-003",
                title="KubeNodeNotReady",
                message="Node health requires diagnosis",
                severity="critical",
                labels={"cluster": "cluster1", "node": node["node"]},
                summary=f"Node {node['node']} requires diagnosis",
            ),
        },
        {
            "name": "4.4 Service Abnormal",
            "expected_type": "service",
            "mode": "assert",
            "alert": _make_alert(
                alert_id="alert-svc-real-004",
                title="ServiceEndpointCheck",
                message="Validate service topology and backend pod context",
                severity="critical",
                labels={"cluster": "cluster1", "namespace": service["namespace"], "service": service["service"]},
                summary=f"Service {service['service']} topology verification",
            ),
        },
        {
            "name": "4.5 Post-Deployment Abnormal",
            "expected_type": "deployment",
            "mode": "assert",
            "alert": _make_alert(
                alert_id="alert-deploy-real-005",
                title="KubeDeploymentReplicasMismatch",
                message="Validate deployment runtime and revision history context",
                severity="warning",
                labels={"cluster": "cluster1", "namespace": deployment["namespace"], "deployment": deployment["deployment"]},
                summary=f"Deployment {deployment['deployment']} post rollout verification",
            ),
        },
    ]

    return scenarios


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_scenario(scenario: dict, llm_model, skill_tool_id: int) -> bool:
    from apps.opspilot.services.chat_service import ChatService

    name = scenario["name"]
    if scenario.get("mode") == "skip":
        logger.info("=" * 80)
        logger.info("[%s] SKIP: %s", name, scenario.get("skip_reason", "未提供原因"))
        logger.info("=" * 80)
        return None

    logger.info("=" * 80)
    logger.info("[%s] 开始场景测试", name)
    logger.info("[%s] 模型: %s (id=%s)", name, llm_model.name, llm_model.id)

    params = _build_invoke_params(llm_model, scenario["alert"], skill_tool_id)

    try:
        result, doc_map, title_map = ChatService.invoke_chat(params)
    except Exception:
        logger.error("[%s] FAIL: invoke_chat 异常:\n%s", name, traceback.format_exc())
        return False

    message = result.get("message", "")
    logger.info("[%s] 返回消息长度: %d", name, len(message))
    logger.info("[%s] 返回消息前 3000 字符:\n%s", name, message[:3000])

    pkg = _validate_evidence_package(message, name)
    if pkg is None:
        return False

    # Type check
    target = pkg.get("target", {})
    actual_type = target.get("resource_type", "")
    expected = scenario.get("expected_type", "")
    if expected and actual_type != expected:
        logger.error("[%s] target.resource_type=%s (期望 %s)", name, actual_type, expected)
        return False

    try:
        _assert_scenario_content(pkg, scenario)
    except AssertionError as e:
        logger.error("[%s] FAIL: %s", name, e)
        return False

    logger.info("[%s] PASS", name)
    logger.info("=" * 80)
    return True


def main():
    # Only run specific scenarios if given as args, e.g.: "4.1" "4.3"
    filter_ids = set(sys.argv[1:]) if len(sys.argv) > 1 else set()

    llm_model = _get_gpt4o_model()
    skill_tool_id = _get_skill_tool_id()
    logger.info("使用模型: %s (id=%s, api_base=%s)", llm_model.name, llm_model.id, llm_model.openai_api_base)
    logger.info("使用工具集: kubernetes_data_collection (id=%s)", skill_tool_id)

    scenarios = _build_scenarios()

    results = {}
    for scenario in scenarios:
        name = scenario["name"]
        # Filter: "4.1" matches "4.1 Pod CrashLoop"
        if filter_ids and not any(fid in name for fid in filter_ids):
            continue
        ok = run_scenario(scenario, llm_model, skill_tool_id)
        results[name] = "SKIP" if ok is None else ("PASS" if ok else "FAIL")

    logger.info("=" * 80)
    logger.info("场景测试汇总:")
    for name, status in results.items():
        logger.info("  %s: %s", name, status)

    failed = [n for n, s in results.items() if s == "FAIL"]
    if failed:
        logger.error("失败场景: %s", failed)
        sys.exit(1)
    else:
        skipped = [n for n, s in results.items() if s == "SKIP"]
        if skipped:
            logger.warning("跳过场景: %s", skipped)
        logger.info("全部通过")


if __name__ == "__main__":
    main()
