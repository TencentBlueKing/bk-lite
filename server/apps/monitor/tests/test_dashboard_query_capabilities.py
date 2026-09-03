from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, AuthorizedMetricQueryService
from apps.monitor.services.dashboard_query_capabilities import build_dashboard_query, dashboard_query_capability_id, load_dashboard_query_capabilities
from apps.monitor.views.metrics_instance import MetricsInstanceViewSet


def _object(name="Website"):
    return MonitorObject(name=name, instance_id_keys=["instance_id"])


def test_manifest_is_complete_and_content_addressed():
    capabilities = load_dashboard_query_capabilities()

    assert len(capabilities) >= 800
    assert all(capability.id == dashboard_query_capability_id(capability.template) for capability in capabilities.values())


def test_static_capability_injects_authorized_instance_and_server_window():
    capability = next(
        item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names and "__$window__" in item.template
    )

    query = build_dashboard_query(
        capability_id=capability.id,
        monitor_object=_object(),
        instance_ids=("('website-a',)",),
        start=0,
        end=3_600_000,
    )

    assert "__$" not in query
    assert 'instance_id=~"website\\\\-a"' in query
    assert "[1h]" in query


def test_capability_is_bound_to_monitor_object():
    capability = next(item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names)

    with pytest.raises(AuthorizedMetricQueryError, match="查询能力与监控对象不匹配"):
        build_dashboard_query(
            capability_id=capability.id,
            monitor_object=_object("Host"),
            instance_ids=("('host-a',)",),
            start=0,
            end=60_000,
        )


def test_unknown_capability_is_rejected():
    with pytest.raises(AuthorizedMetricQueryError, match="查询能力不存在"):
        build_dashboard_query(
            capability_id="dashboard:v1:ffffffff",
            monitor_object=_object(),
            instance_ids=("('website-a',)",),
            start=0,
            end=60_000,
        )


def test_dynamic_kafka_capability_escapes_dimensions_and_keeps_instance_scope():
    query = build_dashboard_query(
        capability_id="dashboard:dynamic:kafka:current-offset",
        monitor_object=_object("Kafka"),
        instance_ids=("('kafka-a',)",),
        start=0,
        end=60_000,
        params={
            "dimensions": [
                {
                    "consumer_group": 'group"a',
                    "topic": "orders",
                    "partition": "0",
                }
            ]
        },
    )

    assert 'instance_id=~"kafka\\\\-a"' in query
    assert 'consumergroup="group\\"a"' in query
    assert 'topic="orders"' in query


@pytest.mark.parametrize(
    "params",
    ["dimensions", {"dimensions": [{"consumer_group": "group-a", "topic": "x" * 257, "partition": "0"}]}],
)
def test_dynamic_kafka_capability_rejects_unbounded_params(params):
    with pytest.raises(AuthorizedMetricQueryError, match="Kafka 查询"):
        build_dashboard_query(
            capability_id="dashboard:dynamic:kafka:current-offset",
            monitor_object=_object("Kafka"),
            instance_ids=("('kafka-a',)",),
            start=0,
            end=60_000,
            params=params,
        )


def test_raw_promql_rest_actions_are_removed():
    assert not hasattr(MetricsInstanceViewSet, "get_metrics")
    assert not hasattr(MetricsInstanceViewSet, "get_metrics_range")


@pytest.mark.django_db
def test_authorized_service_executes_registered_capability(mocker):
    monitor_object = MonitorObject.objects.create(name="Website", instance_id_keys=["instance_id"])
    instance = MonitorInstance.objects.create(
        id="('website-a',)",
        name="website-a",
        monitor_object=monitor_object,
    )
    capability = next(item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names)
    vm_query = mocker.patch(
        "apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range",
        return_value={"status": "success", "data": {"result": []}},
    )

    result = AuthorizedMetricQueryService(
        user=SimpleNamespace(is_superuser=True),
        current_team=1,
        include_children=False,
    ).query_range(
        {
            "monitor_object_id": monitor_object.id,
            "capability_id": capability.id,
            "instance_ids": [instance.id],
            "start": 0,
            "end": 60_000,
            "step": "60s",
        }
    )

    assert result["status"] == "success"
    assert "__$" not in vm_query.call_args.args[0]


@pytest.mark.django_db
def test_capability_object_mismatch_stops_before_vm(mocker):
    monitor_object = MonitorObject.objects.create(name="Host", instance_id_keys=["instance_id"])
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="host-a",
        monitor_object=monitor_object,
    )
    capability = next(item for item in load_dashboard_query_capabilities().values() if "Website" in item.object_names)
    vm_query = mocker.patch("apps.monitor.services.authorized_metric_query.Metrics.get_metrics_range")

    with pytest.raises(AuthorizedMetricQueryError, match="查询能力与监控对象不匹配"):
        AuthorizedMetricQueryService(
            user=SimpleNamespace(is_superuser=True),
            current_team=1,
            include_children=False,
        ).query_range(
            {
                "monitor_object_id": monitor_object.id,
                "capability_id": capability.id,
                "instance_ids": [instance.id],
                "start": 0,
                "end": 60_000,
                "step": "60s",
            }
        )

    vm_query.assert_not_called()
