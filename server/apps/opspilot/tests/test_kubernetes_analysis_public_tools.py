"""Kubernetes 分析公开工具的诊断结果契约。"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.chain import report_renderers
from apps.opspilot.metis.llm.tools.kubernetes import analysis

pytestmark = pytest.mark.unit


def listed(*items):
    return NS(items=list(items))


QUOTA = NS(
    metadata=NS(name="compute", namespace="prod"),
    status=NS(
        hard={"requests.cpu": "10", "pods": "20"},
        used={"requests.cpu": "5", "pods": "12"},
    ),
)
POLICY = NS(
    metadata=NS(name="deny-by-default", namespace="prod"),
    spec=NS(
        pod_selector=NS(match_labels={"app": "api"}),
        policy_types=["Ingress", "Egress"],
        ingress=[NS()],
        egress=[],
    ),
)
PVC = NS(
    metadata=NS(name="data-postgres-0", namespace="prod"),
    spec=NS(volume_name="pv-data"),
    status=NS(phase="Bound"),
)
PV = NS(
    metadata=NS(name="pv-data"),
    spec=NS(
        capacity={"storage": "20Gi"},
        access_modes=["ReadWriteOnce"],
        persistent_volume_reclaim_policy="Retain",
        storage_class_name="fast",
    ),
    status=NS(phase="Bound"),
)
INGRESS = NS(
    metadata=NS(name="api", namespace="prod"),
    spec=NS(
        rules=[
            NS(
                host="api.example.com",
                http=NS(
                    paths=[
                        NS(
                            backend=NS(
                                service=NS(
                                    name="api",
                                    port=NS(number=8080),
                                )
                            ),
                            path="/",
                            path_type="Prefix",
                        )
                    ]
                ),
            )
        ],
        ingress_class_name="nginx",
        tls=[NS()],
    ),
    status=NS(load_balancer=NS(ingress=[NS(ip=None, hostname="lb.example.com")])),
)
DAEMON_SET = NS(
    metadata=NS(name="log-agent", namespace="prod"),
    status=NS(
        desired_number_scheduled=4,
        current_number_scheduled=4,
        number_ready=3,
        updated_number_scheduled=4,
        number_available=3,
    ),
    spec=NS(template=NS(spec=NS(node_selector={"role": "worker"}))),
)
STATEFUL_SET = NS(
    metadata=NS(name="postgres", namespace="prod"),
    spec=NS(
        replicas=2,
        service_name="postgres",
        volume_claim_templates=[NS()],
    ),
    status=NS(ready_replicas=1, current_replicas=2, updated_replicas=2),
)
NOW = datetime.now(timezone.utc)
JOB = NS(
    metadata=NS(name="backup", namespace="prod"),
    spec=NS(completions=1, parallelism=1),
    status=NS(
        succeeded=1,
        failed=None,
        active=None,
        start_time=NOW,
        completion_time=NOW,
    ),
)
CRON_JOB = NS(
    metadata=NS(name="nightly-backup", namespace="prod"),
    spec=NS(schedule="0 2 * * *", suspend=False),
    status=NS(active=[], last_schedule_time=NOW),
)
ENDPOINT = NS(
    metadata=NS(name="api", namespace="prod"),
    subsets=[
        NS(
            addresses=[
                NS(
                    ip="10.2.0.5",
                    hostname="api-0",
                    target_ref=NS(kind="Pod", name="api-0"),
                )
            ],
            not_ready_addresses=[
                NS(
                    ip="10.2.0.6",
                    hostname="api-1",
                    target_ref=NS(kind="Pod", name="api-1"),
                )
            ],
            ports=[NS(name="http", port=8080, protocol="TCP")],
        )
    ],
)
HPA = NS(
    metadata=NS(name="api", namespace="prod"),
    spec=NS(
        scale_target_ref=NS(kind="Deployment", name="api"),
        min_replicas=2,
        max_replicas=10,
        metrics=[
            NS(
                type="Resource",
                resource=NS(
                    name="cpu",
                    target=NS(average_value=None, average_utilization=70),
                ),
            )
        ],
    ),
    status=NS(
        current_replicas=3,
        desired_replicas=4,
        current_metrics=[
            NS(
                type="Resource",
                resource=NS(
                    name="cpu",
                    current=NS(average_value=None, average_utilization=82),
                ),
            )
        ],
        conditions=[
            NS(
                type="AbleToScale",
                status="True",
                reason="ReadyForNewScale",
                message="recommended size matches current size",
            )
        ],
    ),
)
DEPLOYMENT = NS(
    metadata=NS(name="api", namespace="prod"),
    spec=NS(
        replicas=1,
        strategy=NS(type="RollingUpdate"),
        selector=NS(match_labels={"app": "api"}),
        template=NS(
            spec=NS(
                affinity=None,
                containers=[
                    NS(
                        name="api",
                        image="registry.example.com/api:latest",
                        resources=NS(requests=None, limits=None),
                        liveness_probe=None,
                        readiness_probe=None,
                        security_context=None,
                    )
                ],
            )
        ),
    ),
)


class ExternalCoreV1:
    def list_namespaced_resource_quota(self, _namespace):
        return listed(QUOTA)

    list_resource_quota_for_all_namespaces = list_namespaced_resource_quota

    def list_persistent_volume(self):
        return listed(PV)

    def list_persistent_volume_claim_for_all_namespaces(self):
        return listed(PVC)

    def list_namespaced_endpoints(self, _namespace):
        return listed(ENDPOINT)

    list_endpoints_for_all_namespaces = list_namespaced_endpoints

    def list_namespaced_pod_disruption_budget(self, _namespace):
        return listed()


class ExternalNetworkingV1:
    def list_namespaced_network_policy(self, _namespace):
        return listed(POLICY)

    list_network_policy_for_all_namespaces = list_namespaced_network_policy

    def list_namespaced_ingress(self, _namespace):
        return listed(INGRESS)

    list_ingress_for_all_namespaces = list_namespaced_ingress


class ExternalAppsV1:
    def list_namespaced_daemon_set(self, _namespace):
        return listed(DAEMON_SET)

    list_daemon_set_for_all_namespaces = list_namespaced_daemon_set

    def list_namespaced_stateful_set(self, _namespace):
        return listed(STATEFUL_SET)

    list_stateful_set_for_all_namespaces = list_namespaced_stateful_set

    def list_namespaced_deployment(self, _namespace):
        return listed(DEPLOYMENT)

    list_deployment_for_all_namespaces = list_namespaced_deployment


class ExternalBatchV1:
    def list_namespaced_job(self, _namespace):
        return listed(JOB)

    list_job_for_all_namespaces = list_namespaced_job

    def list_namespaced_cron_job(self, _namespace):
        return listed(CRON_JOB)

    list_cron_job_for_all_namespaces = list_namespaced_cron_job


class ExternalAutoscalingV2:
    def list_namespaced_horizontal_pod_autoscaler(self, _namespace):
        return listed(HPA)

    list_horizontal_pod_autoscaler_for_all_namespaces = list_namespaced_horizontal_pod_autoscaler


@pytest.fixture
def kubernetes_analysis_runtime():
    with (
        patch.object(analysis, "prepare_context"),
        patch.object(analysis, "get_current_cluster_name", return_value="prod-a"),
        patch.object(analysis.client, "CoreV1Api", ExternalCoreV1),
        patch.object(analysis.client, "NetworkingV1Api", ExternalNetworkingV1),
        patch.object(analysis.client, "AppsV1Api", ExternalAppsV1),
        patch.object(analysis.client, "BatchV1Api", ExternalBatchV1),
        patch.object(
            analysis.client,
            "AutoscalingV2Api",
            ExternalAutoscalingV2,
        ),
        patch.object(
            report_renderers,
            "dispatch_tool_result_report",
            return_value=None,
        ),
    ):
        yield


def test_resource_quota_analysis_calculates_usage(kubernetes_analysis_runtime):
    result = json.loads(analysis.check_kubernetes_resource_quotas.invoke({"namespace": "prod"}))

    assert result[0]["usage_percentage"] == {
        "requests.cpu": 50.0,
        "pods": 60.0,
    }


def test_network_policy_and_ingress_analysis_map_rules_and_backends(
    kubernetes_analysis_runtime,
):
    policies = json.loads(analysis.check_kubernetes_network_policies.invoke({"namespace": "prod"}))
    ingresses = json.loads(analysis.check_kubernetes_ingress.invoke({"namespace": "prod"}))

    assert policies[0] == {
        "name": "deny-by-default",
        "namespace": "prod",
        "pod_selector": {"app": "api"},
        "policy_types": ["Ingress", "Egress"],
        "ingress_rules": 1,
        "egress_rules": 0,
    }
    assert ingresses[0]["hosts"] == ["api.example.com"]
    assert ingresses[0]["load_balancers"] == [{"type": "hostname", "value": "lb.example.com"}]
    assert ingresses[0]["backends"] == [
        {
            "service_name": "api",
            "service_port": 8080,
            "path": "/",
            "path_type": "Prefix",
        }
    ]


def test_persistent_volume_analysis_correlates_claim(
    kubernetes_analysis_runtime,
):
    result = json.loads(analysis.check_kubernetes_persistent_volumes.invoke({}))

    assert result[0]["name"] == "pv-data"
    assert result[0]["claim"] == {
        "name": "data-postgres-0",
        "namespace": "prod",
        "status": "Bound",
    }


def test_daemonset_and_statefulset_status_include_cluster_and_readiness(
    kubernetes_analysis_runtime,
):
    config = {"configurable": {}}
    daemonsets = json.loads(
        analysis.check_kubernetes_daemonsets.invoke(
            {"namespace": "prod", "instance_name": "prod-a"},
            config=config,
        )
    )
    statefulsets = json.loads(
        analysis.check_kubernetes_statefulsets.invoke(
            {"namespace": "prod", "instance_name": "prod-a"},
            config=config,
        )
    )

    assert daemonsets["cluster_name"] == "prod-a"
    assert daemonsets["daemonsets"][0]["ready"] == 3
    assert statefulsets["statefulsets"][0]["ready_replicas"] == 1
    assert statefulsets["statefulsets"][0]["volume_claim_templates"] == 1


def test_job_analysis_reports_job_and_cron_schedule(
    kubernetes_analysis_runtime,
):
    result = json.loads(analysis.check_kubernetes_jobs.invoke({"namespace": "prod"}))

    assert result["jobs"][0]["succeeded"] == 1
    assert result["jobs"][0]["completion_time"] == NOW.isoformat()
    assert result["cronjobs"][0]["schedule"] == "0 2 * * *"
    assert result["cronjobs"][0]["active_jobs"] == 0


def test_endpoint_analysis_separates_ready_and_unready_addresses(
    kubernetes_analysis_runtime,
):
    result = json.loads(analysis.check_kubernetes_endpoints.invoke({"namespace": "prod"}))

    assert result[0]["ready_count"] == 1
    assert result[0]["not_ready_count"] == 1
    assert result[0]["ready_addresses"][0]["target_ref"] == "Pod/api-0"
    assert result[0]["ready_addresses"][0]["ports"] == [{"name": "http", "port": 8080, "protocol": "TCP"}]


def test_hpa_analysis_maps_current_and_target_metrics(
    kubernetes_analysis_runtime,
):
    result = json.loads(analysis.check_kubernetes_hpa_status.invoke({"namespace": "prod"}))

    assert result[0]["target_ref"] == "Deployment/api"
    assert result[0]["target_metrics"][0]["target_value"] == 70
    assert result[0]["current_metrics"][0]["current_value"] == 82
    assert result[0]["conditions"][0]["reason"] == "ReadyForNewScale"


def test_deployment_configuration_analysis_reports_operational_risks(
    kubernetes_analysis_runtime,
):
    config = {"configurable": {"execution_id": "exec-analysis-1"}}
    result = json.loads(
        analysis.analyze_deployment_configurations.invoke(
            {
                "namespace": "prod",
                "instance_name": "prod-a",
                "name": "api",
            },
            config=config,
        )
    )

    assert result["cluster_name"] == "prod-a"
    assert result["scope"] == {
        "namespace": "prod",
        "instance_name": "prod-a",
        "name": "api",
        "target_name": "api",
    }
    assert result["total"] == 1
    assert result["problematic"] == 1
    assert result["healthy"] == 0
    assert result["_deployments_full"][0]["issues"] == ["单副本部署，存在单点故障风险"]
    container = result["_deployments_full"][0]["config_analysis"]["containers"][0]
    assert set(container["issues"]) == {
        "未设置资源请求",
        "未设置资源限制",
        "未配置存活探针",
        "未配置就绪探针",
        "使用latest标签",
        "可能以root用户运行",
    }
    assert analysis._take_cached_k8s_analysis_details("exec-analysis-1")


@pytest.mark.parametrize(
    ("user_message", "expected"),
    [
        ("使用技能查看 k8s 集群下所有的工作负载有没有配置问题", True),
        ("先分析全部 Deployment 配置", True),
        ("check all workloads for config issues", True),
        ("检查 api Deployment 的配置", False),
        ("", False),
    ],
)
def test_user_requests_all_workloads_markers(user_message, expected):
    assert analysis.user_requests_all_workloads(user_message) is expected


def test_resolve_deployment_analysis_scope_drops_sample_name_and_system_namespace():
    config = {
        "configurable": {
            "graph_request": NS(
                graph_user_message="查看 k8s 集群下所有工作负载有没有配置问题",
                user_message="查看 k8s 集群下所有工作负载有没有配置问题",
            )
        }
    }
    namespace, name = analysis.resolve_deployment_analysis_scope("kube-system", "coredns", config)
    assert namespace is None
    assert name is None

    # 业务命名空间即使未写进原话也保留，避免误扩全集群打断修复报告
    namespace, name = analysis.resolve_deployment_analysis_scope("bk-lite-scan-fixtures", "scan-fixture-001", config)
    assert namespace == "bk-lite-scan-fixtures"
    assert name is None


def test_analyze_ignores_system_namespace_sample_when_user_asks_all_workloads(
    kubernetes_analysis_runtime,
):
    """全部意图下误传 kube-system + name 时，应扩成全集群分析并保留修复闭环所需明细。"""
    kube_system_a = NS(
        metadata=NS(name="coredns", namespace="kube-system"),
        spec=NS(
            replicas=2,
            strategy=NS(type="RollingUpdate"),
            selector=NS(match_labels={"k8s-app": "kube-dns"}),
            template=NS(
                spec=NS(
                    affinity=NS(),
                    containers=[
                        NS(
                            name="coredns",
                            image="coredns:1.0.0",
                            resources=NS(requests={"cpu": "100m"}, limits={"cpu": "100m"}),
                            liveness_probe=None,
                            readiness_probe=None,
                            security_context=NS(run_as_non_root=True),
                        )
                    ],
                )
            ),
        ),
    )
    fixture_a = NS(
        metadata=NS(name="scan-fixture-001", namespace="bk-lite-scan-fixtures"),
        spec=NS(
            replicas=0,
            strategy=NS(type="RollingUpdate"),
            selector=NS(match_labels={"app": "scan-fixture-001"}),
            template=NS(
                spec=NS(
                    affinity=None,
                    containers=[
                        NS(
                            name="app",
                            image="busybox:latest",
                            resources=NS(requests=None, limits=None),
                            liveness_probe=None,
                            readiness_probe=None,
                            security_context=None,
                        )
                    ],
                )
            ),
        ),
    )

    class ClusterAppsV1(ExternalAppsV1):
        def list_namespaced_deployment(self, namespace):
            items = [d for d in (kube_system_a, fixture_a) if d.metadata.namespace == namespace]
            return listed(*items)

        def list_deployment_for_all_namespaces(self):
            return listed(kube_system_a, fixture_a)

    config = {
        "configurable": {
            "execution_id": "exec-all-workloads-scope",
            "graph_request": NS(
                graph_user_message="查看 k8s 集群下所有工作负载有没有配置问题",
                user_message="查看 k8s 集群下所有工作负载有没有配置问题",
            ),
        }
    }
    with patch.object(analysis.client, "AppsV1Api", ClusterAppsV1):
        result = json.loads(
            analysis.analyze_deployment_configurations.invoke(
                {"namespace": "kube-system", "name": "coredns"},
                config=config,
            )
        )

    assert result.get("scope", {}).get("namespace") in (None, "")
    assert "name" not in result.get("scope", {})
    assert result["total"] == 2
    assert result["returned"] == 2
    assert {item["name"] for item in result["_deployments_full"]} == {
        "coredns",
        "scan-fixture-001",
    }
    assert result.get("issues_detail"), "修复闭环依赖 issues_detail"


def test_analyze_keeps_business_namespace_under_all_workloads(kubernetes_analysis_runtime):
    """全部意图下保留业务 ns，避免误扩后 scope_too_large 导致无修复报告。"""
    fixture_a = NS(
        metadata=NS(name="scan-fixture-001", namespace="bk-lite-scan-fixtures"),
        spec=NS(
            replicas=0,
            strategy=NS(type="RollingUpdate"),
            selector=NS(match_labels={"app": "scan-fixture-001"}),
            template=NS(
                spec=NS(
                    affinity=None,
                    containers=[
                        NS(
                            name="app",
                            image="busybox:latest",
                            resources=NS(requests=None, limits=None),
                            liveness_probe=None,
                            readiness_probe=None,
                            security_context=None,
                        )
                    ],
                )
            ),
        ),
    )

    class FixtureAppsV1(ExternalAppsV1):
        def list_namespaced_deployment(self, namespace):
            assert namespace == "bk-lite-scan-fixtures"
            return listed(fixture_a)

        def list_deployment_for_all_namespaces(self):
            raise AssertionError("业务 ns 不应被清掉后落到全集群列表")

    config = {
        "configurable": {
            "execution_id": "exec-keep-business-ns",
            "graph_request": NS(
                graph_user_message="查看所有工作负载有没有配置问题",
                user_message="查看所有工作负载有没有配置问题",
            ),
        }
    }
    with patch.object(analysis.client, "AppsV1Api", FixtureAppsV1):
        result = json.loads(
            analysis.analyze_deployment_configurations.invoke(
                {"namespace": "bk-lite-scan-fixtures", "name": "scan-fixture-001"},
                config=config,
            )
        )

    assert result["scope"]["namespace"] == "bk-lite-scan-fixtures"
    assert "name" not in result["scope"]
    assert result["total"] == 1
    assert result["returned"] == 1
    assert result.get("issues_detail")
