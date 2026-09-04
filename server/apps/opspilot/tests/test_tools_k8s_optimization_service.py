"""Kubernetes 配置优化建议 @tool 单元测试 (kubernetes/optimization)。

mock prepare_context 与 client.CoreV1Api/AppsV1Api,构造节点/Pod/Deployment/RS。覆盖
check_scaling_capacity(Ready/unschedulable 过滤、CPU/内存/Pod 不足、仅 Pod 容量分支、
紧张预警)、check_pod_distribution(单节点单点故障/不均匀/单可用区/StatefulSet 回退/
都不存在)、validate_probe_configuration(探针缺失/initialDelay=0/评分/404、httpGet.path)、
compare_deployment_revisions(镜像/env/副本差异、revision 缺失)。另测 _get_probe_type。
不连真实集群。
"""

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import optimization as o

_PROBE_BODY_SENTINEL = "K8S_PROBE_404_BODY_SENTINEL"
_PROBE_HEADER_SENTINEL = "K8S_PROBE_404_HEADER_SENTINEL"


class _ApiHttpResp:
    def __init__(self, status, body, reason="Not Found"):
        self.status = status
        self.reason = reason
        self.data = body

    def getheaders(self):
        return {"Audit-Id": _PROBE_HEADER_SENTINEL}


def _api_http_error(status, body, reason="Not Found"):
    return ApiException(http_resp=_ApiHttpResp(status, body, reason=reason))


@pytest.fixture
def apis():
    core, apps = MagicMock(), MagicMock()
    with patch.object(o, "prepare_context", return_value=None), patch.object(o.client, "CoreV1Api", return_value=core), patch.object(
        o.client, "AppsV1Api", return_value=apps
    ):
        yield core, apps


def _node(name="n1", ready=True, unschedulable=False, cpu="8", mem="16Gi", pods="110", labels=None):
    cond = SimpleNamespace(type="Ready", status="True" if ready else "False")
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, labels=labels or {}),
        spec=SimpleNamespace(unschedulable=unschedulable),
        status=SimpleNamespace(conditions=[cond], allocatable={"cpu": cpu, "memory": mem, "pods": pods}),
    )


def _pod(name="p", node="n1", phase="Running", cpu=None, mem=None):
    container = SimpleNamespace(resources=SimpleNamespace(requests={"cpu": cpu, "memory": mem} if cpu or mem else None))
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        status=SimpleNamespace(phase=phase),
        spec=SimpleNamespace(node_name=node, containers=[container]),
    )


def _items(lst):
    return SimpleNamespace(items=lst)


class TestScalingCapacity:
    def test_only_ready_schedulable_nodes(self, apis):
        core, _ = apis
        core.list_node.return_value = _items(
            [
                _node("ready1"),
                _node("notready", ready=False),
                _node("cordoned", unschedulable=True),
            ]
        )
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(o.check_scaling_capacity.invoke({"namespace": "p", "replicas": 2, "config": {}}))
        assert out["total_nodes"] == 1
        assert out["node_capacity"][0]["node_name"] == "ready1"

    def test_cpu_insufficient(self, apis):
        core, _ = apis
        core.list_node.return_value = _items([_node("n1", cpu="2", mem="4Gi")])
        core.list_pod_for_all_namespaces.return_value = _items([])
        out = json.loads(
            o.check_scaling_capacity.invoke({"namespace": "p", "replicas": 5, "resource_requirements": {"cpu": "1", "memory": "100Mi"}, "config": {}})
        )
        assert out["can_scale"] is False
        assert any("CPU资源不足" in r for r in out["recommendations"])

    def test_can_scale_with_warning(self, apis):
        core, _ = apis
        core.list_node.return_value = _items([_node("n1", cpu="10", mem="10Gi")])
        core.list_pod_for_all_namespaces.return_value = _items([])
        # require 9 cpu of 10 available -> >80% warning
        out = json.loads(
            o.check_scaling_capacity.invoke({"namespace": "p", "replicas": 9, "resource_requirements": {"cpu": "1", "memory": "100Mi"}, "config": {}})
        )
        assert out["can_scale"] is True
        assert any("CPU利用率将超过80%" in r for r in out["recommendations"])

    def test_pod_capacity_only_branch(self, apis):
        core, _ = apis
        core.list_node.return_value = _items([_node("n1", pods="5")])
        # 4 pods already on node
        existing = [_pod(name=f"e{i}") for i in range(4)]
        core.list_pod_for_all_namespaces.return_value = _items(existing)
        out = json.loads(o.check_scaling_capacity.invoke({"namespace": "p", "replicas": 3, "config": {}}))
        # available pods = 5-4 = 1 < 3
        assert out["can_scale"] is False
        assert any("Pod容量不足" in r for r in out["recommendations"])

    def test_string_replicas_are_coerced(self, apis):
        core, _ = apis
        core.list_node.return_value = _items([_node("n1", pods="5")])
        existing = [_pod(name=f"e{i}") for i in range(4)]
        core.list_pod_for_all_namespaces.return_value = _items(existing)
        out = json.loads(o.check_scaling_capacity.func(namespace="p", replicas="3", config={}))
        assert out["can_scale"] is False
        assert out["requested_replicas"] == 3

    def test_exception_wrapped(self, apis):
        core, _ = apis
        core.list_node.side_effect = RuntimeError("boom")
        out = json.loads(o.check_scaling_capacity.invoke({"namespace": "p", "replicas": 1, "config": {}}))
        assert "检查扩容容量失败" in out["error"]


def _deploy(labels=None):
    return SimpleNamespace(spec=SimpleNamespace(selector=SimpleNamespace(match_labels=labels or {"app": "x"})))


class TestPodDistribution:
    def test_single_node_spof(self, apis):
        core, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        pods = [_pod(name="p1", node="n1"), _pod(name="p2", node="n1")]
        core.list_namespaced_pod.return_value = _items(pods)
        core.list_node.return_value = _items([_node("n1")])
        out = json.loads(o.check_pod_distribution.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert any(i["severity"] == "high" for i in out["issues"])
        assert out["distribution_score"] == "needs_improvement"

    def test_uneven_distribution(self, apis):
        core, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        pods = [_pod(name=f"a{i}", node="n1") for i in range(4)] + [_pod(name="b", node="n2")]
        core.list_namespaced_pod.return_value = _items(pods)
        core.list_node.return_value = _items(
            [
                _node("n1", labels={"topology.kubernetes.io/zone": "z1"}),
                _node("n2", labels={"topology.kubernetes.io/zone": "z2"}),
            ]
        )
        out = json.loads(o.check_pod_distribution.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert any("分布不均匀" in i["message"] for i in out["issues"])

    def test_single_zone(self, apis):
        core, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        pods = [_pod(name="p1", node="n1"), _pod(name="p2", node="n2")]
        core.list_namespaced_pod.return_value = _items(pods)
        core.list_node.return_value = _items(
            [
                _node("n1", labels={"topology.kubernetes.io/zone": "z1"}),
                _node("n2", labels={"topology.kubernetes.io/zone": "z1"}),
            ]
        )
        out = json.loads(o.check_pod_distribution.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert any("同一个可用区" in i["message"] for i in out["issues"])

    def test_statefulset_fallback(self, apis):
        core, apps = apis
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        apps.read_namespaced_stateful_set.return_value = _deploy()
        core.list_namespaced_pod.return_value = _items([_pod(name="p1", node="n1")])
        core.list_node.return_value = _items([_node("n1")])
        out = json.loads(o.check_pod_distribution.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert out["resource_type"] == "StatefulSet"

    def test_neither_found(self, apis):
        core, apps = apis
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        apps.read_namespaced_stateful_set.side_effect = ApiException(status=404)
        out = json.loads(o.check_pod_distribution.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert "未找到Deployment或StatefulSet" in out["error"]


def _probe(http=True, tcp=False, exec_=False, grpc=False, delay=10, timeout=1, path="/healthz", port=8080):
    http_get = None
    if http:
        http_get = SimpleNamespace(path=path, port=port, scheme="HTTP", host=None)
    tcp_socket = SimpleNamespace(port=port, host=None) if tcp else None
    exec_action = SimpleNamespace(command=["cat", "/tmp/healthy"]) if exec_ else None
    grpc_action = SimpleNamespace(port=port, service="health") if grpc else None
    return SimpleNamespace(
        http_get=http_get,
        tcp_socket=tcp_socket,
        _exec=exec_action,
        grpc=grpc_action,
        initial_delay_seconds=delay,
        period_seconds=10,
        timeout_seconds=timeout,
        failure_threshold=3,
    )


def _container(name="c", liveness=None, readiness=None, startup=None):
    return SimpleNamespace(name=name, liveness_probe=liveness, readiness_probe=readiness, startup_probe=startup)


class TestProbeType:
    def test_types(self):
        assert o._get_probe_type(_probe(http=True)) == "httpGet"
        assert o._get_probe_type(_probe(http=False, tcp=True)) == "tcpSocket"
        assert o._get_probe_type(_probe(http=False, exec_=True)) == "exec"
        assert o._get_probe_type(_probe(http=False, grpc=True)) == "grpc"
        assert o._get_probe_type(_probe(http=False)) == "unknown"


class TestValidateProbes:
    def test_both_probes_configured(self, apis):
        _, apps = apis
        container = _container(liveness=_probe(), readiness=_probe())
        apps.read_namespaced_deployment.return_value = SimpleNamespace(
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(containers=[container])))
        )
        out = json.loads(o.validate_probe_configuration.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert out["probe_score"] == "2/2"
        assert out["overall_status"] == "good"
        liveness = out["containers_analysis"][0]["liveness_probe"]
        assert liveness["type"] == "httpGet"
        assert liveness["http_get"]["path"] == "/healthz"
        assert liveness["http_get"]["port"] == 8080
        assert liveness["http_get"]["scheme"] == "HTTP"

    def test_tcp_and_exec_endpoints_are_serialized(self, apis):
        _, apps = apis
        container = _container(liveness=_probe(http=False, tcp=True, port=9090), readiness=_probe(http=False, exec_=True))
        apps.read_namespaced_deployment.return_value = SimpleNamespace(
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(containers=[container])))
        )
        out = json.loads(o.validate_probe_configuration.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        liveness = out["containers_analysis"][0]["liveness_probe"]
        readiness = out["containers_analysis"][0]["readiness_probe"]
        assert liveness["type"] == "tcpSocket"
        assert liveness["tcp_socket"]["port"] == 9090
        assert liveness["http_get"] is None
        assert readiness["type"] == "exec"
        assert readiness["exec_command"] == ["cat", "/tmp/healthy"]

    def test_incomplete_http_get_mock_does_not_raise(self):
        probe = SimpleNamespace(
            http_get=object(),
            tcp_socket=None,
            _exec=None,
            grpc=None,
            initial_delay_seconds=5,
            period_seconds=10,
            timeout_seconds=1,
            failure_threshold=3,
        )
        out = o._serialize_probe(probe)
        assert out["http_get"]["path"] is None
        assert out["type"] == "httpGet"

    def test_nonstandard_port_is_json_safe_and_keeps_path(self):
        probe = SimpleNamespace(
            http_get=SimpleNamespace(path="/readyz", port=object(), scheme="HTTP", host=None),
            tcp_socket=None,
            _exec=SimpleNamespace(command=object()),
            grpc=None,
            initial_delay_seconds=5,
            period_seconds=10,
            timeout_seconds=1,
            failure_threshold=3,
        )
        out = o._serialize_probe(probe)
        dumped = json.dumps(out)
        assert "/readyz" in dumped
        assert out["http_get"]["path"] == "/readyz"
        parsed = json.loads(dumped)
        assert parsed["http_get"]["path"] == "/readyz"

    def test_missing_probes_and_bad_delay(self, apis):
        _, apps = apis
        container = _container(liveness=_probe(delay=0), readiness=None)
        apps.read_namespaced_deployment.return_value = SimpleNamespace(
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(containers=[container])))
        )
        out = json.loads(o.validate_probe_configuration.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert out["probe_score"] == "1/2"  # liveness yes, readiness no
        assert any("initialDelaySeconds为0" in i for i in out["issues"])
        assert any("未配置Readiness" in i for i in out["issues"])

    def test_not_found(self, apis, caplog):
        _, apps = apis
        caplog.set_level(logging.DEBUG, logger="opspilot")
        body = '{"message":"deployments.apps \\"d\\" not found","reason":"NotFound"} ' + _PROBE_BODY_SENTINEL
        apps.read_namespaced_deployment.side_effect = _api_http_error(404, body)
        apps.read_namespaced_replica_set.side_effect = ApiException(status=404)
        out = json.loads(o.validate_probe_configuration.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert "Deployment不存在" in out["error"]
        assert out["status_code"] == 404
        not_found = [record for record in caplog.records if record.msg == o._PROBE_NOT_FOUND_TEMPLATE]
        assert len(not_found) == 1
        record = not_found[0]
        assert record.name == "opspilot"
        assert record.levelno == logging.DEBUG
        assert record.args == ("deployment", "p", "d")
        rendered = record.getMessage()
        formatted = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
        assert rendered == "event=k8s_probe_validate_not_found kind=deployment namespace=p name=d"
        assert _PROBE_BODY_SENTINEL not in rendered
        assert _PROBE_HEADER_SENTINEL not in rendered
        assert _PROBE_BODY_SENTINEL not in formatted
        assert _PROBE_HEADER_SENTINEL not in formatted
        assert _PROBE_BODY_SENTINEL not in caplog.text
        assert not any(rec.levelno >= logging.ERROR and rec.name == "opspilot" for rec in caplog.records)
        assert not any("验证探针配置失败" in rec.getMessage() for rec in caplog.records)

    def test_deployment_404_falls_back_to_replicaset(self, apis):
        _, apps = apis
        container = _container(liveness=_probe(), readiness=_probe())
        apps.read_namespaced_deployment.side_effect = ApiException(status=404)
        apps.read_namespaced_replica_set.return_value = SimpleNamespace(
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(containers=[container])))
        )
        out = json.loads(
            o.validate_probe_configuration.invoke(
                {"deployment_name": "classification-serving-2-55b8c94f55", "namespace": "bklite-mlops", "config": {}}
            )
        )
        assert out["resource_type"] == "replicaset"
        assert out["resource_name"] == "classification-serving-2-55b8c94f55"
        assert out["probe_score"] == "2/2"
        apps.read_namespaced_replica_set.assert_called_once_with("classification-serving-2-55b8c94f55", "bklite-mlops")

    def test_api_error_logs_status_without_response_body(self, apis, caplog):
        _, apps = apis
        caplog.set_level(logging.DEBUG, logger="opspilot")
        body = '{"message":"forbidden"} ' + _PROBE_BODY_SENTINEL
        apps.read_namespaced_deployment.side_effect = _api_http_error(403, body, reason="Forbidden")
        out = json.loads(o.validate_probe_configuration.invoke({"deployment_name": "d", "namespace": "p", "config": {}}))
        assert out["error"] == "验证探针配置失败: HTTP 403"
        assert out["status_code"] == 403
        failed = [record for record in caplog.records if record.msg == o._PROBE_FAILED_TEMPLATE]
        assert len(failed) == 1
        record = failed[0]
        assert record.name == "opspilot"
        assert record.levelno == logging.ERROR
        assert record.args == ("read_probe_containers", "ApiException", "deployment", "p", "d", 403)
        rendered = record.getMessage()
        formatted = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
        assert "failed_stage=read_probe_containers" in rendered
        assert "status=403" in rendered
        assert _PROBE_BODY_SENTINEL not in rendered
        assert _PROBE_HEADER_SENTINEL not in rendered
        assert _PROBE_BODY_SENTINEL not in formatted
        assert _PROBE_BODY_SENTINEL not in caplog.text
        traceback_errors = [rec for rec in caplog.records if rec.name == "opspilot" and rec.levelno >= logging.ERROR and rec.exc_info]
        assert traceback_errors == []

    def test_pod_resource_type_reads_pod_spec(self, apis):
        core, _ = apis
        container = _container(liveness=_probe(), readiness=_probe(timeout=1))
        core.read_namespaced_pod.return_value = SimpleNamespace(spec=SimpleNamespace(containers=[container]))
        out = json.loads(
            o.validate_probe_configuration.invoke({"namespace": "nacos", "resource_type": "pod", "resource_name": "nacos-0", "config": {}})
        )
        assert out["resource_type"] == "pod"
        assert out["resource_name"] == "nacos-0"
        assert out["probe_score"] == "2/2"
        core.read_namespaced_pod.assert_called_once_with("nacos-0", "nacos")

    def test_statefulset_resource_type_reads_template(self, apis):
        _, apps = apis
        container = _container(readiness=_probe())
        apps.read_namespaced_stateful_set.return_value = SimpleNamespace(
            spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(containers=[container])))
        )
        out = json.loads(
            o.validate_probe_configuration.invoke({"namespace": "nacos", "resource_type": "statefulset", "resource_name": "nacos", "config": {}})
        )
        assert out["resource_type"] == "statefulset"
        assert out["probe_score"] == "1/2"
        apps.read_namespaced_stateful_set.assert_called_once_with("nacos", "nacos")


def _rs(name, revision, image="img:1", env=None, replicas=2):
    container = SimpleNamespace(name="c", image=image, env=env)
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name, annotations={"deployment.kubernetes.io/revision": str(revision)}, creation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc)
        ),
        spec=SimpleNamespace(replicas=replicas, template=SimpleNamespace(spec=SimpleNamespace(containers=[container]))),
    )


class TestCompareRevisions:
    def test_image_env_replica_diffs(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        env1 = [SimpleNamespace(name="A", value="1")]
        env2 = [SimpleNamespace(name="A", value="2"), SimpleNamespace(name="B", value="x")]
        rs1 = _rs("rs1", 1, image="img:1", env=env1, replicas=2)
        rs2 = _rs("rs2", 2, image="img:2", env=env2, replicas=3)
        apps.list_namespaced_replica_set.return_value = _items([rs1, rs2])
        out = json.loads(
            o.compare_deployment_revisions.invoke({"deployment_name": "d", "namespace": "p", "revision1": 1, "revision2": 2, "config": {}})
        )
        assert out["has_changes"] is True
        fields = {d["field"] for d in out["differences"]}
        assert "container_images" in fields
        assert "replicas" in fields
        env_diff = next(d for d in out["differences"] if d["field"].endswith("].env"))
        assert "B" in env_diff["added_vars"]
        assert "A" in env_diff["modified_vars"]

    def test_string_revisions_are_coerced(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        rs1 = _rs("rs1", 1, image="img:1", env=None, replicas=2)
        rs2 = _rs("rs2", 2, image="img:2", env=None, replicas=2)
        apps.list_namespaced_replica_set.return_value = _items([rs1, rs2])
        out = json.loads(o.compare_deployment_revisions.func(deployment_name="d", namespace="p", revision1="1", revision2="2", config={}))
        assert "error" not in out
        assert out["has_changes"] is True

    def test_revision1_missing(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        apps.list_namespaced_replica_set.return_value = _items([_rs("rs2", 2)])
        out = json.loads(
            o.compare_deployment_revisions.invoke({"deployment_name": "d", "namespace": "p", "revision1": 1, "revision2": 2, "config": {}})
        )
        assert "未找到revision 1" in out["error"]

    def test_no_changes(self, apis):
        _, apps = apis
        apps.read_namespaced_deployment.return_value = _deploy()
        rs1 = _rs("rs1", 1, image="img:1", env=None, replicas=2)
        rs2 = _rs("rs2", 2, image="img:1", env=None, replicas=2)
        apps.list_namespaced_replica_set.return_value = _items([rs1, rs2])
        out = json.loads(
            o.compare_deployment_revisions.invoke({"deployment_name": "d", "namespace": "p", "revision1": 1, "revision2": 2, "config": {}})
        )
        assert out["has_changes"] is False
        assert out["differences_count"] == 0
