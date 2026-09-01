"""Kubernetes 配置分析工具：配额、网络策略、下一步提示、问题工作负载聚合。

mock kube API 边界，断言 JSON 结构与 fail-closed 错误包装。
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import analysis as a


def _items(lst):
    return SimpleNamespace(items=lst)


@pytest.fixture
def core():
    c = MagicMock()
    with patch.object(a, "prepare_context", return_value=None), patch.object(a.client, "CoreV1Api", return_value=c):
        yield c


def test_resource_quotas_computes_percentage_and_wraps_api_error(core):
    quota = SimpleNamespace(
        metadata=SimpleNamespace(name="q1", namespace="prod"),
        status=SimpleNamespace(hard={"cpu": "1000m", "count/pods": "10"}, used={"cpu": "500m", "count/pods": "2"}),
    )
    core.list_resource_quota_for_all_namespaces.return_value = _items([quota])
    with patch.object(a, "parse_resource_quantity", side_effect=lambda v: float(str(v).replace("m", "")) if "m" in str(v) else float(v)):
        out = json.loads(a.check_kubernetes_resource_quotas.invoke({"config": {}}))
    assert out[0]["name"] == "q1"
    assert out[0]["usage_percentage"]["cpu"] == 50.0
    assert out[0]["usage_percentage"]["count/pods"] == 20.0

    core.list_namespaced_resource_quota.side_effect = ApiException(reason="forbidden")
    err = json.loads(a.check_kubernetes_resource_quotas.invoke({"namespace": "prod", "config": {}}))
    assert "error" in err


def test_network_policies_namespaced_and_cluster():
    policy = SimpleNamespace(
        metadata=SimpleNamespace(name="deny-all", namespace="prod"),
        spec=SimpleNamespace(
            pod_selector=SimpleNamespace(match_labels={"app": "web"}),
            policy_types=["Ingress"],
            ingress=[1],
            egress=None,
        ),
    )
    net = MagicMock()
    net.list_network_policy_for_all_namespaces.return_value = _items([policy])
    net.list_namespaced_network_policy.return_value = _items([policy])
    with patch.object(a, "prepare_context"), patch.object(a.client, "NetworkingV1Api", return_value=net):
        all_ns = json.loads(a.check_kubernetes_network_policies.invoke({"config": {}}))
        named = json.loads(a.check_kubernetes_network_policies.invoke({"namespace": "prod", "config": {}}))
        net.list_network_policy_for_all_namespaces.side_effect = ApiException(reason="down")
        err = json.loads(a.check_kubernetes_network_policies.invoke({"config": {}}))
    assert all_ns[0]["ingress_rules"] == 1
    assert named[0]["pod_selector"] == {"app": "web"}
    assert "error" in err


def test_persistent_volumes_join_claims(core):
    pv = SimpleNamespace(
        metadata=SimpleNamespace(name="pv-1"),
        spec=SimpleNamespace(
            capacity={"storage": "10Gi"},
            access_modes=["ReadWriteOnce"],
            persistent_volume_reclaim_policy="Retain",
            storage_class_name="standard",
        ),
        status=SimpleNamespace(phase="Bound"),
    )
    pvc = SimpleNamespace(
        metadata=SimpleNamespace(name="claim-1", namespace="prod"),
        spec=SimpleNamespace(volume_name="pv-1"),
        status=SimpleNamespace(phase="Bound"),
    )
    core.list_persistent_volume.return_value = _items([pv])
    core.list_persistent_volume_claim_for_all_namespaces.return_value = _items([pvc])
    out = json.loads(a.check_kubernetes_persistent_volumes.invoke({"config": {}}))
    assert out[0]["claim"]["name"] == "claim-1"
    assert out[0]["status"] == "Bound"


def test_jobs_report_completions_and_api_error():
    job = SimpleNamespace(
        metadata=SimpleNamespace(name="migrate", namespace="prod"),
        spec=SimpleNamespace(completions=1, parallelism=1),
        status=SimpleNamespace(succeeded=1, failed=0, active=0, start_time=None, completion_time=None),
    )
    cron = SimpleNamespace(
        metadata=SimpleNamespace(name="nightly", namespace="prod"),
        spec=SimpleNamespace(schedule="0 1 * * *", suspend=False),
        status=SimpleNamespace(active=[], last_schedule_time=None),
    )
    batch = MagicMock()
    batch.list_job_for_all_namespaces.return_value = _items([job])
    batch.list_cron_job_for_all_namespaces.return_value = _items([cron])
    with patch.object(a, "prepare_context"), patch.object(a.client, "BatchV1Api", return_value=batch):
        out = json.loads(a.check_kubernetes_jobs.invoke({"config": {}}))
    assert out["jobs"][0]["succeeded"] == 1
    assert out["cronjobs"][0]["schedule"] == "0 1 * * *"

    batch.list_job_for_all_namespaces.side_effect = ApiException(reason="down")
    with patch.object(a, "prepare_context"), patch.object(a.client, "BatchV1Api", return_value=batch):
        err = json.loads(a.check_kubernetes_jobs.invoke({"config": {}}))
    assert "error" in err


def test_ingress_extracts_hosts_backends_and_lb():
    ingress = SimpleNamespace(
        metadata=SimpleNamespace(name="web", namespace="prod"),
        spec=SimpleNamespace(
            ingress_class_name="nginx",
            tls=["secret"],
            rules=[
                SimpleNamespace(
                    host="app.example",
                    http=SimpleNamespace(
                        paths=[
                            SimpleNamespace(
                                path="/",
                                path_type="Prefix",
                                backend=SimpleNamespace(
                                    service=SimpleNamespace(
                                        name="web-svc",
                                        port=SimpleNamespace(number=80),
                                    )
                                ),
                            )
                        ]
                    ),
                )
            ],
        ),
        status=SimpleNamespace(load_balancer=SimpleNamespace(ingress=[SimpleNamespace(ip="1.1.1.1", hostname=None)])),
    )
    net = MagicMock()
    net.list_ingress_for_all_namespaces.return_value = _items([ingress])
    with patch.object(a, "prepare_context"), patch.object(a.client, "NetworkingV1Api", return_value=net):
        out = json.loads(a.check_kubernetes_ingress.invoke({"config": {}}))
    assert out[0]["hosts"] == ["app.example"]
    assert out[0]["backends"][0]["service_name"] == "web-svc"
    assert out[0]["load_balancers"][0]["value"] == "1.1.1.1"
    assert out[0]["tls"] == 1


def test_endpoints_ready_and_not_ready():
    endpoint = SimpleNamespace(
        metadata=SimpleNamespace(name="web-svc", namespace="prod"),
        subsets=[
            SimpleNamespace(
                addresses=[
                    SimpleNamespace(
                        ip="10.0.0.2",
                        hostname=None,
                        target_ref=SimpleNamespace(kind="Pod", name="web-0"),
                    )
                ],
                not_ready_addresses=[SimpleNamespace(ip="10.0.0.3", hostname=None, target_ref=None)],
                ports=[SimpleNamespace(name="http", port=80, protocol="TCP")],
            )
        ],
    )
    core = MagicMock()
    core.list_endpoints_for_all_namespaces.return_value = _items([endpoint])
    with patch.object(a, "prepare_context"), patch.object(a.client, "CoreV1Api", return_value=core):
        out = json.loads(a.check_kubernetes_endpoints.invoke({"config": {}}))
    assert out[0]["ready_count"] == 1
    assert out[0]["not_ready_count"] == 1
    assert out[0]["ready_addresses"][0]["target_ref"] == "Pod/web-0"


def test_hpa_reports_replicas_and_metrics():
    hpa = SimpleNamespace(
        metadata=SimpleNamespace(name="web-hpa", namespace="prod"),
        spec=SimpleNamespace(
            min_replicas=1,
            max_replicas=5,
            scale_target_ref=SimpleNamespace(kind="Deployment", name="web"),
            metrics=[
                SimpleNamespace(
                    type="Resource",
                    resource=SimpleNamespace(
                        name="cpu",
                        target=SimpleNamespace(average_value=None, average_utilization=70),
                    ),
                )
            ],
        ),
        status=SimpleNamespace(
            current_replicas=2,
            desired_replicas=3,
            current_metrics=[
                SimpleNamespace(
                    type="Resource",
                    resource=SimpleNamespace(
                        name="cpu",
                        current=SimpleNamespace(average_value=None, average_utilization=80),
                    ),
                )
            ],
            conditions=[SimpleNamespace(type="AbleToScale", status="True", reason="ok", message="")],
        ),
    )
    auto = MagicMock()
    auto.list_horizontal_pod_autoscaler_for_all_namespaces.return_value = _items([hpa])
    with patch.object(a, "prepare_context"), patch.object(a.client, "AutoscalingV2Api", return_value=auto):
        out = json.loads(a.check_kubernetes_hpa_status.invoke({"config": {}}))
    assert out[0]["target_ref"] == "Deployment/web"
    assert out[0]["desired_replicas"] == 3
    assert out[0]["current_metrics"][0]["current_value"] == 80


def _deployment(name="web", ns="prod", replicas=1, image="web:latest"):
    container = SimpleNamespace(
        name="app",
        image=image,
        resources=None,
        liveness_probe=None,
        readiness_probe=None,
        security_context=None,
    )
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=ns),
        spec=SimpleNamespace(
            replicas=replicas,
            strategy=SimpleNamespace(type="RollingUpdate"),
            selector=SimpleNamespace(match_labels={"app": name}),
            template=SimpleNamespace(
                spec=SimpleNamespace(
                    containers=[container],
                    affinity=None,
                )
            ),
        ),
    )


def test_analyze_deployment_flags_single_replica_and_missing_guards():
    apps = MagicMock()
    core = MagicMock()
    apps.list_deployment_for_all_namespaces.return_value = _items([_deployment()])
    core.list_namespaced_pod_disruption_budget.side_effect = RuntimeError("no pdb api")
    with (
        patch.object(a, "prepare_context"),
        patch.object(a.client, "AppsV1Api", return_value=apps),
        patch.object(a.client, "CoreV1Api", return_value=core),
        patch.object(a, "get_current_cluster_name", return_value="prod-cluster"),
    ):
        out = json.loads(a.analyze_deployment_configurations.invoke({"config": {}}))
    assert out["cluster_name"] == "prod-cluster"
    assert out["problematic"] == 1
    issues = {item["issue"] for item in out["issues_detail"]}
    assert any("单副本" in i for i in issues)
    assert any("资源限制" in i for i in issues)
    assert any("存活探针" in i for i in issues)
    assert any("latest" in i or "标签" in i for i in issues)
    full = out["_deployments_full"][0]
    assert full["config_analysis"]["replicas"] == 1


def test_analyze_deployment_not_found_and_scope_too_large():
    apps = MagicMock()
    core = MagicMock()
    apps.list_namespaced_deployment.return_value = _items([_deployment("other")])
    with (
        patch.object(a, "prepare_context"),
        patch.object(a.client, "AppsV1Api", return_value=apps),
        patch.object(a.client, "CoreV1Api", return_value=core),
        patch.object(a, "get_current_cluster_name", return_value="c"),
    ):
        missing = json.loads(a.analyze_deployment_configurations.invoke({"namespace": "prod", "name": "web", "config": {}}))
    assert missing["error"] == "deployment_not_found"

    crowded = [_deployment(name=f"d{i}", ns="ns-a" if i < 60 else "ns-b") for i in range(101)]
    apps.list_deployment_for_all_namespaces.return_value = _items(crowded)
    with (
        patch.object(a, "prepare_context"),
        patch.object(a.client, "AppsV1Api", return_value=apps),
        patch.object(a.client, "CoreV1Api", return_value=core),
        patch.object(a, "get_current_cluster_name", return_value="c"),
    ):
        huge = json.loads(a.analyze_deployment_configurations.invoke({"config": {}}))
    assert huge["error"] == "scope_too_large"
    assert huge["total"] == 101


def test_daemonset_and_statefulset_status():
    ds = SimpleNamespace(
        metadata=SimpleNamespace(name="agent", namespace="kube-system"),
        status=SimpleNamespace(
            desired_number_scheduled=3,
            current_number_scheduled=3,
            number_ready=2,
            updated_number_scheduled=3,
            number_available=2,
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec=SimpleNamespace(node_selector={"pool": "sys"}))),
    )
    sts = SimpleNamespace(
        metadata=SimpleNamespace(name="pg", namespace="db"),
        spec=SimpleNamespace(replicas=3, service_name="pg", volume_claim_templates=[1, 2]),
        status=SimpleNamespace(ready_replicas=3, current_replicas=3, updated_replicas=3),
    )
    apps = MagicMock()
    apps.list_daemon_set_for_all_namespaces.return_value = _items([ds])
    apps.list_stateful_set_for_all_namespaces.return_value = _items([sts])
    with (
        patch.object(a, "prepare_context"),
        patch.object(a.client, "AppsV1Api", return_value=apps),
        patch.object(a, "get_current_cluster_name", return_value="c1"),
    ):
        daemon = json.loads(a.check_kubernetes_daemonsets.invoke({"config": {}}))
        stateful = json.loads(a.check_kubernetes_statefulsets.invoke({"config": {}}))
    assert daemon["daemonsets"][0]["ready"] == 2
    assert daemon["daemonsets"][0]["node_selector"] == {"pool": "sys"}
    assert stateful["statefulsets"][0]["volume_claim_templates"] == 2
    assert stateful["statefulsets"][0]["ready_replicas"] == 3
