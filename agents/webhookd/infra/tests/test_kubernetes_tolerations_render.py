"""K8S 采集器容忍策略的渲染契约。

污点是集群管理员的调度主权声明。容忍清单是接入时的显式输入（受限 schema），
仅注入节点级 DaemonSet；缺省注入 control-plane/master 两条精确容忍，
显式空数组表示不容忍任何污点。Deployment 一律不注入，遵循集群默认调度。
无 key 的通配容忍（会穿透 cordon 与专用节点隔离）在 schema 上不可表达。
"""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

WEBHOOKD_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = WEBHOOKD_ROOT / "infra/kubernetes.sh"
VALID_REQUEST = {
    "cluster_name": "prod-k8s",
    "nats_url": "tls://nats.internal:4222",
    "nats_username": "collector",
    "nats_password": "secret",
    "nats_ca": "test-ca",
}
DEFAULT_DS_TOLERATIONS = [
    {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
    {"key": "node-role.kubernetes.io/master", "operator": "Exists", "effect": "NoSchedule"},
]


def _render(config_type, **extra):
    payload = {**VALID_REQUEST, "type": config_type, **extra}
    result = subprocess.run(
        ["bash", str(SCRIPT), json.dumps(payload)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


def _workload_tolerations(yaml_content):
    tolerations = {}
    for document in yaml.safe_load_all(yaml_content):
        if isinstance(document, dict) and document.get("kind") in {"Deployment", "DaemonSet"}:
            key = f"{document['kind']}/{document['metadata']['name']}"
            tolerations[key] = document["spec"]["template"]["spec"].get("tolerations")
    return tolerations


@pytest.mark.parametrize("config_type", ["metric", "log", "resource"])
def test_default_render_gives_daemonsets_exact_control_plane_tolerations(config_type):
    """缺省渲染：DaemonSet 恰好两条精确容忍，Deployment 一律没有，占位符不残留。"""
    result, response = _render(config_type)

    assert result.returncode == 0, result.stderr
    assert response["status"] == "success"
    assert "__DS_TOLERATIONS__" not in response["yaml"]

    tolerations = _workload_tolerations(response["yaml"])
    assert tolerations
    for workload, value in tolerations.items():
        if workload.startswith("DaemonSet/"):
            assert value == DEFAULT_DS_TOLERATIONS, f"{workload} 缺省容忍不符: {value}"
        else:
            assert value is None, f"{workload} 是 Deployment，不得携带 tolerations: {value}"


def test_custom_tolerations_only_reach_daemonsets():
    """显式清单注入 DaemonSet（无 value 渲染为 Exists，有 value 渲染为 Equal），Deployment 不受影响。"""
    requested = [
        {"key": "dedicated", "value": "edge", "effect": "NoSchedule"},
        {"key": "CriticalAddonsOnly", "effect": "NoExecute"},
    ]
    result, response = _render("metric", tolerations=requested)

    assert result.returncode == 0, result.stderr
    assert response["status"] == "success"

    tolerations = _workload_tolerations(response["yaml"])
    expected = [
        {"key": "dedicated", "operator": "Equal", "value": "edge", "effect": "NoSchedule"},
        {"key": "CriticalAddonsOnly", "operator": "Exists", "effect": "NoExecute"},
    ]
    for workload, value in tolerations.items():
        if workload.startswith("DaemonSet/"):
            assert value == expected, f"{workload} 清单渲染不符: {value}"
        else:
            assert value is None


def test_explicit_empty_list_means_no_tolerations_at_all():
    """显式 [] 是管理员"任何采集组件都不容忍污点"的决定，与缺省(默认容忍)必须可区分。"""
    result, response = _render("metric", tolerations=[])

    assert result.returncode == 0, result.stderr
    assert response["status"] == "success"
    tolerations = _workload_tolerations(response["yaml"])
    assert tolerations
    assert all(value is None for value in tolerations.values())


@pytest.mark.parametrize(
    ("case", "tolerations"),
    [
        ("wildcard-without-key", [{"operator": "Exists", "effect": "NoSchedule"}]),
        ("empty-key", [{"key": "", "effect": "NoSchedule"}]),
        ("missing-effect", [{"key": "dedicated"}]),
        ("prefer-no-schedule", [{"key": "dedicated", "effect": "PreferNoSchedule"}]),
        ("not-a-list", {"key": "dedicated", "effect": "NoSchedule"}),
        ("toleration-seconds", [{"key": "a", "effect": "NoExecute", "tolerationSeconds": 30}]),
        ("yaml-injection-in-key", [{"key": "a\nevil: true", "effect": "NoSchedule"}]),
        ("yaml-injection-in-value", [{"key": "a", "value": "x\"\nevil: true", "effect": "NoSchedule"}]),
        ("double-slash-key", [{"key": "a/b/c", "effect": "NoSchedule"}]),
        ("too-many-items", [{"key": f"k{i}", "effect": "NoSchedule"} for i in range(17)]),
    ],
)
def test_invalid_tolerations_are_rejected(case, tolerations):
    """受限 schema：非法输入必须整单拒绝，而不是丢弃或静默修正。"""
    result, response = _render("metric", tolerations=tolerations)

    assert response["status"] == "error", f"{case} 应被拒绝: {response}"
