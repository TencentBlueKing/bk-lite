"""监控 → CMDB 显式推送：信封、回填、回声忽略。"""

import pytest

from apps.cmdb.services.module_ingest import CmdbModuleIngestService
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.module_push import MonitorToCmdbPushService, resolve_cmdb_model_id

INST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


@pytest.fixture
def host_object(db):
    return MonitorObject.objects.create(name="Host", display_name="主机", level="base")


@pytest.fixture
def monitor_instance(db, host_object):
    inst = MonitorInstance.objects.create(
        id="mon-push-1",
        name="mon-host",
        monitor_object=host_object,
        ip="10.0.0.55",
        cloud_region_id=1,
        node_id=None,
        cmdb_id=None,
        is_deleted=False,
        is_active=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)
    return inst


@pytest.fixture
def monitor_instance_with_node(db, host_object):
    inst = MonitorInstance.objects.create(
        id="mon-push-n",
        name="mon-with-node",
        monitor_object=host_object,
        ip="10.0.0.56",
        cloud_region_id=1,
        node_id="n-from-mon",
        cmdb_id=None,
        is_deleted=False,
        is_active=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=1)
    return inst


def test_resolve_cmdb_model_prefers_host():
    assert resolve_cmdb_model_id("Host") == "host"
    assert resolve_cmdb_model_id("unknown-obj") == "host"
    assert resolve_cmdb_model_id("switch") == "switch"


@pytest.mark.django_db
def test_push_to_cmdb_with_node_id_passes_link_ids(mocker, monitor_instance_with_node):
    cmdb = mocker.patch("apps.monitor.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": INST_UUID,
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }

    result = MonitorToCmdbPushService.push_instance(
        monitor_instance_with_node.id,
        actor_scope={"allowed_org_ids": [1], "operator": "bob"},
    )

    kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert kwargs["source_module"] == "monitor"
    assert kwargs["causation_id"] == f"monitor:{monitor_instance_with_node.id}:cmdb"
    assert kwargs["link_ids"]["node_id"] == "n-from-mon"
    assert kwargs["raw"]["model_id"] == "host"
    assert kwargs["raw"]["ip"] == "10.0.0.56"
    assert kwargs["allowed_org_ids"] == [1]
    assert result["cmdb_result"]["id"] == INST_UUID

    monitor_instance_with_node.refresh_from_db()
    assert monitor_instance_with_node.cmdb_id == INST_UUID


@pytest.mark.django_db
def test_push_to_cmdb_without_node_id_uses_cmdb_id_when_present(mocker, monitor_instance):
    monitor_instance.cmdb_id = INST_UUID
    monitor_instance.save(update_fields=["cmdb_id"])

    cmdb = mocker.patch("apps.monitor.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": INST_UUID,
        "created": False,
        "updated": True,
        "ignored": False,
        "claimed": False,
    }

    MonitorToCmdbPushService.push_instance(
        monitor_instance.id,
        actor_scope={"allowed_org_ids": [1], "operator": "bob"},
    )

    kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert "node_id" not in kwargs["link_ids"]
    assert kwargs["link_ids"]["cmdb_id"] == INST_UUID
    assert kwargs["causation_id"].startswith("monitor:")


@pytest.mark.django_db
def test_push_to_cmdb_creates_via_real_ingest_without_node_id(mocker, monitor_instance):
    """无 node_id 时走认领/新建；不要求 node_id。"""
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(CmdbModuleIngestService, "_find_host_by_ip_cloud", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_create_instance",
        return_value={"_id": 101, "inst_uuid": INST_UUID, "ip_addr": "10.0.0.55"},
    )
    mocker.patch(
        "apps.monitor.services.module_push.CMDB"
    ).return_value.ingest_from_source.side_effect = lambda **kwargs: CmdbModuleIngestService.ingest(kwargs)

    result = MonitorToCmdbPushService.push_instance(
        monitor_instance.id,
        actor_scope={"allowed_org_ids": [1], "operator": "bob"},
    )
    assert result["cmdb_result"]["created"] is True
    assert result["cmdb_result"]["id"] == INST_UUID
    monitor_instance.refresh_from_db()
    assert monitor_instance.cmdb_id == INST_UUID


@pytest.mark.django_db
def test_cmdb_ingest_ignores_echo():
    result = CmdbModuleIngestService.ingest(
        {
            "source_module": "cmdb",
            "source_id": INST_UUID,
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.1", "cloud_region_id": 1},
            "link_ids": {"cmdb_id": INST_UUID},
            "causation_id": f"cmdb:{INST_UUID}:monitor",
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )
    assert result["ignored"] is True
    assert result["id"] == INST_UUID
    assert result["created"] is False

    by_causation = CmdbModuleIngestService.ingest(
        {
            "source_module": "monitor",
            "source_id": "m1",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.2", "cloud_region_id": 1},
            "link_ids": {"cmdb_id": INST_UUID},
            "causation_id": f"cmdb:{INST_UUID}:monitor",
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )
    assert by_causation["ignored"] is True
