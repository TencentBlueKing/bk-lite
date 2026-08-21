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


@pytest.mark.parametrize("config_type", ["metric", "log"])
def test_custom_tolerations_only_reach_daemonsets(config_type):
    """显式清单注入 DaemonSet（无 value 渲染为 Exists，有 value 渲染为 Equal），Deployment 不受影响。
    log 类型同时护住「容忍注入必须是最后一个占位符替换」的顺序回归。"""
    requested = [
        {"key": "dedicated", "value": "edge", "effect": "NoSchedule"},
        {"key": "CriticalAddonsOnly", "effect": "NoExecute"},
    ]
    result, response = _render(config_type, tolerations=requested)

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
    ("case", "tolerations", "expected_message"),
    [
        ("wildcard-without-key", [{"operator": "Exists", "effect": "NoSchedule"}], "wildcard tolerations are not allowed"),
        ("empty-key", [{"key": "", "effect": "NoSchedule"}], "key is required"),
        ("non-string-key", [{"key": 123, "effect": "NoSchedule"}], "key is required"),
        ("missing-effect", [{"key": "dedicated"}], "effect must be NoSchedule or NoExecute"),
        ("prefer-no-schedule", [{"key": "dedicated", "effect": "PreferNoSchedule"}], "effect must be NoSchedule or NoExecute"),
        ("not-a-list", {"key": "dedicated", "effect": "NoSchedule"}, "must be a JSON array"),
        ("toleration-seconds", [{"key": "a", "effect": "NoExecute", "tolerationSeconds": 30}], "unknown fields"),
        ("yaml-injection-in-key", [{"key": "a\nevil: true", "effect": "NoSchedule"}], "qualified-name"),
        ("yaml-injection-in-value", [{"key": "a", "value": "x\"\nevil: true", "effect": "NoSchedule"}], "label-value"),
        ("double-slash-key", [{"key": "a/b/c", "effect": "NoSchedule"}], "more than one /"),
        ("bad-dns-prefix-uppercase", [{"key": "Example.COM/dedicated", "effect": "NoSchedule"}], "not a DNS subdomain"),
        ("bad-dns-prefix-empty-label", [{"key": "a..b/dedicated", "effect": "NoSchedule"}], "not a DNS subdomain"),
        ("placeholder-in-key", [{"key": "X__LOG_VOLUME_MOUNTS__X", "effect": "NoSchedule"}], "reserved for template placeholders"),
        ("placeholder-in-value", [{"key": "a", "value": "X__DS_TOLERATIONS__X", "effect": "NoSchedule"}], "reserved for template placeholders"),
        ("too-many-items", [{"key": f"k{i}", "effect": "NoSchedule"} for i in range(17)], "at most 16 items"),
    ],
)
def test_invalid_tolerations_are_rejected(case, tolerations, expected_message):
    """受限 schema：非法输入必须整单拒绝，且给出干净的校验消息而非内部异常。"""
    result, response = _render("metric", tolerations=tolerations)

    assert response["status"] == "error", f"{case} 应被拒绝: {response}"
    assert expected_message in response.get("message", ""), f"{case} 拒绝原因不符: {response}"
    assert "Traceback" not in response.get("message", ""), f"{case} 泄漏了内部异常: {response}"


@pytest.mark.parametrize("ambiguous_key", ["null", "true", "false", "on", "off", "yes", "no", "123456", "0x1A", "1.5"])
def test_yaml_ambiguous_keys_render_as_strings(ambiguous_key):
    """YAML 1.1 隐式标量形态的合法 key 必须引号化输出：裸拼时 "null" 会解析成空 key
    （= 无 key 通配容忍，正是本设计要消灭的），"on"/"0x1A" 会被静默改名。"""
    result, response = _render("metric", tolerations=[{"key": ambiguous_key, "effect": "NoSchedule"}])

    assert result.returncode == 0, result.stderr
    assert response["status"] == "success"
    for workload, value in _workload_tolerations(response["yaml"]).items():
        if workload.startswith("DaemonSet/"):
            rendered_key = value[0]["key"]
            assert isinstance(rendered_key, str), f"{workload} 的 key 被 YAML 隐式转型: {rendered_key!r}"
            assert rendered_key == ambiguous_key, f"{workload} 的 key 被改写: {rendered_key!r}"


def test_toleration_value_is_quoted_in_raw_yaml():
    """value 的引号必须锁在原始文本层面：round-trip 比较会被解析器抵消，测不出引号丢失。"""
    result, response = _render("metric", tolerations=[{"key": "dedicated", "value": "true", "effect": "NoSchedule"}])

    assert response["status"] == "success"
    assert 'value: "true"' in response["yaml"]
    assert 'key: "dedicated"' in response["yaml"]


def test_null_tolerations_equals_omitted():
    """显式 null 与缺省等价（上游可选字段序列化为 null 是常态），区别于显式 [] 的零容忍。"""
    result, response = _render("metric", tolerations=None)

    assert result.returncode == 0, result.stderr
    assert response["status"] == "success"
    for workload, value in _workload_tolerations(response["yaml"]).items():
        if workload.startswith("DaemonSet/"):
            assert value == DEFAULT_DS_TOLERATIONS


def test_dns_prefixed_key_is_accepted():
    """带 DNS 前缀的 key（nvidia.com/gpu 形态）是真实场景最常见形态，正例必须钉住。"""
    result, response = _render("metric", tolerations=[{"key": "example.com/dedicated", "effect": "NoSchedule"}])

    assert response["status"] == "success"
    for workload, value in _workload_tolerations(response["yaml"]).items():
        if workload.startswith("DaemonSet/"):
            assert value[0]["key"] == "example.com/dedicated"


def test_boundary_sizes_are_accepted():
    """界内边界必须成功：name 63 字符、prefix 253 字符、恰好 16 项。"""
    name_63 = "a" * 63
    prefix_253 = ".".join(["a" * 61, "b" * 61, "c" * 61, "d" * 61, "e" * 5])
    assert len(prefix_253) == 253
    sixteen = [{"key": f"k{i}", "effect": "NoSchedule"} for i in range(16)]

    for tolerations in ([{"key": name_63, "effect": "NoSchedule"}], [{"key": f"{prefix_253}/x", "effect": "NoSchedule"}], sixteen):
        result, response = _render("metric", tolerations=tolerations)
        assert response["status"] == "success", response


def test_empty_string_value_renders_equal_with_empty_value():
    """value 为空串是合法输入：渲染为 operator Equal + value ""，用于精确匹配空值污点。"""
    result, response = _render("metric", tolerations=[{"key": "dedicated", "value": "", "effect": "NoSchedule"}])

    assert response["status"] == "success"
    for workload, value in _workload_tolerations(response["yaml"]).items():
        if workload.startswith("DaemonSet/"):
            assert value == [{"key": "dedicated", "operator": "Equal", "value": "", "effect": "NoSchedule"}]


def test_resource_type_silently_ignores_tolerations():
    """resource 模板没有 DaemonSet：清单照常校验但不落地（钉住该行为，API 文档已注明）。"""
    result, response = _render("resource", tolerations=[{"key": "dedicated", "effect": "NoSchedule"}])

    assert response["status"] == "success"
    assert "dedicated" not in response["yaml"]
    assert all(value is None for value in _workload_tolerations(response["yaml"]).values())


def test_render_default_matches_dist_static_default():
    """跨真值一致性锁：webhookd 渲染默认与 dist 静态包写死的默认必须逐字段相等。
    两条生产路径各自有测试比对各自的常量，缺这条锁时可以分叉而全部测试仍然全绿。"""
    dist_dir = WEBHOOKD_ROOT.parents[1] / "deploy" / "dist" / "bk-lite-kubernetes-collector"
    checks = [("metric", dist_dir / "bk-lite-metric-collector.yaml"), ("log", dist_dir / "bk-lite-log-collector.yaml")]
    for config_type, dist_path in checks:
        _, response = _render(config_type)
        rendered = {
            workload: value
            for workload, value in _workload_tolerations(response["yaml"]).items()
            if workload.startswith("DaemonSet/")
        }
        dist_docs = [document for document in yaml.safe_load_all(dist_path.read_text(encoding="utf-8")) if document]
        dist = {
            f"DaemonSet/{document['metadata']['name']}": document["spec"]["template"]["spec"].get("tolerations")
            for document in dist_docs
            if document.get("kind") == "DaemonSet"
        }
        assert rendered == dist, f"{config_type}: 渲染默认与 dist 静态默认漂移\n渲染={rendered}\ndist={dist}"
