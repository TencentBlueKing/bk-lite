"""CMDB → 监控显式推送：无级联、ID 归并、回声忽略。"""

import pytest

from apps.cmdb.services.module_push import CmdbToMonitorPushService
from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.services.module_ingest import DEFAULT_HOST_COLLECT_MODULES, MonitorModuleIngestService

INST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


@pytest.fixture
def host_object(db):
    return MonitorObject.objects.create(name="Host", display_name="主机", level="base")


@pytest.fixture
def host_plugin(host_object):
    plugin = MonitorPlugin.objects.create(
        name="Host",
        collector="Telegraf",
        collect_type="host",
    )
    plugin.monitor_object.add(host_object)
    for module in DEFAULT_HOST_COLLECT_MODULES:
        MonitorPluginConfigTemplate.objects.create(
            plugin=plugin,
            type=module,
            config_type="child",
            file_type="toml",
            content="# test",
        )
    return plugin


def _cmdb_instance(**overrides):
    base = {
        "_id": 42,
        "inst_uuid": INST_UUID,
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
    monitor_ingest = mocker.patch("apps.cmdb.services.module_push.Monitor").return_value.ingest_from_source
    monitor_ingest.return_value = {
        "id": None,
        "created": False,
        "updated": False,
        "ignored": True,
    }
    node_ingest = mocker.patch("apps.node_mgmt.services.module_ingest.NodeModuleIngestService.ingest")
    node_ingest.return_value = {"id": "n1", "updated": True, "ignored": False}

    result = CmdbToMonitorPushService.best_effort_notify_on_host_create(
        {
            "_id": 88,
            "inst_uuid": INST_UUID,
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
    envelope = monitor_ingest.call_args.kwargs
    assert envelope["link_ids"]["cmdb_id"] == INST_UUID
    assert envelope["link_ids"]["cmdb_id_aliases"] == ["88"]
    assert "credential" not in (envelope.get("raw") or {})
    assert node_ingest.call_count == 1
    assert result.get("node_id") == "n1"


@pytest.mark.django_db
def test_explicit_push_with_node_id_merges_on_monitor(mocker, host_object, host_plugin):
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_uuid",
        return_value=_cmdb_instance(node_id="n-shared"),
    )
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)
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

    push = CmdbToMonitorPushService.push_instance(INST_UUID, actor_scope={"allowed_org_ids": [1], "operator": "alice"})
    monitor_result = push["monitor_result"]
    assert monitor_result["updated"] is True
    assert monitor_result["id"] == first["id"]
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=first["id"])
    assert inst.node_id == "n-shared"
    assert inst.cmdb_id == INST_UUID
    assert inst.name == "host-from-cmdb"


@pytest.mark.django_db
def test_explicit_push_without_node_id_uses_cmdb_id(mocker, host_object):
    """CMDB 无凭据推送：不新建资产；仅在已有 cmdb_id 关系时更新建链。"""
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_uuid",
        return_value=_cmdb_instance(node_id=None),
    )
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)

    # 无存量、无凭据 → 忽略创建
    first = CmdbToMonitorPushService.push_instance(INST_UUID, actor_scope={"allowed_org_ids": [1], "operator": "alice"})
    assert first["monitor_result"]["ignored"] is True
    assert first["monitor_result"]["id"] is None
    assert first["node_id"] is None
    assert MonitorInstance.objects.filter(cmdb_id=INST_UUID).count() == 0

    # 先有按旧数字 cmdb_id 关联的监控实例，再推 UUID → 命中并升级
    existing = MonitorInstance.objects.create(
        id="('cmdb-42',)",
        name="stock",
        monitor_object=host_object,
        cmdb_id="42",
    )
    second = CmdbToMonitorPushService.push_instance(INST_UUID, actor_scope={"allowed_org_ids": [1], "operator": "alice"})
    assert second["monitor_result"]["updated"] is True
    assert second["monitor_result"]["id"] == existing.id
    assert MonitorInstance.objects.filter(cmdb_id=INST_UUID, is_deleted=False).count() == 1
    existing.refresh_from_db()
    assert existing.node_id is None
    assert existing.cmdb_id == INST_UUID
    assert existing.name == "host-from-cmdb"


@pytest.mark.django_db
def test_explicit_push_with_credential_creates(mocker, host_object):
    """特权入口 push_with_credential：经 Monitor.ingest_from_source 带凭据建远程资产。"""
    remote_plugin = MonitorPlugin.objects.create(
        name="Host Remote",
        collector="Telegraf",
        collect_type="http",
    )
    remote_plugin.monitor_object.add(host_object)
    MonitorPluginConfigTemplate.objects.create(
        plugin=remote_plugin,
        type="host",
        config_type="child",
        file_type="toml",
        content="# test",
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id="('1_os_10.0.0.42',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mocker.patch(
        "apps.monitor.services.node_mgmt.InstanceConfigService.create_monitor_instance_by_node_mgmt",
        side_effect=_fake_onboarding,
    )
    mocker.patch(
        "apps.monitor.services.module_ingest.MonitorModuleIngestService._best_effort_notify_peers_on_create",
        return_value=None,
    )
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)
    backfill = mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        side_effect=lambda instance, monitor_id, **kwargs: {**instance, "monitor_id": monitor_id},
    )

    push = CmdbToMonitorPushService.push_with_credential(
        _cmdb_instance(),
        credential={"username": "root", "password": "s3cret"},
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )
    result = push["monitor_result"]
    assert result["created"] is True
    assert result["id"] == "('1_os_10.0.0.42',)"
    inst = MonitorInstance.objects.get(id="('1_os_10.0.0.42',)")
    assert inst.cmdb_id == INST_UUID
    backfill.assert_called_once()
    assert backfill.call_args.args[1] == "('1_os_10.0.0.42',)"


@pytest.mark.django_db
def test_push_envelope_carries_causation(mocker, host_object):
    mocker.patch(
        "apps.cmdb.services.module_push.InstanceManage.query_entity_by_uuid",
        return_value=_cmdb_instance(node_id="n1"),
    )
    ingest = mocker.patch("apps.cmdb.services.module_push.Monitor").return_value.ingest_from_source
    ingest.return_value = {"id": "m1", "created": True, "updated": False, "ignored": False}

    CmdbToMonitorPushService.push_instance(INST_UUID, actor_scope={"allowed_org_ids": [1], "operator": "alice"})

    kwargs = ingest.call_args.kwargs
    assert kwargs["source_module"] == "cmdb"
    assert kwargs["causation_id"] == f"cmdb:{INST_UUID}:monitor"
    assert kwargs["link_ids"]["cmdb_id"] == INST_UUID
    assert kwargs["link_ids"]["cmdb_id_aliases"] == ["42"]
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
            "source_id": INST_UUID,
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.0.0.8", "name": "echo2", "organization_ids": [1]},
            "link_ids": {"cmdb_id": INST_UUID},
            "causation_id": "monitor:m1:cmdb",
            "allowed_org_ids": [1],
            "operator": "alice",
        }
    )
    assert by_causation["ignored"] is True
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 0
