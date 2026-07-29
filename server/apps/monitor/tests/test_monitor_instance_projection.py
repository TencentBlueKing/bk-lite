import types

from apps.monitor.models import (
    Metric,
    MetricGroup,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
)
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.dimension import build_safe_instance_id


def test_monitor_object_service_projects_flow_asset_fields_for_existing_asset_prefill(db):
    queryset = MonitorObjectService._project_instance_identity(MonitorInstance.objects.all())
    sql = str(queryset.query)

    assert '"monitor_monitorinstance"."id"' in sql
    assert '"monitor_monitorinstance"."name"' in sql
    assert '"monitor_monitorinstance"."interval"' in sql
    assert '"monitor_monitorinstance"."cloud_region_id"' in sql
    assert '"monitor_monitorinstance"."ip"' in sql
    assert '"monitor_monitorinstance"."fallback_sampling_rate"' in sql
    assert '"monitor_monitorinstance"."enabled_protocols"' not in sql


def test_instance_search_projects_flow_asset_fields_for_existing_asset_prefill(db):
    queryset = InstanceSearch._project_instance_identity(MonitorInstance.objects.all())
    sql = str(queryset.query)

    assert '"monitor_monitorinstance"."id"' in sql
    assert '"monitor_monitorinstance"."name"' in sql
    assert '"monitor_monitorinstance"."interval"' in sql
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
        interval=60,
        cloud_region_id=3,
        ip="10.0.0.12",
        fallback_sampling_rate=2000,
        enabled_protocols=["netflow"],
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=7)
    monkeypatch.setattr(MonitorObjectService, "get_instances_by_metric", lambda *args, **kwargs: {})
    monkeypatch.setattr(MonitorObjectService, "add_attr", lambda result, visible_organization_ids=None: None)

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
        "interval": 60,
        "agent_id": "",
        "time": "",
        "cloud_region_id": 3,
        "ip": "10.0.0.12",
        "fallback_sampling_rate": 2000,
        "organizations": [7],
    }


def test_monitor_instance_list_hides_sibling_organizations(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="ScopedSwitch",
        default_metric="up",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('shared-flow-device',)",
        name="Shared Switch",
        monitor_object=monitor_object,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=7)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=8)
    monkeypatch.setattr(MonitorObjectService, "get_instances_by_metric", lambda *args, **kwargs: {})

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=-1,
        name=None,
        qs=MonitorInstance.objects.all(),
        visible_organization_ids=frozenset({7}),
    )

    assert data["results"][0]["organizations"] == [7]
    assert data["results"][0]["organization"] == [7]


def test_instance_search_hides_sibling_organizations(db):
    monitor_object = MonitorObject.objects.create(
        name="ScopedPrimary",
        default_metric="up",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('shared-primary',)",
        name="Shared Primary",
        monitor_object=monitor_object,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=7)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=8)

    data = InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": -1},
        qs=MonitorInstance.objects.all(),
        visible_organization_ids=frozenset({7}),
    ).get_objs_v2()

    assert data["results"][0]["organizations"] == [7]


def test_instance_search_response_hides_sibling_organizations(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="ScopedSearch",
        default_metric="up",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('shared-search',)",
        name="Shared Search",
        monitor_object=monitor_object,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=7)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=8)
    search = InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": -1},
        qs=MonitorInstance.objects.all(),
        visible_organization_ids=frozenset({7}),
    )
    monkeypatch.setattr(
        search,
        "get_vm_metrics",
        lambda: [{"metric": {"instance_id": "shared-search"}, "value": [1, "1"]}],
    )

    data = search.search()

    assert data["results"][0]["organizations"] == [7]
    assert data["results"][0]["organization"] == [7]


def test_add_attr_fails_closed_for_empty_or_invalid_visible_scope(db):
    monitor_object = MonitorObject.objects.create(name="ScopedAddAttr", default_metric="up")
    instance = MonitorInstance.objects.create(id="('add-attr',)", name="Add Attr", monitor_object=monitor_object)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=7)
    invalid_scopes = ([], [True], [1.5], ["01"])

    for visible_scope in invalid_scopes:
        item = {"instance_id": instance.id, "time": 1}
        MonitorObjectService.add_attr([item], visible_scope)
        assert item["organizations"] == []
        assert item["organization"] == []


def test_add_attr_keeps_legacy_background_scope_when_projection_is_not_requested(db):
    monitor_object = MonitorObject.objects.create(name="BackgroundAddAttr", default_metric="up")
    instance = MonitorInstance.objects.create(id="('background',)", name="Background", monitor_object=monitor_object)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=7)
    item = {"instance_id": instance.id, "time": 1}

    MonitorObjectService.add_attr([item])

    assert item["organizations"] == [7]
    assert item["organization"] == [7]


def test_monitor_instance_list_filters_instances_by_plugin_status_query(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        default_metric="any({instance_type='os'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(
        name="Host",
        display_name="Host",
        collector="Telegraf",
        collect_type="host",
        status_query="any({instance_type='os', collect_type='host'}) by (instance_id)",
    )
    plugin.monitor_object.add(monitor_object)
    active_instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object_id=monitor_object.id,
    )
    MonitorInstance.objects.create(
        id="('host-b',)",
        name="Host B",
        monitor_object_id=monitor_object.id,
    )
    captured_metrics = []

    def fake_get_instances_by_metric(metric, instance_id_keys):
        captured_metrics.append(metric)
        if metric == plugin.status_query:
            return {
                active_instance.id: {
                    "instance_id": active_instance.id,
                    "agent_id": "agent-a",
                    "time": 1781589583,
                }
            }
        return {
            "('host-a',)": {
                "instance_id": "('host-a',)",
                "agent_id": "agent-a",
                "time": 1781589583,
            },
            "('host-b',)": {
                "instance_id": "('host-b',)",
                "agent_id": "agent-b",
                "time": 1781589583,
            },
        }

    monkeypatch.setattr(
        MonitorObjectService,
        "get_instances_by_metric",
        fake_get_instances_by_metric,
    )
    monkeypatch.setattr(MonitorObjectService, "add_attr", lambda result, visible_organization_ids=None: None)

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=-1,
        name=None,
        qs=MonitorInstance.objects.all(),
        monitor_plugin_id=plugin.id,
    )

    assert captured_metrics == [plugin.status_query]
    assert data["count"] == 1
    assert [item["instance_id"] for item in data["results"]] == [active_instance.id]


def test_monitor_instance_list_returns_empty_for_unknown_plugin(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        default_metric="any({instance_type='os'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object_id=monitor_object.id,
    )

    def fake_get_instances_by_metric(metric, instance_id_keys):
        raise AssertionError("unknown plugin should not query the default metric")

    monkeypatch.setattr(
        MonitorObjectService,
        "get_instances_by_metric",
        fake_get_instances_by_metric,
    )

    data = MonitorObjectService.get_monitor_instance(
        monitor_object.id,
        page=1,
        page_size=-1,
        name=None,
        qs=MonitorInstance.objects.all(),
        monitor_plugin_id=999999,
    )

    assert data == {"count": 0, "results": []}


def test_monitor_instance_list_item_serializer_includes_flow_asset_fields():
    obj = types.SimpleNamespace(
        id="('flow-device-1',)",
        name="Core Switch",
        interval=60,
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
        "interval": 60,
        "agent_id": "",
        "time": "",
        "cloud_region_id": 3,
        "ip": "10.0.0.12",
        "fallback_sampling_rate": 2000,
        "organizations": [7],
    }


def test_instance_search_results_include_collection_interval_for_gap_detection(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        default_metric='any({instance_type="os"}) by (instance_id)',
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object_id=monitor_object.id,
        interval=60,
    )
    search = InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": 20},
        qs=MonitorInstance.objects.filter(id=instance.id),
    )
    monkeypatch.setattr(
        search,
        "get_vm_metrics",
        lambda: [
            {
                "metric": {"instance_id": "host-a"},
                "value": [1782184800, "1"],
            }
        ],
    )
    monkeypatch.setattr(MonitorObjectService, "add_attr", lambda result, visible_organization_ids=None: None)

    data = search.search()

    assert data["results"][0]["interval"] == 60


def test_instance_search_by_primary_object_supports_negative_page_size_for_all_results(db):
    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        default_metric='any({instance_type="os"}) by (instance_id)',
        instance_id_keys=["instance_id"],
    )
    instance_a = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object_id=monitor_object.id,
    )
    instance_b = MonitorInstance.objects.create(
        id="('host-b',)",
        name="Host B",
        monitor_object_id=monitor_object.id,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance_a.id, organization=7)
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance_b.id, organization=8)

    data = InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": -1},
        qs=MonitorInstance.objects.all(),
    ).search_by_primary_object()

    assert data["count"] == 2
    assert {item["instance_id"] for item in data["results"]} == {instance_a.id, instance_b.id}
    assert {tuple(item["organizations"]) for item in data["results"]} == {(7,), (8,)}


def test_monitor_instance_list_add_metrics_escapes_flow_instance_regex_for_promql(db, monkeypatch):
    logical_id = build_safe_instance_id(1, "10.10.41.149")
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
            "sum(netflow_in_bytes{instance_type='switch', collect_type='netflow', __$labels__}) "
            "by (instance_id)"
        ),
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id=str((logical_id,)),
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
                                    "instance_id": logical_id,
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
        "sum(netflow_in_bytes{instance_type='switch', collect_type='netflow', "
        f'instance_id=~"{logical_id}"}}) by (instance_id)'
    )
