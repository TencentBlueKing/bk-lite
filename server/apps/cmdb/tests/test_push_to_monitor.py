"""CMDB → 监控显式推送：无级联、ID 归并、回声忽略。"""

import pytest

from apps.cmdb.services.module_ingest import CmdbModuleIngestService
from apps.cmdb.services.module_push import CmdbToMonitorPushService
from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.module_ingest import MonitorModuleIngestService


@pytest.fixture
def host_object(db):
    return MonitorObject.objects.create(name="Host", display_name="主机", level="base")


def _cmdb_instance(**overrides):
    base = {
        "_id": 42,
        "model_id": "host",
        "inst_name": "host-from-cmdb",
        "ip_addr": "10.0.0.42",
        "cloud": 1,
        "organization": [1],
        "os_type": "linux",
        "node_id": None,
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_cmdb_ingest_does_not_cascade_to_monitor(mocker):
    """节点→CMDB ingest 不得自动调用监控。"""
    monitor_rpc = mocker.patch("apps.rpc.monitor.Monitor")
    monitor_push = mocker.patch("apps.cmdb.services.module_push.Monitor")
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(CmdbModuleIngestService, "_find_host_by_ip_cloud", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_create_instance",
        return_value={"_id": 99, "node_id": "n-cascade"},
    )
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )

    result = CmdbModuleIngestService.ingest(
        {
            "source_module": "node_mgmt",
            "source_id": "n-cascade",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.7", "cloud_region_id": 1, "organization_ids": [1]},
            "link_ids": {"node_id": "n-cascade"},
            "allowed_org_ids": [1],
            "operator": "tester",
        }
    )

    assert result["created"] is True
    assert monitor_rpc.call_count == 0
    assert monitor_push.call_count == 0
    assert monitor_rpc.return_value.ingest_from_source.call_count == 0


@pytest.mark.django_db
def test_explicit_push_with_node_id_merges_on_monitor(mocker, host_object):
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_id",
        return_value=_cmdb_instance(node_id="n-shared"),
    )
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = (
        lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)
    )

    # 先有同 node_id 的监控实例
    first = MonitorModuleIngestService.ingest(
        {
            "source_module": "node_mgmt",
            "source_id": "n-shared",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {
                "ip": "10.0.0.1",
                "name": "from-node",
                "cloud_region_id": 1,
                "organization_ids": [1],
            },
            "link_ids": {"node_id": "n-shared"},
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )

    push = CmdbToMonitorPushService.push_instance(
        42, actor_scope={"allowed_org_ids": [1], "operator": "alice"}
    )
    monitor_result = push["monitor_result"]
    assert monitor_result["updated"] is True
    assert monitor_result["id"] == first["id"]
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=first["id"])
    assert inst.node_id == "n-shared"
    assert inst.cmdb_id == "42"
    assert inst.name == "host-from-cmdb"


@pytest.mark.django_db
def test_explicit_push_without_node_id_uses_cmdb_id(mocker, host_object):
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_id",
        return_value=_cmdb_instance(node_id=None),
    )
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = (
        lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)
    )

    first = CmdbToMonitorPushService.push_instance(
        42, actor_scope={"allowed_org_ids": [1], "operator": "alice"}
    )
    assert first["monitor_result"]["created"] is True
    assert first["node_id"] is None

    second = CmdbToMonitorPushService.push_instance(
        42, actor_scope={"allowed_org_ids": [1], "operator": "alice"}
    )
    assert second["monitor_result"]["updated"] is True
    assert second["monitor_result"]["id"] == first["monitor_result"]["id"]
    assert MonitorInstance.objects.filter(cmdb_id="42", is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(cmdb_id="42")
    assert inst.node_id is None


@pytest.mark.django_db
def test_push_envelope_carries_causation(mocker, host_object):
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_id",
        return_value=_cmdb_instance(node_id="n1"),
    )
    ingest = mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source
    ingest.return_value = {"id": "m1", "created": True, "updated": False, "ignored": False}

    CmdbToMonitorPushService.push_instance(
        42, actor_scope={"allowed_org_ids": [1], "operator": "alice"}
    )

    kwargs = ingest.call_args.kwargs
    assert kwargs["source_module"] == "cmdb"
    assert kwargs["causation_id"] == "cmdb:42:monitor"
    assert kwargs["link_ids"]["cmdb_id"] == "42"
    assert kwargs["link_ids"]["node_id"] == "n1"


@pytest.mark.django_db
def test_monitor_ingest_ignores_echo(host_object):
    result = MonitorModuleIngestService.ingest(
        {
            "source_module": "monitor",
            "source_id": "m-self",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.9", "name": "echo", "organization_ids": [1]},
            "link_ids": {"cmdb_id": "99"},
            "causation_id": "monitor:m-self:cmdb",
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )
    assert result["ignored"] is True
    assert result["created"] is False
    assert result["updated"] is False
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 0

    by_causation = MonitorModuleIngestService.ingest(
        {
            "source_module": "cmdb",
            "source_id": "1",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.8", "name": "echo2", "organization_ids": [1]},
            "link_ids": {"cmdb_id": "1"},
            "causation_id": "monitor:m1:cmdb",
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )
    assert by_causation["ignored"] is True
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 0
