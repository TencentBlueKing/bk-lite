"""Kubernetes 链路追踪/事件分析 @tool 单元测试 (kubernetes/tracing)。

mock prepare_context 与 client.CoreV1Api/NetworkingV1Api,构造 Service/Endpoints/Pod/
Ingress/Event/容器 last_state。覆盖 trace_service_chain(无 selector / Service 缺失 /
无就绪 Endpoint / Pod 未就绪 / Ingress 匹配)、get_resource_events_timeline(时间窗口
过滤、类型统计、排序)、analyze_pod_restart_pattern(退出码 137/143/1、CrashLoopBackOff、
事件关联、阈值过滤、排序)、check_oom_events(OOM 事件与 OOMKilled Pod、内存配置提取)。
不连真实集群。
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import tracing as t

NOW = datetime.now(timezone.utc)
RECENT = NOW - timedelta(hours=1)
OLD = NOW - timedelta(hours=48)


@pytest.fixture
def apis():
    core, net = MagicMock(), MagicMock()
    with patch.object(t, "prepare_context", return_value=None), \
         patch.object(t.client, "CoreV1Api", return_value=core), \
         patch.object(t.client, "NetworkingV1Api", return_value=net):
        yield core, net


def _items(lst):
    return SimpleNamespace(items=lst)


def _svc(selector=None, type_="ClusterIP"):
    port = SimpleNamespace(name="http", port=80, target_port=8080, protocol="TCP")
    return SimpleNamespace(spec=SimpleNamespace(
        type=type_, cluster_ip="10.0.0.1", ports=[port], selector=selector))


def _addr(ip, kind="Pod", name="p"):
    return SimpleNamespace(ip=ip, target_ref=SimpleNamespace(kind=kind, name=name))


def _cstatus(name="c", ready=True, restart_count=0):
    return SimpleNamespace(name=name, ready=ready, restart_count=restart_count)


def _pod(name="p", phase="Running", cstatuses=None, ip="1.1.1.1", node="n1"):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace="default"),
        status=SimpleNamespace(phase=phase, container_statuses=cstatuses, pod_ip=ip),
        spec=SimpleNamespace(node_name=node),
    )


class TestTraceServiceChain:
    def test_service_not_found(self, apis):
        core, _ = apis
        core.read_namespaced_service.side_effect = ApiException(status=404)
        out = json.loads(t.trace_service_chain.invoke({
            "service_name": "svc", "namespace": "default", "config": {}}))
        assert out["chain"]["service"]["exists"] is False
        assert any(i["severity"] == "critical" for i in out["issues"])

    def test_no_selector(self, apis):
        core, net = apis
        core.read_namespaced_service.return_value = _svc(selector=None)
        core.read_namespaced_endpoints.return_value = SimpleNamespace(subsets=None)
        net.list_namespaced_ingress.return_value = _items([])
        out = json.loads(t.trace_service_chain.invoke({
            "service_name": "svc", "namespace": "default", "config": {}}))
        assert any("没有配置selector" in i["message"] for i in out["issues"])

    def test_healthy_full_chain(self, apis):
        core, net = apis
        core.read_namespaced_service.return_value = _svc(selector={"app": "x"})
        subset = SimpleNamespace(addresses=[_addr("1.1.1.1")], not_ready_addresses=None)
        core.read_namespaced_endpoints.return_value = SimpleNamespace(subsets=[subset])
        core.list_namespaced_pod.return_value = _items([
            _pod(cstatuses=[_cstatus(ready=True)])])
        net.list_namespaced_ingress.return_value = _items([])
        out = json.loads(t.trace_service_chain.invoke({
            "service_name": "svc", "namespace": "default", "config": {}}))
        assert out["health_status"] == "healthy"
        assert out["chain"]["endpoints"]["ready_count"] == 1

    def test_no_ready_endpoints_and_unready_pod(self, apis):
        core, net = apis
        core.read_namespaced_service.return_value = _svc(selector={"app": "x"})
        subset = SimpleNamespace(addresses=None,
                                 not_ready_addresses=[_addr("2.2.2.2")])
        core.read_namespaced_endpoints.return_value = SimpleNamespace(subsets=[subset])
        core.list_namespaced_pod.return_value = _items([
            _pod(phase="Pending", cstatuses=[_cstatus(ready=False)])])
        net.list_namespaced_ingress.return_value = _items([])
        out = json.loads(t.trace_service_chain.invoke({
            "service_name": "svc", "namespace": "default", "config": {}}))
        assert out["health_status"] == "critical"
        msgs = [i["message"] for i in out["issues"]]
        assert any("没有就绪的Endpoint" in m for m in msgs)
        assert any("未就绪" in m for m in msgs)

    def test_ingress_match(self, apis):
        core, net = apis
        core.read_namespaced_service.return_value = _svc(selector={"app": "x"})
        subset = SimpleNamespace(addresses=[_addr("1.1.1.1")], not_ready_addresses=None)
        core.read_namespaced_endpoints.return_value = SimpleNamespace(subsets=[subset])
        core.list_namespaced_pod.return_value = _items([
            _pod(cstatuses=[_cstatus(ready=True)])])
        path = SimpleNamespace(path="/", path_type="Prefix", backend=SimpleNamespace(
            service=SimpleNamespace(name="svc")))
        rule = SimpleNamespace(host="example.com",
                               http=SimpleNamespace(paths=[path]))
        ingress = SimpleNamespace(metadata=SimpleNamespace(name="ing"),
                                  spec=SimpleNamespace(rules=[rule]))
        net.list_namespaced_ingress.return_value = _items([ingress])
        out = json.loads(t.trace_service_chain.invoke({
            "service_name": "svc", "namespace": "default", "config": {}}))
        assert out["chain"]["ingress"]["exists"] is True
        assert out["chain"]["ingress"]["ingresses"][0]["host"] == "example.com"


class TestEventsTimeline:
    def test_time_filter_and_summary(self, apis):
        core, _ = apis
        recent = SimpleNamespace(
            type="Warning", reason="BackOff", message="m", count=2,
            last_timestamp=RECENT, first_timestamp=RECENT,
            metadata=SimpleNamespace(creation_timestamp=RECENT),
            source=SimpleNamespace(component="kubelet"))
        old = SimpleNamespace(
            type="Normal", reason="Pulled", message="m", count=1,
            last_timestamp=OLD, first_timestamp=OLD,
            metadata=SimpleNamespace(creation_timestamp=OLD),
            source=SimpleNamespace(component="kubelet"))
        core.list_namespaced_event.return_value = _items([recent, old])
        out = json.loads(t.get_resource_events_timeline.invoke({
            "resource_type": "Pod", "resource_name": "p", "namespace": "default",
            "hours": 24, "config": {}}))
        assert out["total_events"] == 1  # old event filtered out
        assert out["event_summary"]["Warning"] == 2

    def test_api_exception(self, apis):
        core, _ = apis
        core.list_namespaced_event.side_effect = ApiException(status=500)
        out = json.loads(t.get_resource_events_timeline.invoke({
            "resource_type": "Pod", "resource_name": "p", "namespace": "default",
            "config": {}}))
        assert "获取事件时间线失败" in out["error"]


def _term(reason="Error", exit_code=1, msg="m"):
    return SimpleNamespace(reason=reason, exit_code=exit_code, message=msg,
                           started_at=RECENT, finished_at=RECENT)


def _restart_cstatus(name="c", restarts=5, waiting=None, terminated=None,
                     running=None, last_term=None):
    state = SimpleNamespace(waiting=waiting, terminated=terminated, running=running)
    last_state = SimpleNamespace(terminated=last_term) if last_term else None
    return SimpleNamespace(name=name, restart_count=restarts, state=state,
                           last_state=last_state)


class TestRestartPattern:
    def test_oom_exit_137(self, apis):
        core, _ = apis
        cs = _restart_cstatus(restarts=5, waiting=SimpleNamespace(
            reason="CrashLoopBackOff", message="back"),
            last_term=_term(reason="OOMKilled", exit_code=137))
        pod = _pod(cstatuses=[cs])
        core.list_pod_for_all_namespaces.return_value = _items([pod])
        core.list_namespaced_event.return_value = _items([
            SimpleNamespace(reason="BackOff", message="m", count=3)])
        out = json.loads(t.analyze_pod_restart_pattern.invoke({"config": {}}))
        a = out["analysis"][0]
        assert a["restart_count"] == 5
        assert any("OOMKilled" in r for r in a["restart_reasons"])
        assert a["severity"] in ("high", "critical")
        assert a["recent_events"][0]["reason"] == "BackOff"

    def test_sigterm_143(self, apis):
        core, _ = apis
        cs = _restart_cstatus(restarts=4, terminated=SimpleNamespace(
            reason="Completed", exit_code=143, message="m"),
            last_term=_term(reason="Completed", exit_code=143))
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        core.list_namespaced_event.return_value = _items([])
        out = json.loads(t.analyze_pod_restart_pattern.invoke({"config": {}}))
        assert any("SIGTERM" in r for r in out["analysis"][0]["restart_reasons"])

    def test_below_threshold_skipped(self, apis):
        core, _ = apis
        cs = _restart_cstatus(restarts=1)
        core.list_pod_for_all_namespaces.return_value = _items([_pod(cstatuses=[cs])])
        out = json.loads(t.analyze_pod_restart_pattern.invoke({
            "min_restarts": 3, "config": {}}))
        assert out["total_problematic_containers"] == 0

    def test_namespace_scoped_and_sorted(self, apis):
        core, _ = apis
        cs_low = _restart_cstatus(name="low", restarts=3,
                                  last_term=_term(exit_code=1))
        cs_high = _restart_cstatus(name="high", restarts=12,
                                   last_term=_term(exit_code=1))
        pod = _pod(cstatuses=[cs_low, cs_high])
        core.list_namespaced_pod.return_value = _items([pod])
        core.list_namespaced_event.return_value = _items([])
        out = json.loads(t.analyze_pod_restart_pattern.invoke({
            "namespace": "prod", "config": {}}))
        core.list_namespaced_pod.assert_called_once_with("prod")
        # sorted desc by restart_count
        assert out["analysis"][0]["restart_count"] == 12
        assert any("重启次数过多" in r for r in out["analysis"][0]["recommendations"])

    def test_exception_wrapped(self, apis):
        core, _ = apis
        core.list_pod_for_all_namespaces.side_effect = RuntimeError("boom")
        out = json.loads(t.analyze_pod_restart_pattern.invoke({"config": {}}))
        assert "分析Pod重启模式失败" in out["error"]


class TestCheckOOM:
    def test_oom_events_and_pods(self, apis):
        core, _ = apis
        ev = SimpleNamespace(
            reason="OOMKilling", message="oom", count=2,
            last_timestamp=RECENT, first_timestamp=RECENT,
            metadata=SimpleNamespace(namespace="default", creation_timestamp=RECENT),
            involved_object=SimpleNamespace(name="p"))
        core.list_event_for_all_namespaces.return_value = _items([ev])
        spec_container = SimpleNamespace(name="c", resources=SimpleNamespace(
            limits={"memory": "256Mi"}, requests={"memory": "128Mi"}))
        cs = SimpleNamespace(name="c", restart_count=3,
                             last_state=SimpleNamespace(terminated=SimpleNamespace(
                                 reason="OOMKilled", finished_at=RECENT, exit_code=137)))
        pod = SimpleNamespace(
            metadata=SimpleNamespace(name="p", namespace="default"),
            status=SimpleNamespace(container_statuses=[cs]),
            spec=SimpleNamespace(containers=[spec_container]))
        core.list_pod_for_all_namespaces.return_value = _items([pod])
        out = json.loads(t.check_oom_events.invoke({"config": {}}))
        assert out["total_oom_events"] == 1
        assert out["total_oom_pods"] == 1
        assert out["oom_pods"][0]["memory_limit"] == "256Mi"
        assert any("VPA" in r for r in out["recommendations"])

    def test_namespace_scoped(self, apis):
        core, _ = apis
        core.list_namespaced_event.return_value = _items([])
        core.list_namespaced_pod.return_value = _items([])
        out = json.loads(t.check_oom_events.invoke({
            "namespace": "prod", "config": {}}))
        core.list_namespaced_event.assert_called_once_with("prod")
        assert out["namespace"] == "prod"
        assert out["total_oom_events"] == 0

    def test_exception_wrapped(self, apis):
        core, _ = apis
        core.list_event_for_all_namespaces.side_effect = RuntimeError("boom")
        out = json.loads(t.check_oom_events.invoke({"config": {}}))
        assert "检查OOM事件失败" in out["error"]
