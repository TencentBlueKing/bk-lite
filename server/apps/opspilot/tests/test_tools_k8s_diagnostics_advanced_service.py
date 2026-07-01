"""Kubernetes 高级诊断 @tool 单元测试 (kubernetes/diagnostics_advanced)。

mock prepare_context 与 client.CoreV1Api/NetworkingV1Api/StorageV1Api,构造
Pod/Node/PVC/NetworkPolicy。覆盖 diagnose_pending_pod_issues(非 Pending 早退、调度失败
Condition、资源不足、NodeSelector 无匹配、污点阻断、PVC 未绑定/不存在、镜像拉取失败、
404)、check_network_policies_blocking(默认 deny egress/ingress、无策略、复杂策略)、
check_pvc_capacity(Pending PVC、挂载映射、命名空间/全局分支、空集群)。不连真实集群。
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import diagnostics_advanced as da


@pytest.fixture
def apis():
    core, net, storage = MagicMock(), MagicMock(), MagicMock()
    with patch.object(da, "prepare_context", return_value=None), \
         patch.object(da.client, "CoreV1Api", return_value=core), \
         patch.object(da.client, "NetworkingV1Api", return_value=net), \
         patch.object(da.client, "StorageV1Api", return_value=storage):
        yield core, net, storage


def _items(lst):
    return SimpleNamespace(items=lst)


def _pod(phase="Pending", conditions=None, containers=None, node_selector=None,
         tolerations=None, volumes=None, cstatuses=None, uid="self"):
    return SimpleNamespace(
        metadata=SimpleNamespace(name="p", namespace="default", uid=uid),
        status=SimpleNamespace(phase=phase, conditions=conditions,
                               container_statuses=cstatuses),
        spec=SimpleNamespace(containers=containers, node_selector=node_selector,
                             tolerations=tolerations, volumes=volumes),
    )


def _node(name="n1", cpu="8", mem="16Gi", pods="110", unschedulable=False,
          labels=None, taints=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, labels=labels or {}),
        spec=SimpleNamespace(unschedulable=unschedulable, taints=taints),
        status=SimpleNamespace(allocatable={"cpu": cpu, "memory": mem, "pods": pods}),
    )


class TestDiagnosePending:
    def test_not_pending_early_return(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.return_value = _pod(phase="Running")
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        assert "不是Pending" in out["diagnosis_summary"]

    def test_not_found_404(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "ghost", "namespace": "default", "config": {}}))
        assert "Pod不存在" in out["error"]

    def test_insufficient_resources(self, apis):
        core, _, _ = apis
        cond = SimpleNamespace(type="PodScheduled", status="False",
                               reason="Unschedulable", message="no fit")
        container = SimpleNamespace(resources=SimpleNamespace(
            requests={"cpu": "16", "memory": "32Gi"}))
        core.read_namespaced_pod.return_value = _pod(
            conditions=[cond], containers=[container])
        core.list_node.return_value = _items([_node(cpu="2", mem="4Gi")])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        cats = [i["category"] for i in out["issues"]]
        assert "scheduling" in cats and "resource" in cats
        assert out["pending_reason"] == "Unschedulable"

    def test_node_selector_no_match(self, apis):
        core, _, _ = apis
        container = SimpleNamespace(resources=None)
        core.read_namespaced_pod.return_value = _pod(
            containers=[container], node_selector={"disktype": "ssd"})
        core.list_node.return_value = _items([_node(labels={"disktype": "hdd"})])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        assert any(i["category"] == "affinity" for i in out["issues"])
        assert any("NodeSelector过于严格" in r for r in out["recommendations"])

    def test_taint_blocking(self, apis):
        core, _, _ = apis
        container = SimpleNamespace(resources=None)
        taint = SimpleNamespace(key="dedicated", value="gpu", effect="NoSchedule")
        core.read_namespaced_pod.return_value = _pod(
            containers=[container], tolerations=None)
        core.list_node.return_value = _items([_node(taints=[taint])])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        assert any(i["category"] == "taint" for i in out["issues"])

    def test_pvc_not_bound_and_missing(self, apis):
        core, _, _ = apis
        container = SimpleNamespace(resources=None)
        vol_unbound = SimpleNamespace(persistent_volume_claim=SimpleNamespace(
            claim_name="data"))
        vol_missing = SimpleNamespace(persistent_volume_claim=SimpleNamespace(
            claim_name="gone"))
        core.read_namespaced_pod.return_value = _pod(
            containers=[container], volumes=[vol_unbound, vol_missing])
        core.list_node.return_value = _items([_node()])
        core.list_pod_for_all_namespaces.return_value = _items([])

        def read_pvc(name, ns):
            if name == "data":
                return SimpleNamespace(status=SimpleNamespace(phase="Pending"))
            raise ApiException(status=404)
        core.read_namespaced_persistent_volume_claim.side_effect = read_pvc
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        msgs = [i["message"] for i in out["issues"] if i["category"] == "pvc"]
        assert any("PVC未绑定" in m for m in msgs)
        assert any("PVC不存在" in m for m in msgs)

    def test_image_pull_failure(self, apis):
        core, _, _ = apis
        container = SimpleNamespace(resources=None)
        cs = SimpleNamespace(name="c", state=SimpleNamespace(
            waiting=SimpleNamespace(reason="ImagePullBackOff", message="not found")))
        core.read_namespaced_pod.return_value = _pod(
            containers=[container], cstatuses=[cs])
        core.list_node.return_value = _items([_node()])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        assert any(i["category"] == "image" for i in out["issues"])

    def test_no_issues_summary(self, apis):
        core, _, _ = apis
        container = SimpleNamespace(resources=None)
        core.read_namespaced_pod.return_value = _pod(containers=[container])
        core.list_node.return_value = _items([_node()])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.diagnose_pending_pod_issues.invoke({
            "pod_name": "p", "namespace": "default", "config": {}}))
        assert "未发现明显问题" in out["diagnosis_summary"]


def _np(name, policy_types, pod_selector=None, egress=None, ingress=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        spec=SimpleNamespace(
            pod_selector=SimpleNamespace(match_labels=pod_selector or {}),
            policy_types=policy_types, egress=egress, ingress=ingress),
    )


class TestNetworkPolicies:
    def test_no_policies(self, apis):
        _, net, _ = apis
        net.list_namespaced_network_policy.return_value = _items([])
        out = json.loads(da.check_network_policies_blocking.invoke({
            "source_namespace": "src", "config": {}}))
        assert "未配置NetworkPolicy" in out["diagnosis_summary"]

    def test_default_deny_egress(self, apis):
        _, net, _ = apis
        np = _np("deny-egress", ["Egress"], egress=None)
        net.list_namespaced_network_policy.return_value = _items([np])
        out = json.loads(da.check_network_policies_blocking.invoke({
            "source_namespace": "src", "config": {}}))
        assert out["egress_blocked"] is True
        assert "出站Egress" in out["diagnosis_summary"]

    def test_default_deny_ingress_target(self, apis):
        _, net, _ = apis
        def list_np(ns):
            if ns == "src":
                return _items([])
            return _items([_np("deny-ingress", ["Ingress"], ingress=None)])
        net.list_namespaced_network_policy.side_effect = list_np
        out = json.loads(da.check_network_policies_blocking.invoke({
            "source_namespace": "src", "target_namespace": "dst", "config": {}}))
        assert out["ingress_blocked"] is True
        assert "入站Ingress" in out["diagnosis_summary"]

    def test_complex_policy_no_obvious_block(self, apis):
        _, net, _ = apis
        # egress defined -> not blocked
        np = _np("allow", ["Egress"], egress=[SimpleNamespace()])
        net.list_namespaced_network_policy.return_value = _items([np])
        out = json.loads(da.check_network_policies_blocking.invoke({
            "source_namespace": "src", "config": {}}))
        assert out["egress_blocked"] is False
        assert "未发现明显阻断" in out["diagnosis_summary"]

    def test_exception_wrapped(self, apis):
        _, net, _ = apis
        net.list_namespaced_network_policy.side_effect = RuntimeError("boom")
        out = json.loads(da.check_network_policies_blocking.invoke({
            "source_namespace": "src", "config": {}}))
        assert "检查失败" in out["error"]


def _pvc(name="pvc", ns="default", phase="Bound", capacity="10Gi", sc="standard"):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=ns),
        status=SimpleNamespace(phase=phase,
                               capacity={"storage": capacity} if capacity else None),
        spec=SimpleNamespace(storage_class_name=sc, access_modes=["ReadWriteOnce"]),
    )


class TestPvcCapacity:
    def test_bound_with_mount_mapping(self, apis):
        core, _, _ = apis
        core.list_persistent_volume_claim_for_all_namespaces.return_value = _items([
            _pvc(name="data")])
        vol = SimpleNamespace(persistent_volume_claim=SimpleNamespace(claim_name="data"))
        pod = SimpleNamespace(
            metadata=SimpleNamespace(name="webpod", namespace="default"),
            spec=SimpleNamespace(volumes=[vol]))
        core.list_pod_for_all_namespaces.return_value = _items([pod])
        out = json.loads(da.check_pvc_capacity.invoke({"config": {}}))
        assert out["total_pvcs"] == 1
        assert out["pvc_list"][0]["mounted_by"] == ["webpod"]

    def test_pending_pvc(self, apis):
        core, _, _ = apis
        core.list_persistent_volume_claim_for_all_namespaces.return_value = _items([
            _pvc(name="data", phase="Pending")])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.check_pvc_capacity.invoke({"config": {}}))
        assert len(out["pending_pvcs"]) == 1
        assert any("未绑定的PVC" in r for r in out["recommendations"])

    def test_namespace_scoped(self, apis):
        core, _, _ = apis
        core.list_namespaced_persistent_volume_claim.return_value = _items([_pvc()])
        core.list_namespaced_pod.return_value = _items([])
        out = json.loads(da.check_pvc_capacity.invoke({
            "namespace": "prod", "config": {}}))
        core.list_namespaced_persistent_volume_claim.assert_called_once_with("prod")
        assert out["total_pvcs"] == 1

    def test_empty_cluster(self, apis):
        core, _, _ = apis
        core.list_persistent_volume_claim_for_all_namespaces.return_value = _items([])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(da.check_pvc_capacity.invoke({"config": {}}))
        assert out["total_pvcs"] == 0
        assert any("没有PVC" in r for r in out["recommendations"])

    def test_exception_wrapped(self, apis):
        core, _, _ = apis
        core.list_persistent_volume_claim_for_all_namespaces.side_effect = \
            RuntimeError("boom")
        out = json.loads(da.check_pvc_capacity.invoke({"config": {}}))
        assert "检查失败" in out["error"]
