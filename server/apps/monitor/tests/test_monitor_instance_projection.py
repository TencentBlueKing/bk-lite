import types

from apps.monitor.models import Metric, MetricGroup, MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService


def test_monitor_object_service_projects_flow_asset_fields_for_existing_asset_prefill(db):
    queryset = MonitorObjectService._project_instance_identity(MonitorInstance.objects.all())
    sql = str(queryset.query)

    assert '"monitor_monitorinstance"."id"' in sql
    assert '"monitor_monitorinstance"."name"' in sql
    assert '"monitor_monitorinstance"."cloud_region_id"' in sql
    assert '"monitor_monitorinstance"."ip"' in sql
    assert '"monitor_monitorinstance"."fallback_sampling_rate"' in sql
    assert '"monitor_monitorinstance"."enabled_protocols"' not in sql


def test_instance_search_projects_flow_asset_fields_for_existing_asset_prefill(db):
    queryset = InstanceSearch._project_instance_identity(MonitorInstance.objects.all())
    sql = str(queryset.query)

    assert '"monitor_monitorinstance"."id"' in sql
    assert '"monitor_monitorinstance"."name"' in sql
    assert '"monitor_monitorinstance"."cloud_region_id"' in sql
    assert '"monitor_monitorinstance"."ip"' in sql
    assert '"monitor_monitorinstance"."fallback_sampling_rate"' in sql
    assert '"monitor_monitorinstance"."enabled_protocols"' not in sql


def test_monitor_instance_list_returns_flow_asset_fields(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="Switch",
        display_name="Switch",
        default_metric="any({instance_type='switch'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=monitor_object.id,
        cloud_region_id=3,
        ip="10.0.0.12",
        fallback_sampling_rate=2000,
        enabled_protocols=["netflow"],
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=7)
    monkeypatch.setattr(MonitorObjectService, "get_instances_by_metric", lambda *args, **kwargs: {})
    monkeypatch.setattr(MonitorObjectService, "add_attr", lambda result: None)

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=-1,
        name=None,
        qs=MonitorInstance.objects.all(),
    )

    assert data["results"][0] == {
        "instance_id": "('flow-device-1',)",
        "instance_id_values": ["flow-device-1"],
        "instance_name": "Core Switch",
        "agent_id": "",
        "time": "",
        "cloud_region_id": 3,
        "ip": "10.0.0.12",
        "fallback_sampling_rate": 2000,
        "organizations": [7],
    }


def test_monitor_instance_list_item_serializer_includes_flow_asset_fields():
    obj = types.SimpleNamespace(
        id="('flow-device-1',)",
        name="Core Switch",
        cloud_region_id=3,
        ip="10.0.0.12",
        fallback_sampling_rate=2000,
    )

    assert MonitorObjectService._serialize_instance_list_item(
        obj,
        instance_map={},
        org_map={obj.id: {7}},
    ) == {
        "instance_id": "('flow-device-1',)",
        "instance_id_values": ["flow-device-1"],
        "instance_name": "Core Switch",
        "agent_id": "",
        "time": "",
        "cloud_region_id": 3,
        "ip": "10.0.0.12",
        "fallback_sampling_rate": 2000,
        "organizations": [7],
    }


def test_monitor_instance_list_add_metrics_escapes_flow_instance_regex_for_promql(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="Switch",
        display_name="Switch",
        default_metric="any({instance_type='switch'}) by (instance_id)",
        instance_id_keys=["instance_id"],
        supplementary_indicators=["device_total_incoming_netflow_traffic"],
    )
    metric_group = MetricGroup.objects.create(monitor_object=monitor_object, name="Traffic")
    Metric.objects.create(
        monitor_object=monitor_object,
        metric_group=metric_group,
        name="device_total_incoming_netflow_traffic",
        query=(
            "sum(flow_bytes_in{instance_type='switch', collect_type='netflow', __$labels__}) "
            "by (instance_id)"
        ),
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('flow:15:1:10.10.41.149',)",
        name="NetFlow-10.10.41.149",
        monitor_object_id=monitor_object.id,
        cloud_region_id=1,
        ip="10.10.41.149",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    captured_queries = []

    class StubVictoriaMetricsAPI:
        def query(self, query, step="20m"):
            captured_queries.append(query)
            if query == monitor_object.default_metric:
                return {
                    "data": {
                        "result": [
                            {
                                "metric": {
                                    "instance_id": "flow:15:1:10.10.41.149",
                                    "agent_id": "172.18.0.19-1",
                                },
                                "value": [1781234567, "1"],
                            }
                        ]
                    }
                }
            return {"data": {"result": []}}

    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=20,
        name=None,
        qs=MonitorInstance.objects.filter(id=instance.id),
        add_metrics=True,
    )

    assert data["count"] == 1
    assert captured_queries[1] == (
        "sum(flow_bytes_in{instance_type='switch', collect_type='netflow', "
        'instance_id=~"flow:15:1:10\\\\.10\\\\.41\\\\.149"}) by (instance_id)'
    )
