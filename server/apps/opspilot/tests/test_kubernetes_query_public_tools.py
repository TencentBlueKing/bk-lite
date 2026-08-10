"""Kubernetes 查询公开工具的资源映射与脱敏契约。"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.tools.kubernetes import query


pytestmark = pytest.mark.unit

CREATED = datetime.now(timezone.utc) - timedelta(hours=3)


def listed(*items):
    return NS(items=list(items))


def metadata(name, namespace="prod", labels=None):
    return NS(
        name=name,
        namespace=namespace,
        labels=labels or {},
        creation_timestamp=CREATED,
    )


POD = NS(
    metadata=metadata("api-0"),
    status=NS(
        phase="Running",
        pod_ip="10.2.0.5",
        container_statuses=[
            NS(ready=True, restart_count=1),
            NS(ready=False, restart_count=2),
        ],
    ),
    spec=NS(node_name="worker-1"),
)
DEPLOYMENT = NS(
    metadata=metadata("api"),
    status=NS(ready_replicas=2, updated_replicas=3, available_replicas=2),
    spec=NS(replicas=3),
)
SERVICE = NS(
    metadata=metadata("api"),
    spec=NS(
        type="LoadBalancer",
        cluster_ip="10.96.0.10",
        external_i_ps=[],
        ports=[NS(port=443, target_port=8443, node_port=None, protocol="TCP")],
    ),
    status=NS(
        load_balancer=NS(ingress=[NS(ip="203.0.113.8", hostname=None)])
    ),
)
NODE = NS(
    metadata=metadata(
        "worker-1",
        namespace=None,
        labels={"node-role.kubernetes.io/worker": ""},
    ),
    status=NS(
        conditions=[NS(type="Ready", status="True")],
        node_info=NS(kubelet_version="v1.30.0"),
        addresses=[
            NS(type="InternalIP", address="10.0.0.8"),
            NS(type="ExternalIP", address="203.0.113.9"),
        ],
    ),
)
REPLICA_SET = NS(
    metadata=metadata("api-abc"),
    spec=NS(replicas=3),
    status=NS(replicas=3, ready_replicas=2),
)
DAEMON_SET = NS(
    metadata=metadata("log-agent"),
    status=NS(
        desired_number_scheduled=4,
        current_number_scheduled=4,
        number_ready=3,
        updated_number_scheduled=4,
        number_available=3,
    ),
)
STATEFUL_SET = NS(
    metadata=metadata("postgres"),
    spec=NS(replicas=2),
    status=NS(ready_replicas=1),
)
CONFIG_MAP = NS(metadata=metadata("settings"), data={"mode": "prod"})
SECRET = NS(
    metadata=metadata("database-password"),
    type="Opaque",
    data={"password": "must-not-be-returned"},
)
NAMESPACE = NS(metadata=metadata("prod", namespace=None), status=NS(phase="Active"))
PV = NS(
    metadata=metadata("pv-data", namespace=None),
    spec=NS(
        capacity={"storage": "20Gi"},
        access_modes=["ReadWriteOnce"],
        persistent_volume_reclaim_policy="Retain",
        storage_class_name="fast",
        claim_ref=NS(namespace="prod", name="data-postgres-0"),
    ),
    status=NS(phase="Bound"),
)
PVC = NS(
    metadata=metadata("data-postgres-0"),
    spec=NS(
        volume_name="pv-data",
        access_modes=["ReadWriteOnce"],
        storage_class_name="fast",
    ),
    status=NS(phase="Bound", capacity={"storage": "20Gi"}),
)
EVENT = NS(
    metadata=metadata("api-unhealthy"),
    type="Warning",
    reason="Unhealthy",
    message="Readiness probe failed",
    source=NS(component="kubelet"),
    first_timestamp=CREATED,
    last_timestamp=CREATED,
    count=2,
)


class ExternalCoreV1:
    def list_namespaced_pod(self, **_kwargs):
        return listed(POD)

    list_pod_for_all_namespaces = list_namespaced_pod

    def list_namespaced_service(self, **_kwargs):
        return listed(SERVICE)

    list_service_for_all_namespaces = list_namespaced_service

    def list_node(self, **_kwargs):
        return listed(NODE)

    def list_namespace(self, **_kwargs):
        return listed(NAMESPACE)

    def list_namespaced_config_map(self, **_kwargs):
        return listed(CONFIG_MAP)

    list_config_map_for_all_namespaces = list_namespaced_config_map

    def list_namespaced_secret(self, **_kwargs):
        return listed(SECRET)

    list_secret_for_all_namespaces = list_namespaced_secret

    def list_persistent_volume(self):
        return listed(PV)

    def list_namespaced_persistent_volume_claim(self, **_kwargs):
        return listed(PVC)

    list_persistent_volume_claim_for_all_namespaces = (
        list_namespaced_persistent_volume_claim
    )

    def list_namespaced_event(self, **_kwargs):
        return listed(EVENT)

    list_event_for_all_namespaces = list_namespaced_event


class ExternalAppsV1:
    def list_namespaced_deployment(self, **_kwargs):
        return listed(DEPLOYMENT)

    list_deployment_for_all_namespaces = list_namespaced_deployment

    def list_namespaced_replica_set(self, **_kwargs):
        return listed(REPLICA_SET)

    list_replica_set_for_all_namespaces = list_namespaced_replica_set

    def list_namespaced_daemon_set(self, **_kwargs):
        return listed(DAEMON_SET)

    list_daemon_set_for_all_namespaces = list_namespaced_daemon_set

    def list_namespaced_stateful_set(self, **_kwargs):
        return listed(STATEFUL_SET)

    list_stateful_set_for_all_namespaces = list_namespaced_stateful_set


@pytest.fixture
def kubernetes_query_runtime():
    with (
        patch.object(query, "prepare_context"),
        patch.object(query.client, "CoreV1Api", ExternalCoreV1),
        patch.object(query.client, "AppsV1Api", ExternalAppsV1),
    ):
        yield


def test_get_all_resources_returns_eight_resource_groups_without_secret_values(
    kubernetes_query_runtime,
):
    result = json.loads(
        query.kubectl_get_all_resources.invoke({"namespace": "prod"})
    )

    assert result["namespace"] == "prod"
    assert set(result["resources"]) == {
        "pods",
        "services",
        "deployments",
        "replicasets",
        "daemonsets",
        "statefulsets",
        "configmaps",
        "secrets",
    }
    assert all(group["count"] == 1 for group in result["resources"].values())
    secret = result["resources"]["secrets"]["items"][0]
    assert secret == {
        "name": "database-password",
        "namespace": "prod",
        "type": "Opaque",
        "data_keys": 1,
        "age": "3h",
    }
    assert "must-not-be-returned" not in json.dumps(result)


@pytest.mark.parametrize(
    ("resource_type", "expected_fragments"),
    [
        ("po", ["api-0", "1/2", "Running", "3"]),
        ("deploy", ["api", "2/3", "3", "2"]),
        ("svc", ["api", "LoadBalancer", "203.0.113.8", "443"]),
        ("node", ["worker-1", "Ready", "worker", "v1.30.0"]),
    ],
)
def test_resource_table_formats_are_human_readable(
    kubernetes_query_runtime,
    resource_type,
    expected_fragments,
):
    result = query.kubectl_get_resources.invoke(
        {
            "resource_type": resource_type,
            "namespace": "prod",
            "label_selector": "app=api",
            "field_selector": "status.phase=Running",
            "output_format": "table",
        }
    )

    for fragment in expected_fragments:
        assert fragment in result


@pytest.mark.parametrize(
    ("resource_type", "expected"),
    [
        ("namespaces", ("prod", "Active")),
        ("configmaps", ("settings", 1)),
        ("secrets", ("database-password", 1)),
        ("pv", ("pv-data", "prod/data-postgres-0")),
        ("pvc", ("data-postgres-0", "20Gi")),
        ("events", ("api-unhealthy", "Readiness probe failed")),
        ("rs", ("api-abc", 2)),
        ("ds", ("log-agent", 3)),
        ("sts", ("postgres", "1/2")),
    ],
)
def test_resource_json_aliases_map_kubernetes_fields(
    kubernetes_query_runtime,
    resource_type,
    expected,
):
    result = json.loads(
        query.kubectl_get_resources.invoke(
            {
                "resource_type": resource_type,
                "namespace": "prod",
            }
        )
    )

    assert result["total"] == 1
    assert expected[0] in json.dumps(result["items"][0])
    assert expected[1] in result["items"][0].values()


def test_resource_query_returns_supported_types_for_unknown_resource(
    kubernetes_query_runtime,
):
    result = json.loads(
        query.kubectl_get_resources.invoke(
            {"resource_type": "databaseclusters"}
        )
    )

    assert result["error"] == "暂不支持的资源类型: databaseclusters"
    assert "pods" in result["supported_types"]
