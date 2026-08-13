"""MonitorModuleIngestService：按 node_id / cmdb_id / ip+cloud 归并。"""

import pytest

from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPlugin,
    MonitorPluginConfigTemplate,
)
from apps.monitor.services.module_ingest import (
    DEFAULT_HOST_COLLECT_MODULES,
    MonitorModuleIngestService,
)
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


@pytest.mark.django_db
def test_requires_auth_scope(host_object):
    with pytest.raises(ValueError, match="authorization"):
        MonitorModuleIngestService.ingest(_params(allowed_org_ids=[]))

    with pytest.raises(ValueError, match="authorization"):
        MonitorModuleIngestService.ingest(
            {k: v for k, v in _params().items() if k != "allowed_org_ids"}
        )


@pytest.mark.django_db
def test_monitor_ingest_merges_by_node_id(host_object):
    first = MonitorModuleIngestService.ingest(_params())
    assert first["created"] is True
    assert first["updated"] is False
    assert first["id"]

    second = MonitorModuleIngestService.ingest(
        _params(raw={"name": "host-1-renamed", "ip": "10.0.0.2"})
    )
    assert second["updated"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]

    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1
    inst = MonitorInstance.objects.get(id=first["id"])
    assert inst.node_id == "n1"
    assert inst.name == "host-1-renamed"
    assert str(inst.ip) == "10.0.0.2"
    assert MonitorInstanceOrganization.objects.filter(
        monitor_instance=inst, organization=1
    ).exists()


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
    assert existing.name == "from-cmdb-2"


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
def test_cmdb_push_unadapted_object_with_credential_does_not_create(
    host_object, mock_collect_apply
):
    """适配范围外（如 switch）即使带凭据也不创建，只做关联。"""
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
    assert existing.name == "sw-renamed"


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

    result = MonitorModuleIngestService.ingest(
        _params(link_ids={"node_id": "n-new"}, raw={"name": "from-node", "ip": "10.0.0.1"})
    )

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

    result = MonitorModuleIngestService.ingest(
        _params(link_ids={"node_id": "n-new"}, raw={"ip": "10.0.0.1"})
    )

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
    created = MonitorModuleIngestService.ingest(
        _params(link_ids={"node_id": "n-unlink", "cmdb_id": "77"})
    )
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
def test_node_push_create_applies_default_host_collect(
    host_object, host_plugin, mock_collect_apply
):
    result = MonitorModuleIngestService.ingest(_params())

    assert result["created"] is True
    assert "collect_error" not in result
    mock_collect_apply.assert_called_once()
    payload = mock_collect_apply.call_args.args[0]
    assert payload["collector"] == "Telegraf"
    assert payload["collect_type"] == "host"
    assert payload["monitor_object_id"] == host_object.id
    assert [c["type"] for c in payload["configs"]] == [
        "cpu", "disk", "diskio", "mem", "net", "processes", "system",
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

    second = MonitorModuleIngestService.ingest(
        _params(raw={"name": "renamed", "ip": "10.0.0.2"})
    )

    assert second["updated"] is True
    mock_collect_apply.assert_not_called()


@pytest.mark.django_db
def test_node_push_collect_failure_does_not_keep_instance(host_object, mock_collect_apply):
    mock_collect_apply.side_effect = RuntimeError("controller boom")

    with pytest.raises(RuntimeError, match="controller boom"):
        MonitorModuleIngestService.ingest(_params())

    assert MonitorInstance.objects.count() == 0


@pytest.mark.django_db
def test_node_push_selects_host_plugin_by_name_not_smallest_id(
    host_object, host_plugin, mock_collect_apply
):
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
    MonitorPluginConfigTemplate.objects.filter(
        plugin=host_plugin, type="cpu"
    ).delete()

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
def test_cmdb_push_with_credential_creates_remote_instance(
    host_object, mock_collect_apply, mocker, monkeypatch
):
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
def test_cmdb_push_with_private_key_credential_maps_env_fields(
    host_object, mock_collect_apply, mocker, monkeypatch
):
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
def test_cmdb_push_with_credential_falls_back_without_container_node(
    host_object, mock_collect_apply, mocker, monkeypatch
):
    monkeypatch.setattr(
        "apps.monitor.services.module_ingest.CMDB_CREDENTIAL_CREATE_ENABLED",
        True,
    )
    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {"count": 0, "nodes": []}

    result = MonitorModuleIngestService.ingest(
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

    assert result["created"] is True
    assert "container" in result["collect_error"]
    mock_collect_apply.assert_not_called()
    inst = MonitorInstance.objects.get(id=result["id"])
    assert inst.cmdb_id == "44"


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
