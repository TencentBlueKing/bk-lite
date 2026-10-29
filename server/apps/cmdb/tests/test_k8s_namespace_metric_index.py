"""同名工作负载和 Pod 必须按命名空间分开索引副本、模板标签和容器资源。"""
import json
import time

import pydantic.root_model  # noqa: F401

from apps.cmdb.collection.collect_plugin.k8s import CollectK8sMetrics
from apps.cmdb.collection.constants import (
    K8S_DEPLOYMENT_ANNOTATIONS,
    K8S_DEPLOYMENT_REPLICAS,
    K8S_POD_CONTAINER_RESOURCE_LIMITS,
    K8S_POD_CONTAINER_RESOURCE_REQUESTS,
    K8S_POD_INFO,
)

CLUSTER = "audit-cluster"
DEPLOYMENT_CREATED = "prometheus_kube_deployment_created"


def _applied_labels(scope):
    body = {"spec": {"template": {"metadata": {"labels": {"scope": scope}}}}}
    return json.dumps(body)


def _replica_sample(namespace, value):
    metric = {"__name__": K8S_DEPLOYMENT_REPLICAS, "deployment": "api"}
    if namespace is not None:
        metric["namespace"] = namespace
    return {"metric": metric, "value": [time.time(), str(value)]}


def _deployment_row(namespace):
    return {
        "index_key": DEPLOYMENT_CREATED,
        "deployment": "api",
        "namespace": namespace,
        "instance_id": CLUSTER,
    }


def _annotation_row(namespace):
    return {
        "index_key": K8S_DEPLOYMENT_ANNOTATIONS,
        "deployment": "api",
        "namespace": namespace,
        "annotation_kubectl_kubernetes_io_last_applied_configuration": _applied_labels(namespace),
    }


def _install_replicas(monkeypatch, samples):
    def _query(self, sql, **kwargs):
        return {"data": {"result": samples}}

    monkeypatch.setattr("apps.cmdb.collection.collect_plugin.k8s.Collection.query", _query)


def _format_workloads(monkeypatch, samples, rows):
    _install_replicas(monkeypatch, samples)
    runner = CollectK8sMetrics(CLUSTER)
    runner.collection_metrics_dict["workload"] = rows
    runner.format_workload_metrics()
    return {item["inst_name"]: item for item in runner.result["k8s_workload"]}


def _assert_split_deployments(workloads):
    ns_a = workloads[f"api({CLUSTER}/ns-a)"]
    ns_b = workloads[f"api({CLUSTER}/ns-b)"]
    assert ns_a["replicas"] == 1
    assert ns_a["labels"] == "scope=ns-a"
    assert ns_b["replicas"] == 3
    assert ns_b["labels"] == "scope=ns-b"


def test_same_name_deployments_keep_namespace_replicas_and_labels(monkeypatch):
    ns_a_samples = [_replica_sample("ns-a", 1)]
    ns_b_samples = [_replica_sample("ns-b", 3)]
    ns_a_rows = [_deployment_row("ns-a"), _annotation_row("ns-a")]
    ns_b_rows = [_deployment_row("ns-b"), _annotation_row("ns-b")]

    forward = _format_workloads(monkeypatch, ns_a_samples + ns_b_samples, ns_a_rows + ns_b_rows)
    _assert_split_deployments(forward)

    reversed_order = _format_workloads(monkeypatch, ns_b_samples + ns_a_samples, ns_b_rows + ns_a_rows)
    _assert_split_deployments(reversed_order)


def _pod_rows(namespace, cpu):
    return [
        {
            "index_key": K8S_POD_INFO,
            "pod": "probe",
            "namespace": namespace,
            "created_by_kind": "Job",
            "created_by_name": "probe-job",
        },
        {
            "index_key": K8S_POD_CONTAINER_RESOURCE_LIMITS,
            "pod": "probe",
            "namespace": namespace,
            "container": "main",
            "resource": "cpu",
            "index_value": str(cpu),
        },
        {
            "index_key": K8S_POD_CONTAINER_RESOURCE_REQUESTS,
            "pod": "probe",
            "namespace": namespace,
            "container": "main",
            "resource": "cpu",
            "index_value": str(cpu),
        },
    ]


def _assert_split_pods(pods):
    ns_a = pods[f"probe({CLUSTER}/ns-a)"]
    ns_b = pods[f"probe({CLUSTER}/ns-b)"]
    assert ns_a["request_cpu"] == 1.0
    assert ns_a["limit_cpu"] == 1.0
    assert ns_b["request_cpu"] == 3.0
    assert ns_b["limit_cpu"] == 3.0


def test_same_name_pods_keep_namespace_cpu(monkeypatch):
    del monkeypatch
    for rows in (_pod_rows("ns-a", 1) + _pod_rows("ns-b", 3), _pod_rows("ns-b", 3) + _pod_rows("ns-a", 1)):
        runner = CollectK8sMetrics(CLUSTER)
        runner.collection_metrics_dict["pod"] = rows
        runner.format_pod_metrics()
        pods = {item["inst_name"]: item for item in runner.result["k8s_pod"]}
        _assert_split_pods(pods)


def test_replica_without_namespace_does_not_match_by_name(monkeypatch):
    samples = [_replica_sample("ns-a", 1), _replica_sample(None, 9)]
    workloads = _format_workloads(
        monkeypatch,
        samples,
        [_deployment_row("ns-a"), _annotation_row("ns-a")],
    )
    assert workloads[f"api({CLUSTER}/ns-a)"]["replicas"] == 1


def test_single_namespace_deployment_keeps_replicas_and_labels(monkeypatch):
    workloads = _format_workloads(
        monkeypatch,
        [_replica_sample("ns-a", 1)],
        [_deployment_row("ns-a"), _annotation_row("ns-a")],
    )
    workload = workloads[f"api({CLUSTER}/ns-a)"]
    assert workload["replicas"] == 1
    assert workload["labels"] == "scope=ns-a"
