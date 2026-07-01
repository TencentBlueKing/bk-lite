"""Kubernetes 故障自愈/操作类 @tool 单元测试 (kubernetes/remediation)。

mock prepare_context 与 client.CoreV1Api/AppsV1Api,patch time 控制轮询循环。覆盖
restart_pod(404/删除失败/wait 就绪)、scale_deployment(Deployment/StatefulSet 分派
与都不存在)、get_deployment_revision_history(版本聚合排序/404)、rollback_deployment
(自动上版本/指定版本/无历史/目标 RS 缺失)、delete_kubernetes_resource(各类型分派/
不支持/404)、wait_for_pod_ready(就绪/失败态/超时/不存在)。不连真实集群。
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import remediation as r


@pytest.fixture
def apis():
    core, apps = MagicMock(), MagicMock()
    with patch.object(r, "prepare_context", return_value=None), \
         patch.object(r.client, "CoreV1Api", return_value=core), \
         patch.object(r.client, "AppsV1Api", return_value=apps):
        yield core, apps


def _pod(uid="u1", phase="Running", ready=None, owner=True, ip="1.2.3.4", node="n1"):
    owner_refs = [SimpleNamespace(kind="ReplicaSet", name="rs", uid="o1")] if owner else None
    cstatuses = None
    if ready is not None:
        cstatuses = [SimpleNamespace(ready=ready)]
    return SimpleNamespace(
        metadata=SimpleNamespace(name="p", namespace="default", uid=uid,
                                 owner_references=owner_refs),
        status=SimpleNamespace(phase=phase, container_statuses=cstatuses, pod_ip=ip),
        spec=SimpleNamespace(node_name=node),
    )


class TestRestartPod:
    def test_not_found(self, apis):
        core, _ = apis
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        out = json.loads(r.restart_pod.invoke({
            "pod_name": "p", "namespace": "default", "wait_for_ready": False,
            "config": {}}))
        assert out["success"] is False and "Pod不存在" in out["error"]

    def test_delete_failure(self, apis):
        core, _ = apis
        core.read_namespaced_pod.return_value = _pod()
        core.delete_namespaced_pod.side_effect = ApiException(status=500)
        out = json.loads(r.restart_pod.invoke({
            "pod_name": "p", "namespace": "default", "wait_for_ready": False,
            "config": {}}))
        assert "删除Pod失败" in out["error"]

    def test_no_wait_success(self, apis):
        core, _ = apis
        core.read_namespaced_pod.return_value = _pod(uid="old")
        out = json.loads(r.restart_pod.invoke({
            "pod_name": "p", "namespace": "default", "wait_for_ready": False,
            "config": {}}))
        assert out["success"] is True
        assert out["old_pod_uid"] == "old"
        assert out["owner_controller"]["kind"] == "ReplicaSet"

    def test_wait_for_ready_success(self, apis):
        core, _ = apis
        core.read_namespaced_pod.side_effect = [
            _pod(uid="old"),  # initial read
            _pod(uid="new", ready=True),  # poll read
        ]
        with patch.object(r.time, "sleep", return_value=None), \
             patch.object(r.time, "time", side_effect=[0, 0, 1]):
            out = json.loads(r.restart_pod.invoke({
                "pod_name": "p", "namespace": "default", "wait_for_ready": True,
                "config": {}}))
        assert out["new_pod_status"] == "ready"
        assert out["new_pod_uid"] == "new"

    def test_wait_timeout(self, apis):
        core, _ = apis
        core.read_namespaced_pod.side_effect = [_pod(uid="old"),
                                                _pod(uid="old")]  # never replaced
        with patch.object(r.time, "sleep", return_value=None), \
             patch.object(r.time, "time", side_effect=[0, 0, 5, 100]):
            out = json.loads(r.restart_pod.invoke({
                "pod_name": "p", "namespace": "default", "wait_for_ready": True,
                "timeout": 3, "config": {}}))
        assert out["new_pod_status"] == "not_ready"


class TestScaleDeployment:
    def test_scale_deployment_up(self, apis):
        _, apps = apis
        dep = SimpleNamespace(spec=SimpleNamespace(replicas=1))
        apps.read_namespaced_deployment.return_value = dep
        out = json.loads(r.scale_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "replicas": 3,
            "config": {}}))
        assert out["resource_type"] == "Deployment"
        assert out["operation"] == "scale_up"
        assert out["previous_replicas"] == 1
        assert dep.spec.replicas == 3
        apps.patch_namespaced_deployment.assert_called_once()

    def test_fallback_to_statefulset(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        ss = SimpleNamespace(spec=SimpleNamespace(replicas=5))
        apps.read_namespaced_stateful_set.return_value = ss
        out = json.loads(r.scale_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "replicas": 2,
            "config": {}}))
        assert out["resource_type"] == "StatefulSet"
        assert out["operation"] == "scale_down"
        apps.patch_namespaced_stateful_set.assert_called_once()

    def test_neither_found(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        apps.read_namespaced_stateful_set.side_effect = ApiException(status=404)
        out = json.loads(r.scale_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "replicas": 2,
            "config": {}}))
        assert "未找到Deployment或StatefulSet" in out["error"]


def _deployment(revision="3"):
    return SimpleNamespace(
        metadata=SimpleNamespace(annotations={"deployment.kubernetes.io/revision": revision}),
        spec=SimpleNamespace(
            selector=SimpleNamespace(match_labels={"app": "x"}),
            revision_history_limit=10,
            template=None,
        ),
        status=SimpleNamespace(conditions=None),
    )


def _rs(name, revision, image="img:1"):
    container = SimpleNamespace(image=image)
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name, annotations={"deployment.kubernetes.io/revision": str(revision)},
            creation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc)),
        spec=SimpleNamespace(replicas=2,
                             template=SimpleNamespace(spec=SimpleNamespace(
                                 containers=[container]))),
        status=SimpleNamespace(ready_replicas=2),
    )


class TestRevisionHistory:
    def test_history_sorted(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deployment("3")
        apps.list_namespaced_replica_set.return_value = SimpleNamespace(
            items=[_rs("rs1", 1), _rs("rs3", 3), _rs("rs2", 2)])
        out = json.loads(r.get_deployment_revision_history.invoke({
            "deployment_name": "d", "namespace": "default", "config": {}}))
        assert out["total_revisions"] == 3
        assert [rv["revision"] for rv in out["revisions"]] == [3, 2, 1]
        assert out["current_revision"] == 3

    def test_not_found(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        out = json.loads(r.get_deployment_revision_history.invoke({
            "deployment_name": "d", "namespace": "default", "config": {}}))
        assert "Deployment不存在" in out["error"]


class TestRollback:
    def test_rollback_to_previous(self, apis):
        _, apps = apis
        dep = _deployment("3")
        apps.read_namespaced_deployment.return_value = dep
        apps.list_namespaced_replica_set.return_value = SimpleNamespace(
            items=[_rs("rs3", 3, "img:3"), _rs("rs2", 2, "img:2")])
        out = json.loads(r.rollback_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "config": {}}))
        assert out["success"] is True
        assert out["target_revision"] == 2  # previous = second highest
        assert out["target_image"] == "img:2"
        apps.patch_namespaced_deployment.assert_called_once()

    def test_rollback_specific_revision_unbound_bug(self, apis):
        # BUG(remediation.py): 显式指定 revision 时跳过了 replica_sets 的获取
        # (它在 `if revision is None` 分支内),后续 line 518 迭代 replica_sets.items
        # 触发 UnboundLocalError,被外层捕获包装为 "回滚失败"。即指定版本回滚永远失败。
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deployment("3")
        apps.list_namespaced_replica_set.return_value = SimpleNamespace(
            items=[_rs("rs1", 1, "img:1"), _rs("rs3", 3, "img:3")])
        out = json.loads(r.rollback_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "revision": 1,
            "config": {}}))
        assert out["success"] is False
        assert "replica_sets" in out["error"]

    def test_no_history_to_rollback(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deployment("1")
        apps.list_namespaced_replica_set.return_value = SimpleNamespace(
            items=[_rs("rs1", 1)])
        out = json.loads(r.rollback_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "config": {}}))
        assert "没有可回滚的历史版本" in out["error"]

    def test_target_revision_missing_also_hits_unbound_bug(self, apis):
        # 同上:显式 revision 路径在到达 "未找到revision" 校验前即因 replica_sets 未绑定失败。
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deployment("3")
        apps.list_namespaced_replica_set.return_value = SimpleNamespace(
            items=[_rs("rs3", 3)])
        out = json.loads(r.rollback_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "revision": 99,
            "config": {}}))
        assert out["success"] is False
        assert "replica_sets" in out["error"]

    def test_deployment_not_found(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        out = json.loads(r.rollback_deployment.invoke({
            "deployment_name": "d", "namespace": "default", "config": {}}))
        assert "Deployment不存在" in out["error"]


class TestDeleteResource:
    @pytest.mark.parametrize("rtype,api_attr", [
        ("pod", "delete_namespaced_pod"),
        ("service", "delete_namespaced_service"),
        ("configmap", "delete_namespaced_config_map"),
        ("secret", "delete_namespaced_secret"),
    ])
    def test_delete_core_types(self, apis, rtype, api_attr):
        core, _ = apis
        out = json.loads(r.delete_kubernetes_resource.invoke({
            "resource_type": rtype, "resource_name": "x", "namespace": "default",
            "config": {}}))
        assert out["success"] is True
        assert out["resource_type"] == rtype
        getattr(core, api_attr).assert_called_once()

    def test_delete_deployment(self, apis):
        _, apps = apis
        out = json.loads(r.delete_kubernetes_resource.invoke({
            "resource_type": "deployment", "resource_name": "d",
            "namespace": "default", "config": {}}))
        assert out["success"] is True
        apps.delete_namespaced_deployment.assert_called_once()

    def test_unsupported_type(self, apis):
        out = json.loads(r.delete_kubernetes_resource.invoke({
            "resource_type": "widget", "resource_name": "x", "namespace": "default",
            "config": {}}))
        assert out["success"] is False
        assert "不支持的资源类型" in out["error"]

    def test_delete_404(self, apis):
        core, _ = apis
        core.delete_namespaced_pod.side_effect = ApiException(status=404)
        out = json.loads(r.delete_kubernetes_resource.invoke({
            "resource_type": "pod", "resource_name": "x", "namespace": "default",
            "config": {}}))
        assert "资源不存在" in out["error"]


class TestWaitForPodReady:
    def test_ready(self, apis):
        core, _ = apis
        core.read_namespaced_pod.return_value = _pod(phase="Running", ready=True)
        with patch.object(r.time, "sleep", return_value=None), \
             patch.object(r.time, "time", side_effect=[0, 0, 1]):
            out = json.loads(r.wait_for_pod_ready.invoke({
                "pod_name": "p", "namespace": "default", "config": {}}))
        assert out["status"] == "ready"
        assert out["pod_ip"] == "1.2.3.4"

    def test_failed_phase(self, apis):
        core, _ = apis
        core.read_namespaced_pod.return_value = _pod(phase="Failed")
        with patch.object(r.time, "time", side_effect=[0, 0, 1]):
            out = json.loads(r.wait_for_pod_ready.invoke({
                "pod_name": "p", "namespace": "default", "config": {}}))
        assert out["status"] == "Failed"

    def test_not_found(self, apis):
        core, _ = apis
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        with patch.object(r.time, "time", side_effect=[0, 0, 1]):
            out = json.loads(r.wait_for_pod_ready.invoke({
                "pod_name": "p", "namespace": "default", "config": {}}))
        assert "Pod不存在" in out["error"]

    def test_timeout(self, apis):
        core, _ = apis
        core.read_namespaced_pod.return_value = _pod(phase="Pending")
        with patch.object(r.time, "sleep", return_value=None), \
             patch.object(r.time, "time", side_effect=[0, 0, 5, 100]):
            out = json.loads(r.wait_for_pod_ready.invoke({
                "pod_name": "p", "namespace": "default", "timeout": 3, "config": {}}))
        assert out["status"] == "timeout"
