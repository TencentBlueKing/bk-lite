"""CollectK8sMetrics 解析逻辑单元测试。

对照 apps/cmdb/collection/collect_plugin/k8s.py：node/pod/workload/namespace 四类指标
的格式化（inst_name 拼接、关联关系构建、资源单位换算、ReplicaSet 归属推导、注解解析）。

VM 查询边界（Collection.query）被打桩；其余全部跑真实解析逻辑并断言真实输出。
"""
import pydantic.root_model  # noqa: F401

from apps.cmdb.collection.collect_plugin.k8s import CollectK8sMetrics
from apps.cmdb.collection.constants import (
    K8S_DEPLOYMENT_ANNOTATIONS,
    K8S_NODE_INFO,
    K8S_NODE_ROLE,
    K8S_NODE_STATUS_CAPACITY,
    K8S_POD_CONTAINER_RESOURCE_LIMITS,
    K8S_POD_CONTAINER_RESOURCE_REQUESTS,
    K8S_POD_INFO,
    K8S_WORKLOAD_REPLICASET,
    K8S_WORKLOAD_REPLICASET_OWNER,
    NODE_CLUSTER_RELATION,
    POD_NODE_RELATION,
    POD_WORKLOAD_RELATION,
    WORKLOAD_NAMESPACE_RELATION,
)

CLUSTER = "prod-cluster"


def _runner(monkeypatch, replicas_map=None):
    """构造一个 runner，并打桩 search_replicas（避免真实 VM 查询）。"""
    monkeypatch.setattr(CollectK8sMetrics, "search_replicas", lambda self: replicas_map or {})
    return CollectK8sMetrics(cluster_name=CLUSTER)


# --------------------------------------------------------------------------
# collector_cluster_id 退化
# --------------------------------------------------------------------------
def test_collector_cluster_id_falls_back_to_cluster_name(monkeypatch):
    monkeypatch.setattr(CollectK8sMetrics, "search_replicas", lambda self: {})
    r = CollectK8sMetrics(cluster_name=CLUSTER)
    assert r.collector_cluster_id == CLUSTER


def test_collector_cluster_id_explicit(monkeypatch):
    monkeypatch.setattr(CollectK8sMetrics, "search_replicas", lambda self: {})
    r = CollectK8sMetrics(cluster_name=CLUSTER, collector_cluster_id="vm-id-123")
    assert r.collector_cluster_id == "vm-id-123"


# --------------------------------------------------------------------------
# format_namespace_metrics
# --------------------------------------------------------------------------
def test_format_namespace_metrics(monkeypatch):
    r = _runner(monkeypatch)
    r.collection_metrics_dict["namespace"] = [{"namespace": "default"}, {"namespace": "kube-system"}]
    r.format_namespace_metrics()
    out = r.result["k8s_namespace"]
    names = sorted(i["name"] for i in out)
    assert names == ["default", "kube-system"]
    first = next(i for i in out if i["name"] == "default")
    assert first["inst_name"] == f"default({CLUSTER})"
    assert first["self_cluster"] == CLUSTER
    assert first["assos"][0]["model_id"] == "k8s_cluster"
    assert first["assos"][0]["inst_name"] == CLUSTER


# --------------------------------------------------------------------------
# format_node_metrics
# --------------------------------------------------------------------------
def test_format_node_metrics_full(monkeypatch):
    r = _runner(monkeypatch)
    r.collection_metrics_dict["node"] = [
        {
            "index_key": K8S_NODE_INFO,
            "node": "node-1",
            "internal_ip": "10.0.0.5",
            "os_image": "Ubuntu 22.04",
            "kernel_version": "5.15",
            "kubelet_version": "v1.28",
            "container_runtime_version": "containerd://1.6",
            "pod_cidr": "10.244.0.0/24",
        },
        {"index_key": K8S_NODE_ROLE, "node": "node-1", "role": "master"},
        {"index_key": K8S_NODE_ROLE, "node": "node-1", "role": "worker"},
        {"index_key": K8S_NODE_STATUS_CAPACITY, "node": "node-1", "resource": "cpu", "index_value": "8"},
        {"index_key": K8S_NODE_STATUS_CAPACITY, "node": "node-1", "resource": "memory", "index_value": str(16 * 1024 ** 3)},
        {"index_key": K8S_NODE_STATUS_CAPACITY, "node": "node-1", "resource": "ephemeral_storage", "index_value": str(100 * 1024 ** 3)},
    ]
    r.format_node_metrics()
    out = r.result["k8s_node"]
    assert len(out) == 1
    node = out[0]
    assert node["inst_name"] == f"node-1({CLUSTER})"
    assert node["ip_addr"] == "10.0.0.5"
    assert node["cpu"] == 8
    assert node["memory"] == 16  # GiB 换算
    assert node["storage"] == 100
    assert node["role"] == "master,worker"
    assert node["assos"][0]["model_asst_id"] == NODE_CLUSTER_RELATION


def test_format_node_metrics_drops_falsy_fields(monkeypatch):
    r = _runner(monkeypatch)
    r.collection_metrics_dict["node"] = [
        {"index_key": K8S_NODE_INFO, "node": "n2", "internal_ip": "", "os_image": None},
    ]
    r.format_node_metrics()
    node = r.result["k8s_node"][0]
    # 空值字段被过滤
    assert "ip_addr" not in node
    assert "os_version" not in node
    assert "role" not in node
    assert node["name"] == "n2"


# --------------------------------------------------------------------------
# format_pod_metrics
# --------------------------------------------------------------------------
def test_format_pod_metrics_with_node_and_workload_assos(monkeypatch):
    r = _runner(monkeypatch)
    # workload index 需含 replicaset 键以建立 deployment 关联
    r.collection_metrics_dict["workload"] = [
        {"replicaset": "web-rs-abc", "owner_name": "web-deploy"},
    ]
    r.collection_metrics_dict["pod"] = [
        {
            "index_key": K8S_POD_INFO,
            "pod": "web-rs-abc-x1",
            "namespace": "default",
            "pod_ip": "10.244.0.10",
            "node": "node-1",
            "created_by_kind": "ReplicaSet",
            "created_by_name": "web-rs-abc",
        },
        {"index_key": K8S_POD_CONTAINER_RESOURCE_LIMITS, "pod": "web-rs-abc-x1", "resource": "cpu", "index_value": "2"},
        {"index_key": K8S_POD_CONTAINER_RESOURCE_LIMITS, "pod": "web-rs-abc-x1", "resource": "memory", "index_value": str(2 * 1024 ** 3)},
        {"index_key": K8S_POD_CONTAINER_RESOURCE_REQUESTS, "pod": "web-rs-abc-x1", "resource": "cpu", "index_value": "1"},
    ]
    r.format_pod_metrics()
    out = r.result["k8s_pod"]
    pod = out[0]
    assert pod["inst_name"] == f"web-rs-abc-x1({CLUSTER}/default)"
    assert pod["ip_addr"] == "10.244.0.10"
    assert pod["limit_cpu"] == 2.0
    assert pod["limit_memory"] == 2  # GiB
    assert pod["request_cpu"] == 1.0
    # ReplicaSet → 通过 workload index 找到 deployment
    assert pod["k8s_workload"] == "web-deploy"
    asso_models = {a["model_asst_id"] for a in pod["assos"]}
    assert POD_NODE_RELATION in asso_models
    assert POD_WORKLOAD_RELATION in asso_models


def test_format_pod_metrics_replicaset_without_workload_falls_back_to_namespace(monkeypatch):
    r = _runner(monkeypatch)
    r.collection_metrics_dict["workload"] = []  # 无匹配 workload
    r.collection_metrics_dict["pod"] = [
        {
            "index_key": K8S_POD_INFO,
            "pod": "orphan-x",
            "namespace": "ns1",
            "created_by_kind": "ReplicaSet",
            "created_by_name": "missing-rs",
            "node": None,
        },
    ]
    r.format_pod_metrics()
    pod = r.result["k8s_pod"][0]
    # 回退到 namespace 关联，且无 node 关联
    asso_models = {a["model_asst_id"] for a in pod["assos"]}
    assert POD_NODE_RELATION not in asso_models
    from apps.cmdb.collection.constants import POD_NAMESPACE_RELATION
    assert POD_NAMESPACE_RELATION in asso_models


def test_format_pod_metrics_direct_workload_kind(monkeypatch):
    r = _runner(monkeypatch)
    r.collection_metrics_dict["workload"] = []
    r.collection_metrics_dict["pod"] = [
        {
            "index_key": K8S_POD_INFO,
            "pod": "ds-pod",
            "namespace": "ns1",
            "created_by_kind": "DaemonSet",
            "created_by_name": "my-ds",
            "node": "node-9",
        },
    ]
    r.format_pod_metrics()
    pod = r.result["k8s_pod"][0]
    assert pod["k8s_workload"] == "my-ds"
    asso_models = {a["model_asst_id"] for a in pod["assos"]}
    assert POD_WORKLOAD_RELATION in asso_models


# --------------------------------------------------------------------------
# format_workload_metrics
# --------------------------------------------------------------------------
def test_format_workload_metrics_deployment_with_replicas(monkeypatch):
    r = _runner(monkeypatch, replicas_map={"deployment": {"web-deploy": "3"}})
    r.collection_metrics_dict["workload"] = [
        {
            "index_key": "prometheus_kube_deployment_created",
            "deployment": "web-deploy",
            "namespace": "default",
            "instance_id": "vm-1",
        },
    ]
    r.format_workload_metrics()
    out = r.result["k8s_workload"]
    wl = out[0]
    assert wl["name"] == "web-deploy"
    assert wl["workload_type"] == "deployment"
    assert wl["replicas"] == 3
    assert wl["inst_name"] == f"web-deploy({CLUSTER}/default)"
    assert wl["assos"][0]["model_asst_id"] == WORKLOAD_NAMESPACE_RELATION


def test_format_workload_metrics_replicaset_with_owner(monkeypatch):
    r = _runner(monkeypatch, replicas_map={})
    r.collection_metrics_dict["workload"] = [
        {
            "index_key": K8S_WORKLOAD_REPLICASET,
            "replicaset": "web-rs",
            "namespace": "default",
            "instance_id": "vm-1",
        },
        {
            "index_key": K8S_WORKLOAD_REPLICASET_OWNER,
            "replicaset": "web-rs",
            "namespace": "default",
            "owner_kind": "Deployment",
            "owner_name": "web-deploy",
        },
    ]
    r.format_workload_metrics()
    out = r.result["k8s_workload"]
    wl = out[0]
    # 有有效 owner → 归属到 deployment
    assert wl["workload_type"] == "deployment"
    assert wl["name"] == "web-deploy"
    assert wl["replicaset_name"] == "web-rs"
    assert wl["inst_name"] == f"web-rs({CLUSTER}/web-deploy)"


def test_format_workload_metrics_replicaset_without_owner(monkeypatch):
    r = _runner(monkeypatch, replicas_map={})
    r.collection_metrics_dict["workload"] = [
        {
            "index_key": K8S_WORKLOAD_REPLICASET,
            "replicaset": "lonely-rs",
            "namespace": "default",
            "instance_id": "vm-1",
        },
    ]
    r.format_workload_metrics()
    wl = r.result["k8s_workload"][0]
    # 无 owner → 独立 replicaset
    assert wl["workload_type"] == "replicaset"
    assert wl["name"] == "lonely-rs"


# --------------------------------------------------------------------------
# format_annotation_metrics
# --------------------------------------------------------------------------
def test_format_annotation_metrics_extracts_labels():
    import json
    annotation = {
        "spec": {"template": {"metadata": {"labels": {"app": "web", "tier": "frontend"}}}}
    }
    metrics = {"annotation_kubectl_kubernetes_io_last_applied_configuration": json.dumps(annotation)}
    labels = CollectK8sMetrics.format_annotation_metrics(metrics)
    assert "app=web" in labels
    assert "tier=frontend" in labels


def test_format_annotation_metrics_missing_key():
    assert CollectK8sMetrics.format_annotation_metrics({}) == ""


def test_format_annotation_metrics_invalid_json():
    metrics = {"annotation_kubectl_kubernetes_io_last_applied_configuration": "{not json"}
    assert CollectK8sMetrics.format_annotation_metrics(metrics) == ""


def test_format_annotation_metrics_no_labels_in_spec():
    import json
    annotation = {"spec": {"template": {"metadata": {}}}}
    metrics = {"annotation_kubectl_kubernetes_io_last_applied_configuration": json.dumps(annotation)}
    assert CollectK8sMetrics.format_annotation_metrics(metrics) == ""


# --------------------------------------------------------------------------
# get_metrics / collect_data / collect_params
# --------------------------------------------------------------------------
def test_get_metrics_aggregates_all_categories():
    metrics = CollectK8sMetrics.get_metrics()
    assert K8S_NODE_INFO in metrics
    assert K8S_POD_INFO in metrics
    assert "prometheus_kube_namespace_labels" in metrics


def test_collect_data_and_params(monkeypatch):
    r = _runner(monkeypatch)
    r.collection_metrics_dict["node"] = [{"x": 1}]
    data = r.collect_data
    assert set(data.keys()) == {"k8s_node", "k8s_pod", "k8s_workload", "k8s_namespace"}
    assert data["k8s_node"] == [{"x": 1}]
    assert r.collect_params["node"] == "k8s_node"


# --------------------------------------------------------------------------
# query_data（VM 边界打桩）
# --------------------------------------------------------------------------
def test_query_data_parses_vm_response(monkeypatch):
    r = _runner(monkeypatch)
    vm_resp = {"data": {"result": [{"metric": {"__name__": "x"}, "value": [1, "2"]}]}}
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_resp,
    )
    out = r.query_data()
    assert out == vm_resp["data"]
    assert r.raw_data == vm_resp["data"]["result"]


# --------------------------------------------------------------------------
# format_data 编排（含一天前时间戳短路）
# --------------------------------------------------------------------------
def test_format_data_routes_metrics_into_buckets(monkeypatch):
    import time
    now_ts = int(time.time())
    r = _runner(monkeypatch)
    # 桩掉子格式化方法以隔离路由逻辑
    monkeypatch.setattr(CollectK8sMetrics, "format_namespace_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_pod_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_node_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_workload_metrics", lambda self: None)
    data = {
        "result": [
            {"metric": {"__name__": "prometheus_kube_namespace_labels", "namespace": "default"}, "value": [now_ts, "1"]},
            {"metric": {"__name__": K8S_NODE_INFO, "node": "n1"}, "value": [now_ts, "1"]},
            {"metric": {"__name__": K8S_POD_INFO, "pod": "p1"}, "value": [now_ts, "1"]},
        ]
    }
    r.format_data(data)
    assert len(r.collection_metrics_dict["namespace"]) == 1
    assert len(r.collection_metrics_dict["node"]) == 1
    assert len(r.collection_metrics_dict["pod"]) == 1


def test_format_data_breaks_on_old_timestamp(monkeypatch):
    r = _runner(monkeypatch)
    monkeypatch.setattr(CollectK8sMetrics, "format_namespace_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_pod_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_node_metrics", lambda self: None)
    monkeypatch.setattr(CollectK8sMetrics, "format_workload_metrics", lambda self: None)
    # 第一条时间戳为 0（远早于一天前）→ 整个循环 break，桶为空
    data = {"result": [{"metric": {"__name__": K8S_NODE_INFO, "node": "n1"}, "value": [0, "1"]}]}
    r.format_data(data)
    assert r.collection_metrics_dict["node"] == []
