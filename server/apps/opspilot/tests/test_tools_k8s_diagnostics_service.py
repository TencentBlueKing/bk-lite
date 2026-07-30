"""Kubernetes 故障诊断 @tool 单元测试 (kubernetes/diagnostics)。

mock prepare_context(kubeconfig 边界)与 client.CoreV1Api,用 SimpleNamespace
构造真实形态的 V1Pod/V1Node/V1Event 对象驱动各诊断工具,断言失败/Pending/高重启
Pod 识别、节点容量百分比计算、孤立资源过滤、单 Pod 深度诊断结构与 404/ApiException
包装。不连真实集群。
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import diagnostics as d


@pytest.fixture
def core():
    c = MagicMock()
    with patch.object(d, "prepare_context", return_value=None), \
         patch.object(d.client, "CoreV1Api", return_value=c):
        yield c


def _state(waiting=None, terminated=None, running=None):
    return SimpleNamespace(waiting=waiting, terminated=terminated, running=running)


def _cstatus(name="app", ready=False, restart_count=0, image="img:1", state=None,
             image_id="id"):
    return SimpleNamespace(name=name, ready=ready, restart_count=restart_count,
                           image=image, image_id=image_id, state=state or _state())


def _meta(name="p", ns="default", owner=None, ts=None):
    return SimpleNamespace(name=name, namespace=ns, owner_references=owner,
                           creation_timestamp=ts)


def _pod(name="p", ns="default", phase="Running", cstatuses=None, node="n1",
         message=None, reason=None, ts=None, conditions=None, owner=None,
         init_cstatuses=None, spec_containers=None, volumes=None,
         restart_policy="Always"):
    return SimpleNamespace(
        metadata=_meta(name, ns, owner, ts),
        status=SimpleNamespace(phase=phase, container_statuses=cstatuses,
                               message=message, reason=reason, conditions=conditions,
                               init_container_statuses=init_cstatuses),
        spec=SimpleNamespace(node_name=node, containers=spec_containers,
                             volumes=volumes, restart_policy=restart_policy),
    )


def _items(lst):
    return SimpleNamespace(items=lst)


class TestFailedPods:
    def test_waiting_crashloop_flagged(self, core):
        cs = _cstatus(state=_state(waiting=SimpleNamespace(
            reason="CrashLoopBackOff", message="boom")))
        core.list_pod_for_all_namespaces.return_value = _items([
            _pod(name="bad", cstatuses=[cs]),
        ])
        out = json.loads(d.get_failed_kubernetes_pods.invoke({"config": {}}))
        assert len(out) == 1
        assert out[0]["name"] == "bad"
        assert out[0]["container_statuses"][0]["state"]["reason"] == "CrashLoopBackOff"

    def test_terminated_nonzero_exit_flagged(self, core):
        cs = _cstatus(state=_state(terminated=SimpleNamespace(
            reason="Error", exit_code=137, message="oom")))
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(d.get_failed_kubernetes_pods.invoke({"config": {}}))
        assert out[0]["container_statuses"][0]["state"]["exit_code"] == 137

    def test_running_pod_not_flagged(self, core):
        started = datetime(2024, 1, 1, tzinfo=timezone.utc)
        cs = _cstatus(ready=True, state=_state(
            running=SimpleNamespace(started_at=started)))
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(d.get_failed_kubernetes_pods.invoke({"config": {}}))
        assert out == []

    def test_phase_failed_flagged(self, core):
        ts = datetime(2024, 5, 1, tzinfo=timezone.utc)
        core.list_pod_for_all_namespaces.return_value = _items([
            _pod(phase="Failed", cstatuses=None, ts=ts, message="m", reason="Evicted"),
        ])
        out = json.loads(d.get_failed_kubernetes_pods.invoke({"config": {}}))
        assert out[0]["phase"] == "Failed"
        assert out[0]["creation_time"] == ts.isoformat()

    def test_api_exception_wrapped(self, core):
        core.list_pod_for_all_namespaces.side_effect = ApiException(status=500)
        out = json.loads(d.get_failed_kubernetes_pods.invoke({"config": {}}))
        assert "error" in out


class TestPendingPods:
    def test_scheduling_failed_condition(self, core):
        cond = SimpleNamespace(type="PodScheduled", status="False",
                               reason="Unschedulable", message="no nodes")
        core.list_pod_for_all_namespaces.return_value = _items([
            _pod(phase="Pending", conditions=[cond], node=None),
        ])
        out = json.loads(d.get_pending_kubernetes_pods.invoke({"config": {}}))
        assert out[0]["reason"] == "Unschedulable"
        assert out[0]["message"] == "no nodes"

    def test_container_waiting_overrides(self, core):
        cs = _cstatus(state=_state(waiting=SimpleNamespace(
            reason="ContainerCreating", message="pulling")))
        core.list_pod_for_all_namespaces.return_value = _items([
            _pod(phase="Pending", cstatuses=[cs]),
        ])
        out = json.loads(d.get_pending_kubernetes_pods.invoke({"config": {}}))
        assert out[0]["reason"] == "ContainerCreating"

    def test_running_pod_skipped(self, core):
        core.list_pod_for_all_namespaces.return_value = _items([_pod(phase="Running")])
        out = json.loads(d.get_pending_kubernetes_pods.invoke({"config": {}}))
        assert out == []

    def test_api_exception_wrapped(self, core):
        core.list_pod_for_all_namespaces.side_effect = ApiException(status=500)
        out = json.loads(d.get_pending_kubernetes_pods.invoke({"config": {}}))
        assert "error" in out


class TestHighRestart:
    def test_above_threshold(self, core):
        cs = _cstatus(restart_count=7, ready=False)
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(d.get_high_restart_kubernetes_pods.invoke(
            {"restart_threshold": 5, "config": {}}))
        assert out[0]["containers"][0]["restart_count"] == 7

    def test_below_threshold_skipped(self, core):
        cs = _cstatus(restart_count=2)
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(d.get_high_restart_kubernetes_pods.invoke(
            {"restart_threshold": 5, "config": {}}))
        assert out == []

    def test_custom_threshold(self, core):
        cs = _cstatus(restart_count=3)
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(d.get_high_restart_kubernetes_pods.invoke(
            {"restart_threshold": 3, "config": {}}))
        assert len(out) == 1

    def test_string_threshold_is_coerced(self, core):
        cs = _cstatus(restart_count=3)
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(d.get_high_restart_kubernetes_pods.invoke(
            {"restart_threshold": "3", "config": {}}))
        assert len(out) == 1

    def test_api_exception_wrapped(self, core):
        core.list_pod_for_all_namespaces.side_effect = ApiException(status=500)
        out = json.loads(d.get_high_restart_kubernetes_pods.invoke({"config": {}}))
        assert "error" in out


class TestNodeCapacity:
    def test_percentages_computed(self, core):
        node = SimpleNamespace(
            metadata=SimpleNamespace(name="n1"),
            status=SimpleNamespace(
                allocatable={"cpu": "4", "memory": "8Gi", "pods": "10"},
                conditions=[SimpleNamespace(type="Ready", status="True",
                                            reason="KubeletReady", message="ok")],
            ),
        )
        container = SimpleNamespace(resources=SimpleNamespace(
            requests={"cpu": "2", "memory": "4Gi"}))
        pod = _pod(name="p1", node="n1", spec_containers=[container])
        core.list_node.return_value = _items([node])
        core.list_pod_for_all_namespaces.return_value = _items([pod])
        out = json.loads(d.get_kubernetes_node_capacity.invoke({"config": {}}))
        n = out[0]
        assert n["name"] == "n1"
        assert n["cpu"]["percent_used"] == 50.0
        assert n["memory"]["percent_used"] == 50.0
        assert n["pods"]["used"] == 1
        assert n["conditions"]["Ready"]["status"] == "True"

    def test_zero_allocatable_no_division_error(self, core):
        node = SimpleNamespace(
            metadata=SimpleNamespace(name="n2"),
            status=SimpleNamespace(allocatable={}, conditions=None),
        )
        core.list_node.return_value = _items([node])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(d.get_kubernetes_node_capacity.invoke({"config": {}}))
        assert out[0]["cpu"]["percent_used"] == 0

    def test_api_exception_wrapped(self, core):
        core.list_node.side_effect = ApiException(status=500)
        out = json.loads(d.get_kubernetes_node_capacity.invoke({"config": {}}))
        assert "error" in out


class TestOrphanedResources:
    def test_orphaned_filtering(self, core):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # orphan pod (no owner, not kube-system)
        orphan_pod = _pod(name="op", ns="prod", owner=None, ts=ts)
        sys_pod = _pod(name="sp", ns="kube-system", owner=None, ts=ts)
        owned_pod = _pod(name="wp", ns="prod", owner=[SimpleNamespace()], ts=ts)
        core.list_pod_for_all_namespaces.return_value = _items(
            [orphan_pod, sys_pod, owned_pod])
        # services: skip default kubernetes svc, keep orphan
        svc = SimpleNamespace(metadata=_meta("mysvc", "prod", None, ts))
        k8s_svc = SimpleNamespace(metadata=_meta("kubernetes", "default", None, ts))
        core.list_service_for_all_namespaces.return_value = _items([svc, k8s_svc])
        # pvc orphan
        pvc = SimpleNamespace(metadata=_meta("data", "prod", None, ts))
        core.list_persistent_volume_claim_for_all_namespaces.return_value = _items([pvc])
        # configmap: skip kube-root-ca.crt
        cm = SimpleNamespace(metadata=_meta("conf", "prod", None, ts))
        root_ca = SimpleNamespace(metadata=_meta("kube-root-ca.crt", "prod", None, ts))
        core.list_config_map_for_all_namespaces.return_value = _items([cm, root_ca])
        # secret: skip sa token type
        secret = SimpleNamespace(metadata=_meta("sec", "prod", None, ts),
                                 type="Opaque")
        sa_secret = SimpleNamespace(
            metadata=_meta("sa", "prod", None, ts),
            type="kubernetes.io/service-account-token")
        core.list_secret_for_all_namespaces.return_value = _items([secret, sa_secret])

        out = json.loads(d.get_kubernetes_orphaned_resources.invoke({"config": {}}))
        assert [p["name"] for p in out["pods"]] == ["op"]
        assert [s["name"] for s in out["services"]] == ["mysvc"]
        assert [p["name"] for p in out["persistent_volume_claims"]] == ["data"]
        assert [c["name"] for c in out["config_maps"]] == ["conf"]
        assert [s["name"] for s in out["secrets"]] == ["sec"]

    def test_api_exception_wrapped(self, core):
        core.list_pod_for_all_namespaces.side_effect = ApiException(status=500)
        out = json.loads(d.get_kubernetes_orphaned_resources.invoke({"config": {}}))
        assert "error" in out


class TestDiagnosePod:
    def test_full_diagnosis(self, core):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        cond = SimpleNamespace(type="Ready", status="False", reason="ContainersNotReady",
                               message="not ready", last_transition_time=ts)
        running_cs = _cstatus(name="app", ready=True, restart_count=1,
                              state=_state(running=SimpleNamespace(started_at=ts)))
        init_cs = SimpleNamespace(name="init", ready=True, restart_count=0, image="i",
                                  state=_state(terminated=SimpleNamespace(
                                      reason="Completed", exit_code=0)))
        spec_container = SimpleNamespace(
            name="app",
            resources=SimpleNamespace(requests={"cpu": "1"}, limits={"memory": "1Gi"}))
        vol_pvc = SimpleNamespace(name="v1",
                                  persistent_volume_claim=SimpleNamespace(claim_name="c"),
                                  config_map=None, secret=None, empty_dir=None,
                                  host_path=None)
        vol_host = SimpleNamespace(name="v2", persistent_volume_claim=None,
                                   config_map=None, secret=None, empty_dir=None,
                                   host_path=SimpleNamespace(path="/data"))
        pod = _pod(name="px", phase="Running", cstatuses=[running_cs],
                   conditions=[cond], init_cstatuses=[init_cs],
                   spec_containers=[spec_container], volumes=[vol_pvc, vol_host])
        core.read_namespaced_pod.return_value = pod
        ev = SimpleNamespace(type="Warning", reason="BackOff", message="failed",
                             count=3, last_timestamp=ts)
        core.list_namespaced_event.return_value = _items([ev])

        out = json.loads(d.diagnose_kubernetes_pod_issues.invoke(
            {"namespace": "default", "pod_name": "px", "config": {}}))
        assert out["phase"] == "Running"
        assert out["conditions"][0]["type"] == "Ready"
        assert out["containers"][0]["state"]["status"] == "running"
        assert out["init_containers"][0]["state"]["status"] == "terminated"
        assert out["resource_requests"]["app"] == {"cpu": "1"}
        assert out["resource_limits"]["app"] == {"memory": "1Gi"}
        vol_types = {v["name"]: v["type"] for v in out["volumes"]}
        assert vol_types == {"v1": "pvc", "v2": "hostpath"}
        assert out["recent_events"][0]["reason"] == "BackOff"

    def test_recent_events_sort_handles_aware_and_missing_timestamps(self, core):
        older = datetime(2024, 1, 1, tzinfo=timezone.utc)
        newer = datetime(2024, 1, 2, tzinfo=timezone.utc)
        core.read_namespaced_pod.return_value = _pod(name="px")
        core.list_namespaced_event.return_value = _items([
            SimpleNamespace(
                type="Normal",
                reason="NoTimestamp",
                message="missing",
                count=1,
                last_timestamp=None,
            ),
            SimpleNamespace(
                type="Warning",
                reason="Older",
                message="old",
                count=1,
                last_timestamp=older,
            ),
            SimpleNamespace(
                type="Warning",
                reason="Newer",
                message="new",
                count=1,
                last_timestamp=newer,
            ),
        ])

        out = json.loads(d.diagnose_kubernetes_pod_issues.invoke(
            {"namespace": "default", "pod_name": "px", "config": {}}
        ))

        assert [event["reason"] for event in out["recent_events"]] == [
            "Newer",
            "Older",
            "NoTimestamp",
        ]
        assert [event["last_timestamp"] for event in out["recent_events"]] == [
            newer.isoformat(),
            older.isoformat(),
            None,
        ]

    def test_pod_not_found_404(self, core):
        core.read_namespaced_pod.side_effect = ApiException(status=404)
        out = json.loads(d.diagnose_kubernetes_pod_issues.invoke(
            {"namespace": "default", "pod_name": "ghost", "config": {}}))
        assert "不存在" in out["error"]

    def test_other_api_error_wrapped(self, core):
        core.read_namespaced_pod.side_effect = ApiException(status=500)
        out = json.loads(d.diagnose_kubernetes_pod_issues.invoke(
            {"namespace": "default", "pod_name": "x", "config": {}}))
        assert "诊断Pod失败" in out["error"]
