"""多实例路由辅助与 resolve/定点/扫描行为单测。不连真实集群。"""

import io
import json
import logging
import pickle
import threading
import traceback
from contextlib import contextmanager

import pydantic.root_model  # noqa
import yaml

from apps.core.logger import SafeLogException, opspilot_logger
from apps.opspilot.metis.llm.tools.kubernetes.instance_scope import bind_instance_config, point_instance_error, route_alert_cluster, run_scan_tool

_LOOKUP_NAMESPACES = "apps.opspilot.metis.llm.tools.kubernetes.data_collection._lookup_namespaces_by_resource_name"
_LOOKUP_SECRET_SENTINEL = "kc-secret-hunter2-not-for-logs"


@contextmanager
def _capture_opspilot_formatted_logs():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    opspilot_logger.addHandler(handler)
    try:
        yield output
    finally:
        opspilot_logger.removeHandler(handler)


def _multi_config(names=("bk-lite-k3s", "onedc_k8s_cluster")):
    instances = [{"id": f"i{i}", "name": name, "kubeconfig_data": f"kc-{name}"} for i, name in enumerate(names, start=1)]
    return {"configurable": {"kubernetes_instances": instances}}, instances


class TestRouteAlertCluster:
    def test_multi_match_by_display_name(self):
        config, _ = _multi_config()
        bound, extra = route_alert_cluster("onedc_k8s_cluster", config)
        assert extra["instance_name"] == "onedc_k8s_cluster"
        assert bound["configurable"]["instance_name"] == "onedc_k8s_cluster"
        assert "route_error" not in extra

    def test_bind_skips_unpicklable_runtime_objects(self):
        config, _ = _multi_config(names=("minikube", "other"))
        config["configurable"]["browser_step_callback"] = threading.Lock()
        config["configurable"]["graph_request"] = threading.Lock()
        config["configurable"]["token_usage_accumulator"] = threading.Lock()

        bound, extra = route_alert_cluster("minikube", config)
        assert extra["instance_name"] == "minikube"
        assert bound["configurable"]["instance_name"] == "minikube"
        assert "browser_step_callback" not in bound["configurable"]
        pickle.dumps(bound)

        rebound = bind_instance_config(config, config["configurable"]["kubernetes_instances"][0])
        pickle.dumps(rebound)

    def test_multi_match_by_kubeconfig_cluster(self):
        kubeconfig = yaml.safe_dump({"clusters": [{"name": "onedc_k8s_cluster"}]})
        config = {
            "configurable": {
                "kubernetes_instances": [
                    {"id": "i1", "name": "bk-lite-k3s", "kubeconfig_data": "kc-a"},
                    {"id": "i2", "name": "prod-display", "kubeconfig_data": kubeconfig},
                ]
            }
        }
        bound, extra = route_alert_cluster("onedc_k8s_cluster", config)
        assert extra["instance_name"] == "prod-display"
        assert bound["configurable"]["instance_id"] == "i2"

    def test_multi_unbound_closes(self):
        config, _ = _multi_config()
        bound, extra = route_alert_cluster("ghost-cluster", config)
        assert bound is None
        assert "未绑定实例" in extra["route_error"]
        assert "bk-lite-k3s" in extra["route_error"]

    def test_multi_missing_cluster_closes(self):
        config, _ = _multi_config()
        bound, extra = route_alert_cluster(None, config)
        assert bound is None
        assert "未提供集群标识" in extra["route_error"]

    def test_single_mismatch_hint(self):
        config = {"configurable": {"kubernetes_instances": [{"id": "i1", "name": "bk-lite-k3s", "kubeconfig_data": "kc"}]}}
        bound, extra = route_alert_cluster("onedc_k8s_cluster", config)
        assert bound is not None
        assert extra["instance_name"] == "bk-lite-k3s"
        assert "cluster_mismatch" in extra

    def test_single_match_no_mismatch(self):
        config = {"configurable": {"kubernetes_instances": [{"id": "i1", "name": "onedc_k8s_cluster", "kubeconfig_data": "kc"}]}}
        bound, extra = route_alert_cluster("onedc_k8s_cluster", config)
        assert extra["instance_name"] == "onedc_k8s_cluster"
        assert "cluster_mismatch" not in extra

    def test_no_instances_passthrough(self):
        bound, extra = route_alert_cluster("onedc_k8s_cluster", {"configurable": {}})
        assert extra == {}
        assert bound == {"configurable": {}}


class TestPointInstanceError:
    def test_multi_requires_name(self):
        config, _ = _multi_config()
        err = json.loads(point_instance_error(config))
        assert "请指定 instance_name" in err["error"]
        assert "onedc_k8s_cluster" in err["instance_names"]

    def test_single_ok(self):
        config = {"configurable": {"kubernetes_instances": [{"id": "i1", "name": "only", "kubeconfig_data": "kc"}]}}
        assert point_instance_error(config) is None

    def test_already_bound_ok(self):
        config, _ = _multi_config()
        config["configurable"]["instance_name"] = "bk-lite-k3s"
        assert point_instance_error(config) is None


class TestRunScanTool:
    def test_single_passthrough_list(self):
        out = json.loads(run_scan_tool({"configurable": {}}, None, lambda _cfg: json.dumps([{"name": "p"}])))
        assert out == [{"name": "p"}]

    def test_fanout_aggregates_and_skips_error(self):
        config, _ = _multi_config()

        def _run(bound):
            name = bound["configurable"]["instance_name"]
            if name == "bk-lite-k3s":
                return json.dumps([{"name": "a"}])
            return json.dumps({"error": "kubeconfig 无效"})

        out = json.loads(run_scan_tool(config, None, _run))
        assert out["mode"] == "multi_instance"
        by_cluster = {item["cluster"]: item for item in out["instances"]}
        assert by_cluster["bk-lite-k3s"]["items"] == [{"name": "a"}]
        assert by_cluster["onedc_k8s_cluster"]["error"] == "kubeconfig 无效"

    def test_explicit_instance_no_fanout(self):
        config, _ = _multi_config()
        seen = []

        def _run(bound):
            seen.append(bound["configurable"]["instance_name"])
            return json.dumps([{"name": "p"}])

        out = json.loads(run_scan_tool(config, "onedc_k8s_cluster", _run))
        assert out == [{"name": "p"}]
        assert seen == ["onedc_k8s_cluster"]

    def test_already_bound_no_fanout(self):
        config, _ = _multi_config()
        config["configurable"]["instance_name"] = "bk-lite-k3s"
        seen = []

        def _run(bound):
            seen.append(bound["configurable"].get("instance_name"))
            return json.dumps([{"name": "p"}])

        out = json.loads(run_scan_tool(config, None, _run))
        assert out == [{"name": "p"}]
        assert seen == ["bk-lite-k3s"]


def test_resolve_routes_to_matched_instance_and_looks_up(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config()
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection._cluster_config_error", return_value=None)
    mocker.patch(
        _LOOKUP_NAMESPACES,
        return_value=([{"name": "nacos-0", "namespace": "nacos"}], [], None),
    )

    payload = json.loads(
        resolve_k8s_target_from_alert.invoke(
            {"normalized_alert": "告警：Unhealthy（kubernetes，onedc_k8s_cluster，nacos-0） 检测到异常\n内容：Readiness probe failed"},
            config=config,
        )
    )
    assert payload["resolved"] is True
    assert payload["instance_name"] == "onedc_k8s_cluster"
    assert payload["namespace"] == "nacos"
    assert payload["pod_name"] == "nacos-0"


def test_resolve_survives_runtime_locks_in_configurable(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config(names=("minikube", "other"))
    config["configurable"]["browser_step_callback"] = threading.Lock()
    config["configurable"]["graph_request"] = threading.Lock()
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection._cluster_config_error", return_value=None)
    lookup = mocker.patch(_LOOKUP_NAMESPACES)
    list_pods = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.resources.list_kubernetes_pods")

    payload = json.loads(
        resolve_k8s_target_from_alert.invoke(
            {"normalized_alert": ("告警：Unhealthy（kubernetes，minikube，kube-scheduler-minikube） 检测到异常\n" "内容：Liveness probe failed")},
            config=config,
        )
    )
    assert payload.get("error") != "TypeError"
    assert "cannot pickle" not in str(payload.get("error") or "")
    assert payload["resolved"] is True
    assert payload["instance_name"] == "minikube"
    assert payload["namespace"] == "kube-system"
    assert payload["namespace_lookup"] == "control_plane_convention"
    lookup.assert_not_called()
    list_pods.invoke.assert_not_called()


def test_resolve_model_object_name_json_routes_to_minikube(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config(names=("bk-lite-k3s", "minikube"))
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection._cluster_config_error", return_value=None)
    lookup = mocker.patch(_LOOKUP_NAMESPACES)
    list_pods = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.resources.list_kubernetes_pods")

    payload = json.loads(
        resolve_k8s_target_from_alert.invoke(
            {
                "normalized_alert": json.dumps(
                    {
                        "alert_name": "Unhealthy",
                        "cluster": "minikube",
                        "object_name": "kube-scheduler-minikube",
                        "probe_type": "Liveness",
                        "error": "TLS handshake timeout",
                    },
                    ensure_ascii=False,
                )
            },
            config=config,
        )
    )
    assert payload.get("missing_data") != ["resource_type_or_name"]
    assert payload["resource_type"] == "pod"
    assert payload["pod_name"] == "kube-scheduler-minikube"
    assert payload["instance_name"] == "minikube"
    assert payload["namespace"] == "kube-system"
    assert payload["namespace_lookup"] == "control_plane_convention"
    assert payload["resolved"] is True
    lookup.assert_not_called()
    list_pods.invoke.assert_not_called()


def test_resolve_static_pod_name_without_kind_routes_to_minikube(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config(names=("bk-lite-k3s", "minikube"))
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection._cluster_config_error", return_value=None)
    lookup = mocker.patch(_LOOKUP_NAMESPACES)
    list_pods = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.resources.list_kubernetes_pods")

    payload = json.loads(
        resolve_k8s_target_from_alert.invoke(
            {"normalized_alert": {"name": "kube-scheduler-minikube", "cluster": "minikube"}},
            config=config,
        )
    )
    assert payload.get("missing_data") != ["resource_type_or_name"]
    assert payload["resource_type"] == "pod"
    assert payload["pod_name"] == "kube-scheduler-minikube"
    assert payload["instance_name"] == "minikube"
    assert payload["namespace"] == "kube-system"
    assert payload["namespace_lookup"] == "control_plane_convention"
    assert payload["resolved"] is True
    lookup.assert_not_called()
    list_pods.invoke.assert_not_called()


def test_resolve_event_json_does_not_treat_monitor_service_as_k8s_service(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config(names=("bk-lite-k3s", "minikube"))
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection._cluster_config_error", return_value=None)
    payload = json.loads(
        resolve_k8s_target_from_alert.invoke(
            {
                "normalized_alert": {
                    "item": "Unhealthy",
                    "service": "kubernetes",
                    "location": "minikube",
                    "resource_name": "kube-scheduler-minikube",
                    "labels": {
                        "kind": "Pod",
                        "name": "kube-scheduler-minikube",
                        "namespace": "kube-system",
                        "cluster_name": "minikube",
                    },
                    "tags": {"cluster": "minikube", "namespace": "kube-system", "kind": "Pod"},
                }
            },
            config=config,
        )
    )
    assert payload["resource_type"] == "pod"
    assert payload.get("service_name") in (None, "", [])
    assert payload["instance_name"] == "minikube"
    assert payload["cluster"] == "minikube"
    assert payload["namespace"] == "kube-system"
    assert payload["resolved"] is True
    assert payload.get("error") is None


def test_resolve_lookup_failure_logs_once(mocker, caplog):
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config(names=("minikube-log", "other-log"))
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.data_collection._cluster_config_error", return_value=None)
    lookup_error = RuntimeError(f"conn refused {_LOOKUP_SECRET_SENTINEL}")
    mocker.patch(_LOOKUP_NAMESPACES, side_effect=lookup_error)
    caplog.set_level(logging.INFO, logger="opspilot")

    with _capture_opspilot_formatted_logs() as output:
        payload = json.loads(
            resolve_k8s_target_from_alert.invoke(
                {"normalized_alert": {"labels": {"cluster": "minikube-log", "pod": "log-probe-pod"}}},
                config=config,
            )
        )
    rendered = output.getvalue()
    assert payload["resolved"] is False
    assert _LOOKUP_SECRET_SENTINEL in payload["error"]
    owned = [
        rec
        for rec in caplog.records
        if rec.name == "opspilot"
        and rec.levelno >= logging.ERROR
        and rec.exc_info
        and rec.msg == "event=k8s_alert_resolve_failed failed_stage=%s error_type=%s instance_name=%s"
    ]
    assert len(owned) == 1
    rec = owned[0]
    assert rec.args == ("namespace_lookup", "RuntimeError", "minikube-log")
    message = rec.getMessage()
    assert "failed_stage=namespace_lookup" in message
    assert "error_type=RuntimeError" in message
    assert "instance_name=minikube-log" in message
    assert rec.exc_info[0] is SafeLogException
    assert rec.exc_info[1] is not lookup_error
    assert rec.exc_info[2] is lookup_error.__traceback__
    assert str(rec.exc_info[1]) == "RuntimeError"
    assert str(lookup_error) == f"conn refused {_LOOKUP_SECRET_SENTINEL}"
    frame_names = [frame.name for frame in traceback.extract_tb(rec.exc_info[2])]
    assert "resolve_k8s_target_from_alert" in frame_names
    assert "kubeconfig" not in message.lower()
    assert _LOOKUP_SECRET_SENTINEL not in message
    assert "Traceback" in rendered
    assert "resolve_k8s_target_from_alert" in rendered
    assert _LOOKUP_SECRET_SENTINEL not in rendered
    traceback_errors = [r for r in caplog.records if r.name == "opspilot" and r.levelno >= logging.ERROR and r.exc_info]
    assert traceback_errors == owned


def test_resolve_unbound_cluster_is_conclusive():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config()
    payload = json.loads(
        resolve_k8s_target_from_alert.invoke(
            {"normalized_alert": {"title": "Unhealthy（kubernetes，ghost，nacos-0）", "labels": {"cluster": "ghost", "pod": "nacos-0"}}},
            config=config,
        )
    )
    assert payload["resolved"] is False
    assert payload["conclusive"] is True
    assert "未绑定实例" in payload["error"]


def test_resolve_multi_without_cluster_is_conclusive():
    from apps.opspilot.metis.llm.tools.kubernetes.data_collection import resolve_k8s_target_from_alert

    config, _ = _multi_config()
    payload = json.loads(resolve_k8s_target_from_alert.invoke({"normalized_alert": {"labels": {"pod": "nacos-0"}}}, config=config))
    assert payload["resolved"] is False
    assert payload["conclusive"] is True
    assert "未提供集群标识" in payload["error"]


def test_diagnose_multi_requires_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.diagnostics import diagnose_kubernetes_pod_issues

    config, _ = _multi_config()
    out = json.loads(diagnose_kubernetes_pod_issues.invoke({"namespace": "nacos", "pod_name": "nacos-0"}, config=config))
    assert "请指定 instance_name" in out["error"]


def test_list_pods_fanout_uses_scan_wrapper(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes import resources as res

    config, _ = _multi_config()
    seen = []

    def _fake(namespace, bound_config):
        seen.append(bound_config["configurable"]["instance_name"])
        if bound_config["configurable"]["instance_name"] == "bk-lite-k3s":
            raise RuntimeError("conn refused")
        return json.dumps([{"name": "nacos-0", "namespace": "nacos"}])

    mocker.patch.object(res, "_list_kubernetes_pods_on_instance", side_effect=_fake)
    out = json.loads(res.list_kubernetes_pods.invoke({}, config=config))
    assert out["mode"] == "multi_instance"
    by_cluster = {item["cluster"]: item for item in out["instances"]}
    assert "conn refused" in by_cluster["bk-lite-k3s"]["error"]
    assert by_cluster["onedc_k8s_cluster"]["items"][0]["name"] == "nacos-0"
    assert set(seen) == {"bk-lite-k3s", "onedc_k8s_cluster"}


def _assert_requires_instance_name(payload):
    assert "请指定 instance_name" in payload["error"]


def test_restart_pod_multi_requires_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.remediation import restart_pod

    config, _ = _multi_config()
    out = json.loads(restart_pod.invoke({"pod_name": "p", "namespace": "default", "wait_for_ready": False}, config=config))
    _assert_requires_instance_name(out)


def test_scale_deployment_multi_requires_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.remediation import scale_deployment

    config, _ = _multi_config()
    out = json.loads(scale_deployment.invoke({"deployment_name": "d", "namespace": "default", "replicas": 2}, config=config))
    _assert_requires_instance_name(out)


def test_batch_restart_pods_multi_requires_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.batch_operations import batch_restart_pods

    config, _ = _multi_config()
    out = json.loads(batch_restart_pods.invoke({"namespace": "default", "pod_names": ["p"]}, config=config))
    _assert_requires_instance_name(out)


def test_diagnose_pending_pod_issues_multi_requires_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.diagnostics_advanced import diagnose_pending_pod_issues

    config, _ = _multi_config()
    out = json.loads(diagnose_pending_pod_issues.invoke({"pod_name": "p", "namespace": "default"}, config=config))
    _assert_requires_instance_name(out)


def test_restart_pod_explicit_instance_binds_only_target(mocker):
    from kubernetes.client import ApiException

    from apps.opspilot.metis.llm.tools.kubernetes import remediation as r

    config, _ = _multi_config()
    seen = []

    def _prep(cfg):
        seen.append(cfg["configurable"]["instance_name"])

    mocker.patch.object(r, "prepare_context", side_effect=_prep)
    core = mocker.MagicMock()
    mocker.patch.object(r.client, "CoreV1Api", return_value=core)
    core.read_namespaced_pod.side_effect = ApiException(status=404)

    out = json.loads(
        r.restart_pod.invoke(
            {"pod_name": "p", "namespace": "default", "wait_for_ready": False, "instance_name": "onedc_k8s_cluster"},
            config=config,
        )
    )
    assert "Pod不存在" in out["error"]
    assert seen == ["onedc_k8s_cluster"]


def test_scale_deployment_explicit_instance_binds_only_target(mocker):
    from kubernetes.client import ApiException

    from apps.opspilot.metis.llm.tools.kubernetes import remediation as r

    config, _ = _multi_config()
    seen = []

    def _prep(cfg):
        seen.append(cfg["configurable"]["instance_name"])

    mocker.patch.object(r, "prepare_context", side_effect=_prep)
    apps = mocker.MagicMock()
    mocker.patch.object(r.client, "AppsV1Api", return_value=apps)
    apps.read_namespaced_deployment.side_effect = ApiException(status=404)
    apps.read_namespaced_stateful_set.side_effect = ApiException(status=404)

    out = json.loads(
        r.scale_deployment.invoke(
            {"deployment_name": "d", "namespace": "default", "replicas": 2, "instance_name": "onedc_k8s_cluster"},
            config=config,
        )
    )
    assert seen == ["onedc_k8s_cluster"]
    assert out.get("error") or out.get("success") is False


def test_batch_restart_pods_explicit_instance_binds_only_target(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes import batch_operations as b

    config, _ = _multi_config()
    seen = []

    def _prep(cfg):
        seen.append(cfg["configurable"]["instance_name"])

    mocker.patch.object(b, "prepare_context", side_effect=_prep)
    core = mocker.MagicMock()
    mocker.patch.object(b.client, "CoreV1Api", return_value=core)
    core.read_namespaced_pod.side_effect = Exception("missing")

    out = json.loads(
        b.batch_restart_pods.invoke(
            {"namespace": "default", "pod_names": ["p"], "instance_name": "onedc_k8s_cluster"},
            config=config,
        )
    )
    assert seen == ["onedc_k8s_cluster"]
    assert "error" in out or "failed_pods" in out


def test_diagnose_pending_explicit_instance_binds_only_target(mocker):
    from kubernetes.client import ApiException

    from apps.opspilot.metis.llm.tools.kubernetes import diagnostics_advanced as da

    config, _ = _multi_config()
    seen = []

    def _prep(cfg):
        seen.append(cfg["configurable"]["instance_name"])

    mocker.patch.object(da, "prepare_context", side_effect=_prep)
    core = mocker.MagicMock()
    mocker.patch.object(da.client, "CoreV1Api", return_value=core)
    core.read_namespaced_pod.side_effect = ApiException(status=404)

    out = json.loads(
        da.diagnose_pending_pod_issues.invoke(
            {"pod_name": "p", "namespace": "default", "instance_name": "onedc_k8s_cluster"},
            config=config,
        )
    )
    assert "Pod不存在" in out["error"]
    assert seen == ["onedc_k8s_cluster"]


def test_list_events_fanout_uses_scan_wrapper(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes import resources as res

    config, _ = _multi_config()
    seen = []

    def _fake(namespace, bound_config):
        seen.append(bound_config["configurable"]["instance_name"])
        if bound_config["configurable"]["instance_name"] == "bk-lite-k3s":
            raise RuntimeError("conn refused")
        return json.dumps([{"type": "Warning", "reason": "BackOff"}])

    mocker.patch.object(res, "_list_kubernetes_events_on_instance", side_effect=_fake)
    out = json.loads(res.list_kubernetes_events.invoke({}, config=config))
    assert out["mode"] == "multi_instance"
    by_cluster = {item["cluster"]: item for item in out["instances"]}
    assert "conn refused" in by_cluster["bk-lite-k3s"]["error"]
    assert by_cluster["onedc_k8s_cluster"]["items"][0]["reason"] == "BackOff"
    assert set(seen) == {"bk-lite-k3s", "onedc_k8s_cluster"}


def test_cleanup_failed_pods_multi_requires_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.batch_operations import cleanup_failed_pods

    config, _ = _multi_config()
    out = json.loads(cleanup_failed_pods.invoke({}, config=config))
    _assert_requires_instance_name(out)


def test_rollback_and_wait_and_delete_multi_require_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.remediation import delete_kubernetes_resource, rollback_deployment, wait_for_pod_ready

    config, _ = _multi_config()
    _assert_requires_instance_name(json.loads(rollback_deployment.invoke({"deployment_name": "d", "namespace": "ns"}, config=config)))
    _assert_requires_instance_name(json.loads(wait_for_pod_ready.invoke({"pod_name": "p", "namespace": "ns"}, config=config)))
    _assert_requires_instance_name(
        json.loads(delete_kubernetes_resource.invoke({"resource_type": "pod", "resource_name": "p", "namespace": "ns"}, config=config))
    )


def test_pending_trace_scaling_compare_multi_require_instance_name():
    from apps.opspilot.metis.llm.tools.kubernetes.optimization import check_scaling_capacity, compare_deployment_revisions
    from apps.opspilot.metis.llm.tools.kubernetes.tracing import trace_service_chain

    config, _ = _multi_config()
    _assert_requires_instance_name(json.loads(trace_service_chain.invoke({"service_name": "svc", "namespace": "ns"}, config=config)))
    _assert_requires_instance_name(json.loads(check_scaling_capacity.invoke({"namespace": "ns", "replicas": 2}, config=config)))
    _assert_requires_instance_name(
        json.loads(compare_deployment_revisions.invoke({"deployment_name": "d", "namespace": "ns", "revision1": 1, "revision2": 2}, config=config))
    )


def test_list_deployments_fanout_uses_scan_wrapper(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes import resources as res

    config, _ = _multi_config()
    seen = []

    def _fake(namespace, limit, offset, bound_config):
        seen.append(bound_config["configurable"]["instance_name"])
        return json.dumps(
            {"items": [{"name": bound_config["configurable"]["instance_name"]}], "total": 1, "returned": 1, "offset": 0, "has_more": False}
        )

    mocker.patch.object(res, "_list_kubernetes_deployments_on_instance", side_effect=_fake)
    out = json.loads(res.list_kubernetes_deployments.invoke({}, config=config))
    assert out["mode"] == "multi_instance"
    by_cluster = {item["cluster"]: item for item in out["instances"]}
    assert by_cluster["bk-lite-k3s"]["items"][0]["name"] == "bk-lite-k3s"
    assert set(seen) == {"bk-lite-k3s", "onedc_k8s_cluster"}
