"""MonitorModuleIngestService：按 node_id / cmdb_id / ip+cloud / 同名 归并。"""

import pytest

from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.services.module_ingest import DEFAULT_HOST_COLLECT_MODULES, MonitorModuleIngestService
from apps.monitor.utils.dimension import build_safe_instance_id, normalize_instance_identity
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


@pytest.fixture
def host_object(db):
    return MonitorObject.objects.create(name="Host", display_name="主机", level="base")


@pytest.fixture(autouse=True)
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


@pytest.fixture(autouse=True)
def mock_collect_apply(mocker):
    """隔离采集模板套用：ingest 单测不触达 Controller / node_mgmt RPC。"""
    return mocker.patch(
        "apps.monitor.services.node_mgmt.InstanceConfigService.create_monitor_instance_by_node_mgmt",
        return_value=None,
    )


@pytest.fixture(autouse=True)
def mock_peer_notify(mocker):
    """隔离创建后的 CMDB 回写；本地仍按 IP+云区域补 node_id。"""

    def _notify(instance, *, operator, allowed_org_ids):
        if instance.node_id:
            return
        linked = MonitorModuleIngestService._best_effort_auto_link_node(
            monitor_id=instance.id,
            ip=str(instance.ip) if instance.ip else None,
            cloud=instance.cloud_region_id,
        )
        if not linked:
            return
        instance.node_id = linked
        instance.save(update_fields=["node_id", "updated_at"])

    return mocker.patch(
        "apps.monitor.services.module_ingest.MonitorModuleIngestService._best_effort_notify_peers_on_create",
        side_effect=_notify,
    )


def _create_named_plugin(name, *, monitor_object, collect_type, config_type, instance_fact_bindings=None):
    plugin = MonitorPlugin.objects.create(
        name=name,
        collector="Telegraf",
        collect_type=collect_type,
        instance_fact_bindings=instance_fact_bindings or [],
    )
    plugin.monitor_object.add(monitor_object)
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type=config_type,
        config_type="child",
        file_type="toml",
        content="# test",
    )
    return plugin


def _ip_fact_binding(field: str) -> list[dict]:
    return [
        {
            "fact": "asset.ip",
            "value_type": "ip",
            "resolver": "input",
            "options": {"field": field},
        }
    ]


@pytest.fixture
def host_remote_plugin(host_object):
    return _create_named_plugin(
        "Host Remote",
        monitor_object=host_object,
        collect_type="http",
        config_type="host",
    )


def _params(**overrides):
    base = {
        "source_module": "node_mgmt",
        "source_id": "n1",
        "event_type": "upsert",
        "occurred_at": "2026-08-05T12:00:00Z",
        "raw": {
            "ip": "10.0.0.1",
            "name": "host-1",
            "cloud_region_id": 1,
            "organization_ids": [1],
        },
        "link_ids": {"node_id": "n1"},
        "allowed_org_ids": [1],
        "operator": "alice",
    }
    default_raw = dict(base["raw"])
    base.update(overrides)
    if isinstance(overrides.get("raw"), dict):
        raw = dict(default_raw)
        raw.update(overrides["raw"])
        base["raw"] = raw
    if isinstance(overrides.get("link_ids"), dict):
        base["link_ids"] = dict(overrides["link_ids"])
    return base


def _network_storage_key(cloud, ip):
    return normalize_instance_identity(build_safe_instance_id(cloud, ip))["storage_instance_key"]


def test_network_device_storage_key_uses_monitor_identity_adapter():
    from apps.monitor.services.node_mgmt import InstanceConfigService

    raw_id = "1_switch_snmp_10.0.0.100"
    key = MonitorModuleIngestService._storage_key_after_onboarding(
        model_id="switch",
        raw_instance_id=raw_id,
        cloud=1,
        ip="10.0.0.100",
    )
    prepared = InstanceConfigService._prepare_network_device_identity_instances([{"instance_id": raw_id, "ip": "10.0.0.100", "cloud_region_id": 1}])
    assert key == prepared[0]["storage_instance_key"]
    assert key != normalize_instance_identity(raw_id)["storage_instance_key"]


@pytest.mark.django_db
def test_requires_auth_scope(host_object):
    with pytest.raises(ValueError, match="authorization"):
        MonitorModuleIngestService.ingest(_params(allowed_org_ids=[]))

    with pytest.raises(ValueError, match="authorization"):
        MonitorModuleIngestService.ingest({k: v for k, v in _params().items() if k != "allowed_org_ids"})


@pytest.mark.django_db
def test_monitor_ingest_merges_by_node_id(host_object):
    first = MonitorModuleIngestService.ingest(_params())
    assert first["created"] is True
    assert first["updated"] is False
    assert first["id"]

    second = MonitorModuleIngestService.ingest(_params(raw={"name": "host-1-renamed", "ip": "10.0.0.2"}))
    assert second["updated"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]

    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=first["id"])
    assert inst.node_id == "n1"
    assert inst.name == "host-1-renamed"
    assert str(inst.ip) == "10.0.0.2"
    assert MonitorInstanceOrganization.objects.filter(monitor_instance=inst, organization=1).exists()


@pytest.mark.django_db
def test_monitor_ingest_by_cmdb_id_updates_existing(host_object):
    existing = MonitorInstance.objects.create(
        id="('cmdb-stock',)",
        name="from-cmdb",
        monitor_object=host_object,
        cmdb_id="42",
    )

    again = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="42",
            link_ids={"cmdb_id": "42"},
            raw={"name": "from-cmdb-2", "ip": "10.0.0.9"},
        )
    )
    assert again["updated"] is True
    assert again["id"] == existing.id
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    existing.refresh_from_db()
    assert existing.name == "from-cmdb"


@pytest.mark.django_db
def test_cmdb_uncredentialed_hit_links_ids_without_renaming(host_object):
    existing = MonitorInstance.objects.create(
        id="('stock-host',)",
        name="keep-my-name",
        monitor_object=host_object,
        ip="10.0.0.42",
        cloud_region_id=1,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
            link_ids={"cmdb_id": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e", "node_id": "n-host"},
            raw={
                "name": "cmdb-name-must-not-win",
                "ip": "10.0.0.42",
                "cloud_region_id": 1,
                "model_id": "host",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    assert result["ignored"] is False
    assert result.get("conflict") in (None, "")
    existing.refresh_from_db()
    assert existing.name == "keep-my-name"
    assert existing.cmdb_id == "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    assert existing.node_id == "n-host"
    assert str(existing.ip) == "10.0.0.42"
    assert not MonitorInstanceOrganization.objects.filter(monitor_instance=existing).exists()


@pytest.mark.django_db
def test_cmdb_uncredentialed_hit_stays_link_only_when_create_switch_on(host_object, monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.services.module_ingest.CMDB_CREDENTIAL_CREATE_ENABLED",
        True,
    )
    existing = MonitorInstance.objects.create(
        id="('stock-host-flag-on',)",
        name="keep-my-name",
        monitor_object=host_object,
        ip="10.0.0.43",
        cloud_region_id=1,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="flag-on-cmdb",
            link_ids={"cmdb_id": "flag-on-cmdb"},
            raw={
                "name": "cmdb-name-must-not-win",
                "ip": "10.0.0.43",
                "cloud_region_id": 1,
                "model_id": "host",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.name == "keep-my-name"
    assert existing.cmdb_id == "flag-on-cmdb"


@pytest.mark.django_db
def test_cmdb_uncredentialed_claims_switch_by_ip_cloud(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    existing = MonitorInstance.objects.create(
        id="('sw-1',)",
        name="core-sw",
        monitor_object=switch_object,
        ip="10.0.0.100",
        cloud_region_id=1,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-uuid",
            link_ids={"cmdb_id": "sw-uuid"},
            raw={
                "name": "cmdb-sw",
                "ip": "10.0.0.100",
                "cloud_region_id": 1,
                "model_id": "switch",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.cmdb_id == "sw-uuid"
    assert existing.name == "core-sw"
    assert existing.node_id in (None, "")


@pytest.mark.django_db
def test_cmdb_uncredentialed_claims_monitor_ui_switch_without_ip_column(db):
    """监控中心手动接入的交换机只写 adapter 主键和默认名，不填 ip/cloud 列。"""
    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    ip = "10.10.69.246"
    existing = MonitorInstance.objects.create(
        id=_network_storage_key(1, ip),
        name=f"{ip}-switch",
        monitor_object=switch_object,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-uuid",
            link_ids={"cmdb_id": "sw-uuid"},
            raw={
                "ip": ip,
                "cloud_region_id": 1,
                "model_id": "switch",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.cmdb_id == "sw-uuid"
    assert existing.name == f"{ip}-switch"
    assert existing.ip in (None, "")


@pytest.mark.django_db
def test_cmdb_uncredentialed_claims_monitor_ui_switch_when_cmdb_has_no_cloud(db):
    """CMDB 交换机通常没有 cloud；监控侧 cloud 只编码在主键里时仍应按 IP 认领。"""
    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    ip = "10.10.69.246"
    existing = MonitorInstance.objects.create(
        id=_network_storage_key(1, ip),
        name=f"{ip}-switch",
        monitor_object=switch_object,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-uuid",
            link_ids={"cmdb_id": "sw-uuid"},
            raw={
                "ip": ip,
                "model_id": "switch",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.cmdb_id == "sw-uuid"


@pytest.mark.django_db
def test_cmdb_uncredentialed_claims_switch_when_pk_encodes_name_not_ip(db):
    """现场：接入页把默认名 10.10.69.246-switch 编进主键，ip 列为空。"""
    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    ip = "10.10.69.246"
    existing = MonitorInstance.objects.create(
        id=_network_storage_key(1, f"{ip}-switch"),
        name=f"{ip}-switch",
        monitor_object=switch_object,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-uuid",
            link_ids={"cmdb_id": "sw-uuid"},
            raw={
                "ip": ip,
                "model_id": "switch",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.cmdb_id == "sw-uuid"
    assert existing.name == f"{ip}-switch"
    assert existing.ip in (None, "")


@pytest.mark.django_db
def test_cmdb_uncredentialed_claims_mysql_by_ip_port(db):
    mysql_object = MonitorObject.objects.create(name="Mysql", display_name="Mysql", level="base")
    existing = MonitorInstance.objects.create(
        id="('1_10.0.0.20_3306',)",
        name="db-prod",
        monitor_object=mysql_object,
        ip="10.0.0.20",
        cloud_region_id=1,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="mysql-uuid",
            link_ids={"cmdb_id": "mysql-uuid"},
            raw={
                "ip": "10.0.0.20",
                "cloud_region_id": 1,
                "port": 3306,
                "model_id": "mysql",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.cmdb_id == "mysql-uuid"
    assert existing.name == "db-prod"


@pytest.mark.django_db
def test_cmdb_uncredentialed_does_not_claim_mysql_on_different_port(db):
    mysql_object = MonitorObject.objects.create(name="Mysql", display_name="Mysql", level="base")
    existing = MonitorInstance.objects.create(
        id="('1_10.0.0.20_3307',)",
        name="db-other-port",
        monitor_object=mysql_object,
        ip="10.0.0.20",
        cloud_region_id=1,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="mysql-uuid",
            link_ids={"cmdb_id": "mysql-uuid"},
            raw={
                "ip": "10.0.0.20",
                "cloud_region_id": 1,
                "port": 3306,
                "model_id": "mysql",
                "organization_ids": [1],
            },
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    existing.refresh_from_db()
    assert existing.cmdb_id in (None, "")
    assert MonitorInstance.objects.filter(cmdb_id="mysql-uuid").count() == 0


@pytest.mark.django_db
def test_cmdb_uncredentialed_does_not_claim_host_as_switch(host_object, db):
    MonitorInstance.objects.create(
        id="('host-same-ip',)",
        name="a-host",
        monitor_object=host_object,
        ip="10.0.0.100",
        cloud_region_id=1,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-uuid",
            link_ids={"cmdb_id": "sw-uuid"},
            raw={"ip": "10.0.0.100", "cloud_region_id": 1, "model_id": "switch", "organization_ids": [1]},
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    assert MonitorInstance.objects.filter(cmdb_id="sw-uuid").count() == 0


@pytest.mark.django_db
def test_cmdb_uncredentialed_claims_host_by_exact_name_when_ip_misses(host_object):
    """IP/云区域认领失败时，同名唯一命中可作为最低优先级关联。"""
    existing = MonitorInstance.objects.create(
        id="('host-ecom-inventory-02',)",
        name="host-ecom-inventory-02",
        monitor_object=host_object,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="96ca6630-afda-4916-aba6-76139b311d62",
            link_ids={"cmdb_id": "96ca6630-afda-4916-aba6-76139b311d62"},
            raw={
                "name": "host-ecom-inventory-02",
                "inst_name": "host-ecom-inventory-02",
                "ip": "10.20.1.23",
                "cloud_region_id": 1,
                "model_id": "host",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == existing.id
    existing.refresh_from_db()
    assert existing.cmdb_id == "96ca6630-afda-4916-aba6-76139b311d62"
    assert existing.name == "host-ecom-inventory-02"


@pytest.mark.django_db
def test_cmdb_uncredentialed_prefers_ip_cloud_over_same_name(host_object):
    """同名兜底不得抢过 IP+云区域认领。"""
    by_ip = MonitorInstance.objects.create(
        id="('1_os_10.20.1.23',)",
        name="other-name",
        monitor_object=host_object,
        ip="10.20.1.23",
        cloud_region_id=1,
    )
    MonitorInstance.objects.create(
        id="('named-shell',)",
        name="host-ecom-inventory-02",
        monitor_object=host_object,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="cmdb-uuid",
            link_ids={"cmdb_id": "cmdb-uuid"},
            raw={
                "name": "host-ecom-inventory-02",
                "inst_name": "host-ecom-inventory-02",
                "ip": "10.20.1.23",
                "cloud_region_id": 1,
                "model_id": "host",
                "organization_ids": [1],
            },
        )
    )
    assert result["id"] == by_ip.id
    by_ip.refresh_from_db()
    assert by_ip.cmdb_id == "cmdb-uuid"
    assert MonitorInstance.objects.get(name="host-ecom-inventory-02").cmdb_id in (None, "")


@pytest.mark.django_db
def test_cmdb_uncredentialed_does_not_claim_ambiguous_host_name(host_object):
    MonitorInstance.objects.create(
        id="('dup-a',)",
        name="dup-host",
        monitor_object=host_object,
    )
    MonitorInstance.objects.create(
        id="('dup-b',)",
        name="dup-host",
        monitor_object=host_object,
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="cmdb-uuid",
            link_ids={"cmdb_id": "cmdb-uuid"},
            raw={
                "name": "dup-host",
                "inst_name": "dup-host",
                "ip": "10.20.9.9",
                "cloud_region_id": 1,
                "model_id": "host",
                "organization_ids": [1],
            },
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    assert MonitorInstance.objects.filter(cmdb_id="cmdb-uuid").count() == 0


@pytest.mark.django_db
def test_cmdb_uncredentialed_skips_deleted_instance(host_object):
    MonitorInstance.objects.create(
        id="('gone',)",
        name="deleted",
        monitor_object=host_object,
        ip="10.0.0.8",
        cloud_region_id=1,
        is_deleted=True,
        cmdb_id="gone-uuid",
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="gone-uuid",
            link_ids={"cmdb_id": "gone-uuid"},
            raw={"ip": "10.0.0.8", "cloud_region_id": 1, "model_id": "host"},
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    inst = MonitorInstance.objects.get(id="('gone',)")
    assert inst.is_deleted is True


@pytest.mark.django_db
def test_cmdb_push_without_credential_does_not_create(host_object, mock_collect_apply):
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="42",
            link_ids={"cmdb_id": "42"},
            raw={"name": "from-cmdb", "ip": "10.0.0.9", "organization_ids": [1]},
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    assert MonitorInstance.objects.count() == 0
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_cmdb_push_unadapted_object_with_credential_does_not_create(host_object, mock_collect_apply):
    """全局开关关闭时，适配范围内对象带凭据仍不创建（扫描须显式 allow_credential_create）。"""
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="100",
            link_ids={"cmdb_id": "100"},
            raw={
                "name": "sw-1",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "organization_ids": [1],
                "credential": {"username": "admin", "password": "x"},
            },
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    assert MonitorInstance.objects.count() == 0
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_cmdb_push_unadapted_object_still_links_existing(host_object, mock_collect_apply):
    existing = MonitorInstance.objects.create(
        id="('sw-stock',)",
        name="old-sw",
        monitor_object=host_object,
        cmdb_id="100",
    )
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="100",
            link_ids={"cmdb_id": "100"},
            raw={
                "name": "sw-renamed",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "organization_ids": [1],
                "credential": {"username": "admin", "password": "x"},
            },
        )
    )
    assert result["updated"] is True
    assert result["id"] == existing.id
    mock_collect_apply.assert_not_called()
    existing.refresh_from_db()
    assert existing.name == "old-sw"


@pytest.mark.django_db
def test_node_then_same_node_id_single_instance(host_object):
    a = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "shared-n"}))
    b = MonitorModuleIngestService.ingest(
        _params(
            source_id="shared-n",
            link_ids={"node_id": "shared-n", "cmdb_id": "99"},
            raw={"name": "after-cmdb-link", "ip": "10.0.0.1"},
        )
    )
    assert a["id"] == b["id"]
    assert MonitorInstance.objects.filter(node_id="shared-n", is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=a["id"])
    assert inst.cmdb_id == "99"
    assert inst.name == "after-cmdb-link"


@pytest.mark.django_db
def test_monitor_ingest_claims_by_ip_cloud_when_ids_miss(host_object):
    existing = MonitorInstance.objects.create(
        id="('1_os_10.0.0.1',)",
        name="stock-host",
        monitor_object=host_object,
        ip="10.0.0.1",
        cloud_region_id=1,
    )

    result = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-new"}, raw={"name": "from-node", "ip": "10.0.0.1"}))

    assert result["updated"] is True
    assert result["id"] == existing.id
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    existing.refresh_from_db()
    assert existing.node_id == "n-new"
    assert existing.name == "from-node"


@pytest.mark.django_db
def test_monitor_ingest_ip_cloud_conflict_when_bound_to_other_node(host_object):
    MonitorInstance.objects.create(
        id="('1_os_10.0.0.1',)",
        name="owned",
        monitor_object=host_object,
        ip="10.0.0.1",
        cloud_region_id=1,
        node_id="other-node",
    )

    result = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-new"}, raw={"ip": "10.0.0.1"}))

    assert result["conflict"] == LINK_CONFLICT
    assert result["created"] is False
    assert result["updated"] is False
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    assert not MonitorInstance.objects.filter(node_id="n-new").exists()


@pytest.mark.django_db
def test_link_conflict_when_ids_disagree(host_object):
    by_node = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-a"}))
    by_cmdb = MonitorInstance.objects.create(
        id="('cmdb-77',)",
        name="other",
        monitor_object=host_object,
        cmdb_id="77",
    )
    assert by_node["id"] != by_cmdb.id

    conflict = MonitorModuleIngestService.ingest(
        _params(
            link_ids={"node_id": "n-a", "cmdb_id": "77"},
            raw={"name": "conflict", "ip": "10.0.0.1"},
        )
    )
    assert conflict["conflict"] == LINK_CONFLICT
    assert conflict["created"] is False
    assert conflict["updated"] is False
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 2


@pytest.mark.django_db
def test_lifecycle_retire_soft_deactivates_without_hard_delete(host_object):
    created = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-ret"}))
    inst_id = created["id"]
    assert MonitorInstance.objects.filter(id=inst_id, is_deleted=False, is_active=True).exists()

    result = MonitorModuleIngestService.ingest(
        _params(
            source_id="n-ret",
            event_type="lifecycle",
            link_ids={"node_id": "n-ret", "monitor_id": inst_id},
            raw={"action": "retire"},
        )
    )

    assert result["updated"] is True
    assert result["id"] == inst_id
    # 仍在库中：软删，非物理删除
    assert MonitorInstance.objects.filter(id=inst_id).count() == 1
    inst = MonitorInstance.objects.get(id=inst_id)
    assert inst.is_deleted is True
    assert inst.is_active is False
    assert MonitorInstance.objects.filter(id=inst_id, is_deleted=False).count() == 0


@pytest.mark.django_db
def test_lifecycle_from_cmdb_only_clears_cmdb_id(host_object):
    created = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-unlink", "cmdb_id": "77"}))
    inst = MonitorInstance.objects.get(id=created["id"])
    assert inst.cmdb_id == "77"
    assert inst.node_id == "n-unlink"

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="77",
            event_type="lifecycle",
            link_ids={"cmdb_id": "77", "monitor_id": inst.id},
            raw={"action": "unlink"},
        )
    )
    assert result["updated"] is True
    inst.refresh_from_db()
    assert inst.cmdb_id in (None, "")
    assert inst.node_id == "n-unlink"
    assert inst.is_deleted is False
    assert inst.is_active is True


@pytest.mark.django_db
def test_lifecycle_idempotent_when_already_retired(host_object):
    created = MonitorModuleIngestService.ingest(_params(link_ids={"node_id": "n-ret2"}))
    MonitorModuleIngestService.ingest(
        _params(
            source_id="n-ret2",
            event_type="lifecycle",
            link_ids={"node_id": "n-ret2", "monitor_id": created["id"]},
            raw={"action": "retire"},
        )
    )
    again = MonitorModuleIngestService.ingest(
        _params(
            source_id="n-ret2",
            event_type="lifecycle",
            link_ids={"monitor_id": created["id"]},
            raw={"action": "retire"},
        )
    )
    assert again["ignored"] is True
    assert MonitorInstance.objects.filter(id=created["id"]).count() == 1


# ----- 创建场景分流：模板套用 -----


@pytest.mark.django_db
def test_node_push_create_applies_default_host_collect(host_object, host_plugin, mock_collect_apply):
    result = MonitorModuleIngestService.ingest(_params())

    assert result["created"] is True
    assert "collect_error" not in result
    mock_collect_apply.assert_called_once()
    payload = mock_collect_apply.call_args.args[0]
    assert payload["collector"] == "Telegraf"
    assert payload["collect_type"] == "host"
    assert payload["monitor_object_id"] == host_object.id
    assert [c["type"] for c in payload["configs"]] == [
        "cpu",
        "disk",
        "diskio",
        "mem",
        "net",
        "processes",
        "system",
    ]
    assert all(c["interval"] == 60 for c in payload["configs"])
    instance_payload = payload["instances"][0]
    assert instance_payload["instance_id"] == "1_os_10.0.0.1"
    assert instance_payload["node_ids"] == ["n1"]
    assert instance_payload["group_ids"] == [1]
    assert payload["monitor_plugin_id"] == host_plugin.id


@pytest.mark.django_db
def test_node_push_existing_does_not_apply_collect(host_object, mock_collect_apply):
    from apps.monitor.models import CollectConfig

    first = MonitorModuleIngestService.ingest(_params())
    # 模拟创建时已落下 Telegraf/host 配置；更新分支不应再套模板
    CollectConfig.objects.create(
        id="cfg-existing",
        monitor_instance_id=first["id"],
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
    )
    mock_collect_apply.reset_mock()

    second = MonitorModuleIngestService.ingest(_params(raw={"name": "renamed", "ip": "10.0.0.2"}))

    assert second["updated"] is True
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_node_push_collect_failure_does_not_keep_instance(host_object, mock_collect_apply):
    mock_collect_apply.side_effect = RuntimeError("controller boom")

    with pytest.raises(RuntimeError, match="controller boom"):
        MonitorModuleIngestService.ingest(_params())

    assert MonitorInstance.objects.count() == 0


@pytest.mark.django_db
def test_node_push_selects_host_plugin_by_name_not_smallest_id(host_object, host_plugin, mock_collect_apply):
    host_plugin.delete()
    decoy = MonitorPlugin.objects.create(
        name="Process",
        collector="Telegraf",
        collect_type="host",
    )
    decoy.monitor_object.add(host_object)
    real = MonitorPlugin.objects.create(
        name="Host",
        collector="Telegraf",
        collect_type="host",
    )
    real.monitor_object.add(host_object)
    for module in DEFAULT_HOST_COLLECT_MODULES:
        MonitorPluginConfigTemplate.objects.create(
            plugin=real,
            type=module,
            config_type="child",
            file_type="toml",
            content="# test",
        )
    assert decoy.id < real.id

    MonitorModuleIngestService.ingest(_params())

    payload = mock_collect_apply.call_args.args[0]
    assert payload["monitor_plugin_id"] == real.id


@pytest.mark.django_db
def test_node_push_fails_when_host_plugin_missing(host_object, host_plugin):
    host_plugin.delete()

    with pytest.raises(ValueError, match="Host"):
        MonitorModuleIngestService.ingest(_params())

    assert MonitorInstance.objects.count() == 0


@pytest.mark.django_db
def test_node_push_fails_when_host_templates_incomplete(host_object, host_plugin):
    MonitorPluginConfigTemplate.objects.filter(plugin=host_plugin, type="cpu").delete()

    with pytest.raises(ValueError, match="missing templates"):
        MonitorModuleIngestService.ingest(_params())

    assert MonitorInstance.objects.count() == 0


@pytest.mark.django_db
def test_cmdb_credential_create_disabled_by_default(host_object, mock_collect_apply):
    """凭据创建路径默认关闭：即使带凭据也只关联/忽略。"""
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="42",
            link_ids={"cmdb_id": "42"},
            raw={
                "name": "from-cmdb",
                "ip": "10.0.0.9",
                "organization_ids": [1],
                "credential": {"username": "root", "password": "s3cret"},
            },
        )
    )
    assert result["ignored"] is True
    assert result["id"] is None
    assert MonitorInstance.objects.count() == 0
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_cmdb_push_with_credential_creates_remote_instance(host_object, host_remote_plugin, mock_collect_apply, mocker, monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.services.module_ingest.CMDB_CREDENTIAL_CREATE_ENABLED",
        True,
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id="('1_os_10.0.0.9',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="42",
            link_ids={"cmdb_id": "42"},
            raw={
                "name": "from-cmdb",
                "ip": "10.0.0.9",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {
                    "username": "root",
                    "password": "s3cret",
                    "port": 22,
                },
            },
        )
    )

    assert result["created"] is True
    assert "collect_error" not in result
    payload = mock_collect_apply.call_args.args[0]
    assert payload["collect_type"] == "http"
    assert payload["monitor_plugin_id"] == host_remote_plugin.id
    assert payload["instances"][0]["node_ids"] == ["container-1"]
    assert payload["instances"][0]["instance_id"] == "1_os_10.0.0.9"
    config = payload["configs"][0]
    assert config["type"] == "host"
    assert config["host"] == "10.0.0.9"
    assert config["username"] == "root"
    assert config["auth_type"] == "password"
    assert config["ENV_PASSWORD"] == "s3cret"

    inst = MonitorInstance.objects.get(id="('1_os_10.0.0.9',)")
    assert inst.cmdb_id == "42"
    assert str(inst.ip) == "10.0.0.9"


@pytest.mark.django_db
def test_cmdb_push_with_private_key_credential_maps_env_fields(host_object, host_remote_plugin, mock_collect_apply, mocker, monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.services.module_ingest.CMDB_CREDENTIAL_CREATE_ENABLED",
        True,
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id="('1_os_10.0.0.10',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="43",
            link_ids={"cmdb_id": "43"},
            raw={
                "name": "keyed",
                "ip": "10.0.0.10",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {
                    "username": "ops",
                    "authType": "privateKey",
                    "private_key": "-----BEGIN KEY-----",
                    "passphrase": "pp",
                },
            },
        )
    )

    config = mock_collect_apply.call_args.args[0]["configs"][0]
    assert config["auth_type"] == "private_key"
    assert config["ENV_PRIVATE_KEY_CONTENT"] == "-----BEGIN KEY-----"
    assert config["ENV_PRIVATE_KEY_PASSPHRASE"] == "pp"


@pytest.mark.django_db
def test_cmdb_push_with_credential_fails_without_container_node(host_object, host_remote_plugin, mock_collect_apply, mocker, monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.services.module_ingest.CMDB_CREDENTIAL_CREATE_ENABLED",
        True,
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {"count": 0, "nodes": []}

    with pytest.raises(ValueError, match="container"):
        MonitorModuleIngestService.ingest(
            _params(
                source_module="cmdb",
                source_id="44",
                link_ids={"cmdb_id": "44"},
                raw={
                    "name": "no-collector",
                    "ip": "10.0.0.11",
                    "organization_ids": [1],
                    "credential": {"username": "root", "password": "x"},
                },
            )
        )

    mock_collect_apply.assert_not_called()
    assert MonitorInstance.objects.count() == 0


@pytest.mark.django_db
def test_monitor_create_auto_links_matching_node(host_object, mock_collect_apply, db):
    from apps.node_mgmt.models.cloud_region import CloudRegion
    from apps.node_mgmt.models.sidecar import Node

    region = CloudRegion.objects.create(name="auto-link-region")
    # cloud_region_id 须与 raw.cloud_region_id 一致；用固定 id 不稳，改写 raw 用 region.id
    node = Node.objects.create(
        id="auto-node-1",
        name="auto-node-1",
        ip="10.0.0.1",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    # 模拟非 node_mgmt 来源创建（无 node_id），触发自动关联
    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="other",
            source_id="x",
            link_ids={"cmdb_id": "55"},
            raw={
                "ip": "10.0.0.1",
                "name": "auto-host",
                "cloud_region_id": region.id,
                "organization_ids": [1],
            },
        )
    )
    assert result["created"] is True
    inst = MonitorInstance.objects.get(id=result["id"])
    assert inst.node_id == node.id
    node.refresh_from_db()
    assert node.monitor_id == inst.id
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_allow_credential_create_mysql_builds_database_config(host_object, mock_collect_apply, mocker, db):
    mysql_object = MonitorObject.objects.create(name="Mysql", display_name="MySQL", level="base")
    mysql_plugin = _create_named_plugin(
        "Mysql",
        monitor_object=mysql_object,
        collect_type="database",
        config_type="mysql",
        instance_fact_bindings=_ip_fact_binding("host"),
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id="('1_10.0.0.20_3306',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="db-1",
            link_ids={"cmdb_id": "db-1"},
            allow_credential_create=True,
            raw={
                "name": "mysql-1",
                "ip": "10.0.0.20",
                "port": 3306,
                "model_id": "mysql",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"username": "monitor", "password": "db-secret"},
            },
        )
    )

    assert result["created"] is True
    payload = mock_collect_apply.call_args.args[0]
    assert payload["collect_type"] == "database"
    assert payload["monitor_object_id"] == mysql_object.id
    assert payload["monitor_plugin_id"] == mysql_plugin.id
    assert payload["instances"][0]["ip"] == "10.0.0.20"
    assert payload["instances"][0]["host"] == "10.0.0.20"
    config = payload["configs"][0]
    assert config["type"] == "mysql"
    assert config["host"] == "10.0.0.20"
    assert config["ENV_PASSWORD"] == "db-secret"
    assert MonitorInstance.objects.get(id="('1_10.0.0.20_3306',)").cmdb_id == "db-1"


@pytest.mark.django_db
def test_allow_credential_create_switch_uses_snmp_collect_type(host_object, mock_collect_apply, mocker, db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    switch_plugin = _create_named_plugin(
        "Switch SNMP General",
        monitor_object=switch_object,
        collect_type="snmp",
        config_type="switch",
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    storage_key = _network_storage_key(1, "10.0.0.100")

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id=storage_key,
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-1",
            link_ids={"cmdb_id": "sw-1"},
            allow_credential_create=True,
            raw={
                "name": "sw-1",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"version": "v2", "community": "public"},
            },
        )
    )

    assert result["created"] is True
    assert result["id"] == storage_key
    payload = mock_collect_apply.call_args.args[0]
    assert payload["collect_type"] == "snmp"
    assert payload["monitor_object_id"] == switch_object.id
    assert payload["monitor_plugin_id"] == switch_plugin.id
    assert payload["instances"][0]["ip"] == "10.0.0.100"
    assert payload["instances"][0]["cloud_region_id"] == 1
    assert payload["configs"][0]["community"] == "public"
    assert payload["configs"][0]["version"] == 2
    assert payload["configs"][0]["type"] == "switch"
    assert payload["configs"][0]["timeout"] == 10
    inst = MonitorInstance.objects.get(id=storage_key)
    assert inst.cmdb_id == "sw-1"
    assert inst.ip == "10.0.0.100"
    assert inst.cloud_region_id == 1


@pytest.mark.django_db
def test_allow_credential_create_router_uses_router_config_type(host_object, mock_collect_apply, mocker, db):
    router_object = MonitorObject.objects.create(name="Router", display_name="路由器", level="base")
    router_plugin = _create_named_plugin(
        "Router SNMP General",
        monitor_object=router_object,
        collect_type="snmp",
        config_type="router",
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    storage_key = _network_storage_key(1, "10.0.0.101")

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id=storage_key,
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="rt-1",
            link_ids={"cmdb_id": "rt-1"},
            allow_credential_create=True,
            raw={
                "name": "rt-1",
                "ip": "10.0.0.101",
                "model_id": "router",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"version": "v2", "community": "public"},
            },
        )
    )

    assert result["created"] is True
    assert result["id"] == storage_key
    payload = mock_collect_apply.call_args.args[0]
    assert payload["monitor_plugin_id"] == router_plugin.id
    assert payload["instances"][0]["instance_id"] == "1_router_snmp_10.0.0.101"
    assert payload["instances"][0]["instance_type"] == "router"
    assert payload["instances"][0]["ip"] == "10.0.0.101"
    assert payload["configs"][0]["type"] == "router"
    inst = MonitorInstance.objects.get(id=storage_key)
    assert inst.cmdb_id == "rt-1"
    assert inst.ip == "10.0.0.101"


@pytest.mark.django_db
def test_network_device_reuses_existing_safe_instance_without_recreate(host_object, mock_collect_apply, mocker, db):
    """已有采集配置的实例：只补链路字段，不再次走接入。"""
    from apps.monitor.models import CollectConfig

    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    switch_plugin = _create_named_plugin(
        "Switch SNMP General",
        monitor_object=switch_object,
        collect_type="snmp",
        config_type="switch",
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }
    storage_key = _network_storage_key(1, "10.0.0.100")
    MonitorInstance.objects.create(
        id=storage_key,
        name="10.0.0.100-switch",
        monitor_object=switch_object,
    )
    CollectConfig.objects.create(
        id="cfg-sw-1",
        monitor_instance_id=storage_key,
        monitor_plugin=switch_plugin,
        collector="Telegraf",
        collect_type="snmp",
        config_type="switch",
        is_child=True,
        file_type="toml",
    )

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-1",
            link_ids={"cmdb_id": "sw-1"},
            allow_credential_create=True,
            raw={
                "name": "sw-from-cmdb",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"version": "v2", "community": "public"},
            },
        )
    )

    assert result["created"] is False
    assert result["updated"] is True
    assert result["id"] == storage_key
    mock_collect_apply.assert_not_called()
    inst = MonitorInstance.objects.get(id=storage_key)
    assert inst.cmdb_id == "sw-1"
    assert inst.ip == "10.0.0.100"
    assert inst.cloud_region_id == 1
    assert inst.name == "sw-from-cmdb"


@pytest.mark.django_db
def test_network_device_empty_shell_reonboards_and_uses_cmdb_name(host_object, mock_collect_apply, mocker, db):
    """空壳（无采集配置）必须补接入，并用 CMDB 实例名覆盖乱码/安全 ID 名。"""
    from apps.monitor.models import CollectConfig
    from apps.monitor.utils.dimension import build_safe_instance_id

    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    switch_plugin = _create_named_plugin(
        "Switch SNMP General",
        monitor_object=switch_object,
        collect_type="snmp",
        config_type="switch",
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }
    storage_key = _network_storage_key(1, "10.0.0.100")
    garbled = build_safe_instance_id(1, "10.0.0.100")
    MonitorInstance.objects.create(
        id=storage_key,
        name=garbled,
        monitor_object=switch_object,
    )

    def _fake_onboarding(payload, actor_context=None):
        inst = MonitorInstance.objects.get(id=storage_key)
        inst.name = payload["instances"][0]["instance_name"]
        inst.save(update_fields=["name", "updated_at"])
        CollectConfig.objects.get_or_create(
            id="cfg-sw-reonboard",
            defaults={
                "monitor_instance_id": storage_key,
                "monitor_plugin": switch_plugin,
                "collector": "Telegraf",
                "collect_type": "snmp",
                "config_type": "switch",
                "is_child": True,
                "file_type": "toml",
            },
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-1",
            link_ids={"cmdb_id": "sw-1"},
            allow_credential_create=True,
            raw={
                "name": "10.0.0.100-switch",
                "inst_name": "10.0.0.100-switch",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"version": "v2", "community": "public"},
            },
        )
    )

    assert result["created"] is False
    assert result["updated"] is True
    assert result["id"] == storage_key
    mock_collect_apply.assert_called_once()
    assert mock_collect_apply.call_args.args[0]["instances"][0]["instance_name"] == "10.0.0.100-switch"
    inst = MonitorInstance.objects.get(id=storage_key)
    assert inst.name == "10.0.0.100-switch"
    assert inst.cmdb_id == "sw-1"
    assert CollectConfig.objects.filter(monitor_instance_id=storage_key).exists()


@pytest.mark.django_db
def test_existing_by_cmdb_empty_shell_still_applies_collect(host_object, mock_collect_apply, mocker, db):
    """已按 cmdb_id 命中的空壳：带凭据推送仍须补采集，不能只 update 名称。"""
    from apps.monitor.models import CollectConfig

    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    switch_plugin = _create_named_plugin(
        "Switch SNMP General",
        monitor_object=switch_object,
        collect_type="snmp",
        config_type="switch",
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }
    storage_key = _network_storage_key(1, "10.0.0.100")
    MonitorInstance.objects.create(
        id=storage_key,
        name="MTox-garbled",
        monitor_object=switch_object,
        cmdb_id="sw-1",
        ip="10.0.0.100",
        cloud_region_id=1,
    )

    def _fake_onboarding(payload, actor_context=None):
        inst = MonitorInstance.objects.get(id=storage_key)
        inst.name = payload["instances"][0]["instance_name"]
        inst.save(update_fields=["name", "updated_at"])
        CollectConfig.objects.get_or_create(
            id="cfg-sw-by-cmdb",
            defaults={
                "monitor_instance_id": storage_key,
                "monitor_plugin": switch_plugin,
                "collector": "Telegraf",
                "collect_type": "snmp",
                "config_type": "switch",
                "is_child": True,
                "file_type": "toml",
            },
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-1",
            link_ids={"cmdb_id": "sw-1"},
            allow_credential_create=True,
            raw={
                "name": "sw-from-cmdb",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"version": "v2", "community": "public"},
            },
        )
    )

    assert result["updated"] is True
    assert result["id"] == storage_key
    mock_collect_apply.assert_called_once()
    inst = MonitorInstance.objects.get(id=storage_key)
    assert inst.name == "sw-from-cmdb"
    assert CollectConfig.objects.filter(monitor_instance_id=storage_key).exists()


@pytest.mark.django_db
def test_existing_by_cmdb_with_collect_skips_repeat_credential_push(host_object, mock_collect_apply, mocker, db):
    """已有 cmdb_id 且已有采集：带凭据重复推送应 skipped，不再走接入页。"""
    from apps.monitor.models import CollectConfig

    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    switch_plugin = _create_named_plugin(
        "Switch SNMP General",
        monitor_object=switch_object,
        collect_type="snmp",
        config_type="switch",
    )
    storage_key = _network_storage_key(1, "10.0.0.100")
    MonitorInstance.objects.create(
        id=storage_key,
        name="sw-from-cmdb",
        monitor_object=switch_object,
        cmdb_id="sw-1",
        ip="10.0.0.100",
        cloud_region_id=1,
    )
    CollectConfig.objects.create(
        id="cfg-sw-skip",
        monitor_instance_id=storage_key,
        monitor_plugin=switch_plugin,
        collector="Telegraf",
        collect_type="snmp",
        config_type="switch",
        is_child=True,
        file_type="toml",
    )

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="sw-1",
            link_ids={"cmdb_id": "sw-1"},
            allow_credential_create=True,
            raw={
                "name": "sw-from-cmdb",
                "ip": "10.0.0.100",
                "model_id": "switch",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"version": "v2", "community": "public"},
            },
        )
    )

    assert result["skipped"] is True
    assert result["created"] is False
    assert result["updated"] is False
    assert result["id"] == storage_key
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_allow_credential_create_influxdb_maps_token_to_env_password(host_object, mock_collect_apply, mocker, db):
    influx_object = MonitorObject.objects.create(name="InfluxDB", display_name="InfluxDB", level="base")
    influx_plugin = _create_named_plugin(
        "InfluxDB",
        monitor_object=influx_object,
        collect_type="database",
        config_type="influxdb",
        instance_fact_bindings=_ip_fact_binding("server"),
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id="('1_10.0.0.30',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="inf-1",
            link_ids={"cmdb_id": "inf-1"},
            allow_credential_create=True,
            raw={
                "name": "influx-1",
                "ip": "10.0.0.30",
                "model_id": "influxdb",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {
                    "scheme": "https",
                    "port": 8086,
                    "token": "op-token",
                    "_client_id": "should-not-leak",
                },
            },
        )
    )

    assert result["created"] is True
    payload = mock_collect_apply.call_args.args[0]
    assert payload["monitor_plugin_id"] == influx_plugin.id
    assert payload["instances"][0]["ip"] == "10.0.0.30"
    assert payload["instances"][0]["server"] == "10.0.0.30"
    config = payload["configs"][0]
    assert config["type"] == "influxdb"
    assert config["server"] == "https://10.0.0.30:8086/debug/vars"
    assert config["ENV_PASSWORD"] == "op-token"
    assert "_client_id" not in config


@pytest.mark.django_db
def test_allow_credential_create_mssql_uses_1433_in_instance_id(host_object, mock_collect_apply, mocker, db):
    mssql_object = MonitorObject.objects.create(name="MSSQL", display_name="MSSQL", level="base")
    mssql_plugin = _create_named_plugin(
        "MSSQL",
        monitor_object=mssql_object,
        collect_type="database",
        config_type="mssql",
        instance_fact_bindings=_ip_fact_binding("host"),
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        MonitorInstance.objects.create(
            id="('1_10.0.0.40_1433',)",
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mock_collect_apply.side_effect = _fake_onboarding

    result = MonitorModuleIngestService.ingest(
        _params(
            source_module="cmdb",
            source_id="ms-1",
            link_ids={"cmdb_id": "ms-1"},
            allow_credential_create=True,
            raw={
                "name": "mssql-1",
                "ip": "10.0.0.40",
                "model_id": "mssql",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "credential": {"username": "sa", "password": "secret", "port": 1433},
            },
        )
    )

    assert result["created"] is True
    payload = mock_collect_apply.call_args.args[0]
    assert payload["monitor_plugin_id"] == mssql_plugin.id
    assert payload["instances"][0]["instance_id"] == "1_10.0.0.40_1433"
    assert payload["instances"][0]["host"] == "10.0.0.40"
    assert payload["configs"][0]["port"] == 1433


@pytest.mark.django_db
def test_allow_credential_create_without_named_plugin_does_not_create_shell(host_object, mock_collect_apply, mocker, db):
    MonitorObject.objects.create(name="Mysql", display_name="MySQL", level="base")
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    with pytest.raises(ValueError, match="Mysql"):
        MonitorModuleIngestService.ingest(
            _params(
                source_module="cmdb",
                source_id="db-missing-plugin",
                link_ids={"cmdb_id": "db-missing-plugin"},
                allow_credential_create=True,
                raw={
                    "name": "mysql-1",
                    "ip": "10.0.0.20",
                    "port": 3306,
                    "model_id": "mysql",
                    "cloud_region_id": 1,
                    "organization_ids": [1],
                    "credential": {"username": "monitor", "password": "db-secret"},
                },
            )
        )

    mock_collect_apply.assert_not_called()
    assert MonitorInstance.objects.count() == 0
