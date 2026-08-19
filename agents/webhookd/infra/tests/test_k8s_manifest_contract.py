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

# 渲染前的模板占位符，独占整行，解析前剔除
LINE_PLACEHOLDERS = (
    "__LOG_VOLUME_MOUNTS__",
    "__LOG_VOLUMES__",
    "__INCLUDE_PATHS_GLOB_PATTERNS__",
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
