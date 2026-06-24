"""Kubernetes 批量操作 @tool 单元测试 (kubernetes/batch_operations)。

mock prepare_context 与 client.CoreV1Api,构造 V1Pod 列表驱动 batch_restart_pods /
find_configmap_consumers / cleanup_failed_pods。覆盖参数校验、label/pod_names 选择、
孤立 Pod 跳过、删除成功/失败统计、wait_for_ready 就绪轮询(patch time)、ConfigMap
volume/subPath/env 消费者识别与建议、Failed/Succeeded 清理过滤与异常包装。
另测纯 helper _check_volume_uses_configmap / _check_env_uses_configmap。不连真实集群。
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import batch_operations as b


@pytest.fixture
def core():
    c = MagicMock()
    with patch.object(b, "prepare_context", return_value=None), \
         patch.object(b.client, "CoreV1Api", return_value=c):
        yield c


def _pod(name="p", ns="default", phase="Running", owner=True, uid="u1",
         volumes=None, containers=None, reason=None, cstatuses=None):
    owner_refs = [SimpleNamespace(kind="ReplicaSet", name="rs")] if owner else None
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=ns, uid=uid,
                                 owner_references=owner_refs),
        status=SimpleNamespace(phase=phase, reason=reason,
                               container_statuses=cstatuses),
        spec=SimpleNamespace(volumes=volumes, containers=containers),
    )


def _items(lst):
    return SimpleNamespace(items=lst)


# ---------------- pure helpers ----------------
class TestConfigMapHelpers:
    def test_volume_uses_configmap_with_subpath(self):
        vol = SimpleNamespace(name="v", config_map=SimpleNamespace(name="cm"))
        vm = SimpleNamespace(name="v", sub_path="cfg.yaml")
        container = SimpleNamespace(volume_mounts=[vm])
        pod = _pod(volumes=[vol], containers=[container])
        uses, subpath = b._check_volume_uses_configmap(pod, "cm")
        assert uses is True and subpath is True

    def test_volume_uses_configmap_no_subpath(self):
        vol = SimpleNamespace(name="v", config_map=SimpleNamespace(name="cm"))
        vm = SimpleNamespace(name="v", sub_path=None)
        container = SimpleNamespace(volume_mounts=[vm])
        pod = _pod(volumes=[vol], containers=[container])
        uses, subpath = b._check_volume_uses_configmap(pod, "cm")
        assert uses is True and subpath is False

    def test_volume_no_volumes(self):
        pod = _pod(volumes=None)
        assert b._check_volume_uses_configmap(pod, "cm") == (False, False)

    def test_env_uses_configmap(self):
        ref = SimpleNamespace(config_map_key_ref=SimpleNamespace(name="cm"))
        env = SimpleNamespace(value_from=ref)
        container = SimpleNamespace(env=[env])
        pod = _pod(containers=[container])
        assert b._check_env_uses_configmap(pod, "cm") is True

    def test_env_not_referencing(self):
        env = SimpleNamespace(value_from=None)
        container = SimpleNamespace(env=[env])
        pod = _pod(containers=[container])
        assert b._check_env_uses_configmap(pod, "cm") is False


# ---------------- batch_restart_pods ----------------
class TestBatchRestart:
    def test_no_selector_or_names(self, core):
        out = json.loads(b.batch_restart_pods.invoke({"namespace": "p", "config": {}}))
        assert "label_selector 或 pod_names" in out["error"]

    def test_label_selector_restart_and_skip_orphan(self, core):
        owned = _pod(name="owned", owner=True, uid="a")
        orphan = _pod(name="orphan", owner=False, uid="b")
        core.list_namespaced_pod.return_value = _items([owned, orphan])
        out = json.loads(b.batch_restart_pods.invoke({
            "namespace": "prod", "label_selector": "app=x", "config": {}}))
        assert out["total_pods"] == 2
        assert [p["pod_name"] for p in out["restarted_pods"]] == ["owned"]
        assert [p["pod_name"] for p in out["skipped_pods"]] == ["orphan"]
        core.delete_namespaced_pod.assert_called_once()

    def test_pod_names_with_missing_404(self, core):
        def read(name, ns):
            if name == "gone":
                raise ApiException(status=404)
            return _pod(name=name, owner=True)
        core.read_namespaced_pod.side_effect = read
        out = json.loads(b.batch_restart_pods.invoke({
            "namespace": "prod", "pod_names": ["live", "gone"], "config": {}}))
        assert out["total_pods"] == 1
        assert out["restarted_pods"][0]["pod_name"] == "live"

    def test_no_matching_pods(self, core):
        core.list_namespaced_pod.return_value = _items([])
        out = json.loads(b.batch_restart_pods.invoke({
            "namespace": "prod", "label_selector": "app=none", "config": {}}))
        assert out["message"] == "没有找到匹配的Pod"

    def test_delete_failure_recorded(self, core):
        core.list_namespaced_pod.return_value = _items([_pod(owner=True)])
        core.delete_namespaced_pod.side_effect = ApiException(status=500)
        out = json.loads(b.batch_restart_pods.invoke({
            "namespace": "prod", "label_selector": "a=b", "config": {}}))
        assert len(out["failed_pods"]) == 1

    def test_wait_for_ready(self, core):
        pod = _pod(name="w", owner=True, uid="old")
        core.list_namespaced_pod.return_value = _items([pod])
        new_pod = _pod(name="w", owner=True, uid="new",
                       cstatuses=[SimpleNamespace(ready=True)])
        new_pod.status.phase = "Running"
        core.read_namespaced_pod.return_value = new_pod
        with patch.object(b.time, "sleep", return_value=None), \
             patch.object(b.time, "time", side_effect=[0, 0, 1]):
            out = json.loads(b.batch_restart_pods.invoke({
                "namespace": "prod", "label_selector": "a=b",
                "wait_for_ready": True, "config": {}}))
        assert out["all_ready"] is True
        assert out["ready_count"] == 1

    def test_generic_exception_wrapped(self, core):
        core.list_namespaced_pod.side_effect = RuntimeError("boom")
        out = json.loads(b.batch_restart_pods.invoke({
            "namespace": "prod", "label_selector": "a=b", "config": {}}))
        assert "批量重启失败" in out["error"]


# ---------------- find_configmap_consumers ----------------
class TestFindConfigMapConsumers:
    def test_configmap_not_found(self, core):
        core.read_namespaced_config_map.side_effect = ApiException(status=404)
        out = json.loads(b.find_configmap_consumers.invoke({
            "configmap_name": "cm", "namespace": "prod", "config": {}}))
        assert out["configmap_exists"] is False
        assert "不存在" in out["message"]

    def test_consumers_volume_and_env(self, core):
        core.read_namespaced_config_map.return_value = SimpleNamespace()
        # volume + subpath pod
        vol = SimpleNamespace(name="v", config_map=SimpleNamespace(name="cm"))
        vm = SimpleNamespace(name="v", sub_path="x")
        sub_pod = _pod(name="subp", owner=True,
                       volumes=[vol], containers=[SimpleNamespace(
                           volume_mounts=[vm], env=None)])
        # env pod
        ref = SimpleNamespace(config_map_key_ref=SimpleNamespace(name="cm"))
        env_pod = _pod(name="envp", owner=True, volumes=None,
                       containers=[SimpleNamespace(
                           volume_mounts=[], env=[SimpleNamespace(value_from=ref)])])
        # unrelated pod
        other = _pod(name="other", owner=True, volumes=None,
                     containers=[SimpleNamespace(volume_mounts=[], env=None)])
        core.list_namespaced_pod.return_value = _items([sub_pod, env_pod, other])
        out = json.loads(b.find_configmap_consumers.invoke({
            "configmap_name": "cm", "namespace": "prod", "config": {}}))
        assert out["total_consumers"] == 2
        names = {c["pod_name"] for c in out["consumers"]}
        assert names == {"subp", "envp"}
        assert all(c["needs_restart"] for c in out["consumers"])
        assert "ReplicaSet/rs" in out["affected_controllers"]

    def test_no_consumers_recommendation(self, core):
        core.read_namespaced_config_map.return_value = SimpleNamespace()
        pod = _pod(name="x", volumes=None,
                   containers=[SimpleNamespace(volume_mounts=[], env=None)])
        core.list_namespaced_pod.return_value = _items([pod])
        out = json.loads(b.find_configmap_consumers.invoke({
            "configmap_name": "cm", "namespace": "prod", "config": {}}))
        assert out["total_consumers"] == 0
        assert any("可以安全修改或删除" in r for r in out["recommendations"])

    def test_volume_no_subpath_auto_update(self, core):
        core.read_namespaced_config_map.return_value = SimpleNamespace()
        vol = SimpleNamespace(name="v", config_map=SimpleNamespace(name="cm"))
        vm = SimpleNamespace(name="v", sub_path=None)
        pod = _pod(name="vp", owner=True, volumes=[vol],
                   containers=[SimpleNamespace(volume_mounts=[vm], env=None)])
        core.list_namespaced_pod.return_value = _items([pod])
        out = json.loads(b.find_configmap_consumers.invoke({
            "configmap_name": "cm", "namespace": "prod", "config": {}}))
        assert out["consumers"][0]["needs_restart"] is False
        assert any("自动生效" in r for r in out["recommendations"])

    def test_exception_wrapped(self, core):
        core.read_namespaced_config_map.side_effect = RuntimeError("boom")
        out = json.loads(b.find_configmap_consumers.invoke({
            "configmap_name": "cm", "namespace": "prod", "config": {}}))
        assert "查找失败" in out["error"]


# ---------------- cleanup_failed_pods ----------------
class TestCleanupFailedPods:
    def test_cleans_failed_and_succeeded(self, core):
        failed = _pod(name="f", phase="Failed")
        done = _pod(name="d", phase="Succeeded")
        running = _pod(name="r", phase="Running")
        core.list_pod_for_all_namespaces.return_value = _items([failed, done, running])
        out = json.loads(b.cleanup_failed_pods.invoke({"config": {}}))
        cleaned = {p["name"]: p["reason"] for p in out["cleaned_pods"]}
        assert cleaned == {"f": "Failed", "d": "Completed"}
        assert out["total_cleaned"] == 2

    def test_namespace_scoped(self, core):
        core.list_namespaced_pod.return_value = _items([_pod(name="f", phase="Failed")])
        out = json.loads(b.cleanup_failed_pods.invoke({
            "namespace": "prod", "config": {}}))
        core.list_namespaced_pod.assert_called_once_with("prod")
        assert out["namespace"] == "prod"

    def test_no_pods_to_clean(self, core):
        core.list_pod_for_all_namespaces.return_value = _items(
            [_pod(name="r", phase="Running")])
        out = json.loads(b.cleanup_failed_pods.invoke({"config": {}}))
        assert out["message"] == "没有需要清理的Pod"

    def test_delete_failure_counted(self, core):
        core.list_pod_for_all_namespaces.return_value = _items(
            [_pod(name="f", phase="Failed")])
        core.delete_namespaced_pod.side_effect = ApiException(status=500)
        out = json.loads(b.cleanup_failed_pods.invoke({"config": {}}))
        assert out["total_failed"] == 1
        assert out["total_cleaned"] == 0

    def test_exception_wrapped(self, core):
        core.list_pod_for_all_namespaces.side_effect = RuntimeError("boom")
        out = json.loads(b.cleanup_failed_pods.invoke({"config": {}}))
        assert "批量清理失败" in out["error"]
