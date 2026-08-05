"""CMDB → 监控显式推送：无级联、ID 归并、回声忽略。"""

import pytest

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
def test_cmdb_ingest_create_hook_notifies_peers_without_creating_monitor_asset(mocker):
    """CMDB 主机创建钩子会通知监控，但无凭据时监控不得新建资产。"""
    monitor_ingest = mocker.patch(
        "apps.monitor.services.module_ingest.MonitorModuleIngestService.ingest"
    )
    monitor_ingest.return_value = {
        "id": None,
        "created": False,
        "updated": False,
        "ignored": True,
    }
    node_ingest = mocker.patch(
        "apps.node_mgmt.services.module_ingest.NodeModuleIngestService.ingest"
    )
    node_ingest.return_value = {"id": "n1", "updated": True, "ignored": False}

    result = CmdbToMonitorPushService.best_effort_notify_on_host_create(
        {
            "_id": 88,
            "model_id": "host",
            "inst_name": "h88",
            "ip_addr": "10.0.0.88",
            "cloud": 1,
            "organization": [1],
        },
        operator="alice",
        allowed_org_ids=[1],
    )
    assert monitor_ingest.call_count == 1
    assert "credential" not in (monitor_ingest.call_args.args[0].get("raw") or {})
    assert node_ingest.call_count == 1
    assert result.get("node_id") == "n1"

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
    mocker.patch(
        "apps.monitor.services.node_mgmt.InstanceConfigService.create_monitor_instance_by_node_mgmt",
        return_value=None,
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
    """CMDB 无凭据推送：不新建资产；仅在已有 cmdb_id 关系时更新建链。"""
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_id",
        return_value=_cmdb_instance(node_id=None),
    )
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = (
        lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)
    )

    # 无存量、无凭据 → 忽略创建
    first = CmdbToMonitorPushService.push_instance(
        42, actor_scope={"allowed_org_ids": [1], "operator": "alice"}
    )
    assert first["monitor_result"]["ignored"] is True
    assert first["monitor_result"]["id"] is None
    assert first["node_id"] is None
    assert MonitorInstance.objects.filter(cmdb_id="42").count() == 0

    # 先有按 cmdb_id 关联的监控实例，再推 → 更新建链
    existing = MonitorInstance.objects.create(
        id="('cmdb-42',)",
        name="stock",
        monitor_object=host_object,
        cmdb_id="42",
    )
    second = CmdbToMonitorPushService.push_instance(
        42, actor_scope={"allowed_org_ids": [1], "operator": "alice"}
    )
    assert second["monitor_result"]["updated"] is True
    assert second["monitor_result"]["id"] == existing.id
    assert MonitorInstance.objects.filter(cmdb_id="42", is_deleted=False).count() == 1
    existing.refresh_from_db()
    assert existing.node_id is None
    assert existing.name == "host-from-cmdb"


@pytest.mark.django_db
def test_explicit_push_with_credential_creates(mocker, host_object, monkeypatch):
    """扩展点：打开凭据创建开关后，CMDB 带凭据可建远程资产。"""
    monkeypatch.setattr(
        "apps.monitor.services.module_ingest.CMDB_CREDENTIAL_CREATE_ENABLED",
        True,
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload):
        MonitorInstance.objects.create(
            id="('1_os_10.0.0.42',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mocker.patch(
        "apps.monitor.services.node_mgmt.InstanceConfigService.create_monitor_instance_by_node_mgmt",
        side_effect=_fake_onboarding,
    )

    # 凭据需经 CmdbToMonitorPushService 信封；当前信封未带凭据，直接测 ingest 路径
    result = MonitorModuleIngestService.ingest(
        {
            "source_module": "cmdb",
            "source_id": "42",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {
                "ip": "10.0.0.42",
                "name": "host-from-cmdb",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"username": "root", "password": "s3cret"},
            },
            "link_ids": {"cmdb_id": "42"},
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )
    assert result["created"] is True
    inst = MonitorInstance.objects.get(id="('1_os_10.0.0.42',)")
    assert inst.cmdb_id == "42"


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
