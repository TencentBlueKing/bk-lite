"""K8S 采集器 manifest 的集群级资源命名契约。

集群级资源（ClusterRole / ClusterRoleBinding）在整个集群内唯一，`kubectl apply`
遇到同名对象会整份覆盖而不是合并。裸名 `kube-state-metrics` / `vmagent-role` /
`vector-daemonset` 会与集群自带的监控栈（kube-prometheus、KubeSphere 等）撞名，
静默夺走对方的权限。因此 BK-Lite 下发的集群级资源必须带 `bk-lite-` 前缀。
"""

from pathlib import Path

import pytest
import yaml

WEBHOOKD_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = WEBHOOKD_DIR.parents[1]
DIST_DIR = REPO_ROOT / "deploy" / "dist" / "bk-lite-kubernetes-collector"

MANIFEST_PATHS = [
    WEBHOOKD_DIR / "bk-lite-metric-collector.yaml",
    WEBHOOKD_DIR / "bk-lite-resource-collector.yaml",
    WEBHOOKD_DIR / "bk-lite-log-collector.yaml",
    DIST_DIR / "bk-lite-metric-collector.yaml",
    DIST_DIR / "bk-lite-log-collector.yaml",
]

CLUSTER_SCOPED_KINDS = ("ClusterRole", "ClusterRoleBinding")
CLUSTER_SCOPED_PREFIX = "bk-lite-"
# DaemonSet 容忍策略：模板经 __DS_TOLERATIONS__ 占位符由渲染脚本注入（默认两条精确容忍），
# dist 静态部署包写死同样的默认值；Deployment 一律不带 tolerations，遵循集群默认调度。
DS_TOLERATIONS_PLACEHOLDER = "__DS_TOLERATIONS__"
DEFAULT_DS_TOLERATIONS = [
    {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
    {"key": "node-role.kubernetes.io/master", "operator": "Exists", "effect": "NoSchedule"},
]
TEMPLATE_MANIFEST_PATHS = [
    WEBHOOKD_DIR / "bk-lite-metric-collector.yaml",
    WEBHOOKD_DIR / "bk-lite-resource-collector.yaml",
    WEBHOOKD_DIR / "bk-lite-log-collector.yaml",
]
DIST_MANIFEST_PATHS = [
    DIST_DIR / "bk-lite-metric-collector.yaml",
    DIST_DIR / "bk-lite-log-collector.yaml",
]

# 渲染前的模板占位符，独占整行，解析前剔除
LINE_PLACEHOLDERS = (
    "__LOG_VOLUME_MOUNTS__",
    "__LOG_VOLUMES__",
    "__INCLUDE_PATHS_GLOB_PATTERNS__",
    "__DS_TOLERATIONS__",
)


def _load_documents(path):
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if line.strip() not in LINE_PLACEHOLDERS)
    return [document for document in yaml.safe_load_all(text) if document]


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda path: path.name)
def test_cluster_scoped_resources_are_namespaced_by_name(path):
    """集群级资源必须带 bk-lite- 前缀，避免与集群自带监控栈撞名。"""
    for document in _load_documents(path):
        if document["kind"] not in CLUSTER_SCOPED_KINDS:
            continue
        name = document["metadata"]["name"]
        assert name.startswith(CLUSTER_SCOPED_PREFIX), (
            f"{path.name}: {document['kind']} `{name}` 缺少 `{CLUSTER_SCOPED_PREFIX}` 前缀，" "会与集群内同名的集群级资源互相覆盖"
        )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda path: path.name)
def test_cluster_scoped_resources_carry_no_namespace_field(path):
    """集群级资源上的 namespace 字段会被 API Server 忽略，不得出现。"""
    for document in _load_documents(path):
        if document["kind"] not in CLUSTER_SCOPED_KINDS:
            continue
        metadata = document["metadata"]
        assert "namespace" not in metadata, f"{path.name}: {document['kind']} `{metadata['name']}` 带了 namespace 字段，" "集群级资源没有命名空间归属"


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda path: path.name)
def test_cluster_role_binding_role_ref_resolves_within_manifest(path):
    """改名后 ClusterRoleBinding 的 roleRef 必须仍指向同一份 manifest 里的 ClusterRole。"""
    documents = _load_documents(path)
    cluster_roles = {document["metadata"]["name"] for document in documents if document["kind"] == "ClusterRole"}
    for document in documents:
        if document["kind"] != "ClusterRoleBinding":
            continue
        role_ref = document["roleRef"]
        assert role_ref["kind"] == "ClusterRole"
        assert role_ref["name"] in cluster_roles, (
            f"{path.name}: ClusterRoleBinding `{document['metadata']['name']}` 的 roleRef " f"`{role_ref['name']}` 在本 manifest 中没有对应的 ClusterRole"
        )


@pytest.mark.parametrize("path", MANIFEST_PATHS, ids=lambda path: path.name)
def test_cluster_role_binding_subjects_stay_in_bk_lite_namespace(path):
    """ServiceAccount 是命名空间内资源，主体必须仍绑定 BK-Lite 自己的命名空间。"""
    for document in _load_documents(path):
        if document["kind"] != "ClusterRoleBinding":
            continue
        for subject in document["subjects"]:
            assert subject["kind"] == "ServiceAccount"
            assert subject["namespace"].startswith("bk-lite-"), (
                f"{path.name}: ClusterRoleBinding `{document['metadata']['name']}` " f"绑定了非 BK-Lite 命名空间 `{subject['namespace']}`"
            )


def test_metric_and_resource_collector_share_identical_cluster_rbac():
    """两份 manifest 共用同一套集群级 RBAC，先后 apply 必须幂等。"""

    def cluster_rbac(path):
        return {
            (document["kind"], document["metadata"]["name"]): document
            for document in _load_documents(path)
            if document["kind"] in CLUSTER_SCOPED_KINDS
        }

    metric = cluster_rbac(WEBHOOKD_DIR / "bk-lite-metric-collector.yaml")
    resource = cluster_rbac(WEBHOOKD_DIR / "bk-lite-resource-collector.yaml")

    shared = set(metric) & set(resource)
    assert ("ClusterRole", "bk-lite-kube-state-metrics") in shared
    assert ("ClusterRoleBinding", "bk-lite-kube-state-metrics") in shared
    for identity in shared:
        assert metric[identity] == resource[identity], f"{identity} 在 metric 与 resource 采集器中定义不一致，" "后 apply 的一份会覆盖前一份"


def test_dist_and_webhookd_metric_manifests_share_cluster_rbac():
    """手动部署包与 webhookd 渲染模板的集群级 RBAC 必须同名同权限。"""

    def cluster_rbac(path):
        return {
            (document["kind"], document["metadata"]["name"]): document
            for document in _load_documents(path)
            if document["kind"] in CLUSTER_SCOPED_KINDS
        }

    template = cluster_rbac(WEBHOOKD_DIR / "bk-lite-metric-collector.yaml")
    dist = cluster_rbac(DIST_DIR / "bk-lite-metric-collector.yaml")

    assert set(template) == set(dist)
    for identity in template:
        assert template[identity] == dist[identity], f"{identity} 在 webhookd 模板与 deploy/dist 部署包中不一致"


@pytest.mark.parametrize("path", TEMPLATE_MANIFEST_PATHS + DIST_MANIFEST_PATHS, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_deployments_carry_no_tolerations(path):
    """Deployment 是中心组件，只需要集群里有地方跑；容忍污点会穿透 cordon/专用池等
    管理员隔离语义，一律遵循集群默认调度。单节点集群的 control-plane 污点由管理员
    按 Kubernetes 管理实践自行移除。"""
    for document in _load_documents(path):
        if document["kind"] != "Deployment":
            continue
        pod_spec = document["spec"]["template"]["spec"]
        assert "tolerations" not in pod_spec, (
            f"{path.name}: Deployment `{document['metadata']['name']}` 不得携带 tolerations，" "中心组件必须遵循集群默认调度语义"
        )


@pytest.mark.parametrize("path", TEMPLATE_MANIFEST_PATHS, ids=lambda path: path.name)
def test_template_daemonsets_use_tolerations_placeholder(path):
    """模板 DaemonSet 的容忍策略由渲染脚本注入：每个 DaemonSet 对应一个
    __DS_TOLERATIONS__ 占位行，模板自身不得硬编码 tolerations。"""
    documents = _load_documents(path)
    daemonsets = [document for document in documents if document["kind"] == "DaemonSet"]
    for document in daemonsets:
        assert "tolerations" not in document["spec"]["template"]["spec"], (
            f"{path.name}: DaemonSet `{document['metadata']['name']}` 硬编码了 tolerations，" "容忍策略必须经渲染参数注入"
        )
    placeholder_count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip() == DS_TOLERATIONS_PLACEHOLDER)
    assert placeholder_count == len(daemonsets), (
        f"{path.name}: __DS_TOLERATIONS__ 占位行数量 ({placeholder_count}) 与 DaemonSet 数量 ({len(daemonsets)}) 不一致"
    )


@pytest.mark.parametrize("path", DIST_MANIFEST_PATHS, ids=lambda path: path.name)
def test_dist_daemonsets_carry_exact_default_tolerations(path):
    """手动部署包无渲染环节，DaemonSet 写死与渲染默认值一致的两条精确容忍；
    禁止无 key 的通配容忍（会穿透 cordon 与专用节点隔离）。"""
    daemonsets = [document for document in _load_documents(path) if document["kind"] == "DaemonSet"]
    assert daemonsets, f"{path} 没有 DaemonSet"
    for document in daemonsets:
        tolerations = document["spec"]["template"]["spec"].get("tolerations")
        assert tolerations == DEFAULT_DS_TOLERATIONS, (
            f"{path.name}: DaemonSet `{document['metadata']['name']}` 的 tolerations 必须恰好是 " "control-plane/master 两条精确容忍"
        )
