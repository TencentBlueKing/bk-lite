import pytest

from apps.node_mgmt.models import Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


@pytest.fixture
def node(db):
    region = CloudRegion.objects.create(name="default-push")
    n = Node.objects.create(
        id="n-push-1",
        name="push-node",
        ip="10.0.0.9",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=n, organization=1)
    return n


@pytest.mark.django_db
def test_push_cmdb_only_does_not_call_monitor(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 99,
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "u"},
    )

    cmdb.return_value.ingest_from_source.assert_called_once()
    assert monitor.call_count == 0
    node.refresh_from_db()
    assert node.cmdb_id == "99"
    assert node.push_status["cmdb"]["state"] == "ok"


@pytest.mark.django_db
def test_push_retries_then_skips(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.side_effect = TimeoutError("x")
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "u"},
        max_attempts=3,
    )

    assert cmdb.return_value.ingest_from_source.call_count == 3
    node.refresh_from_db()
    assert node.push_status["cmdb"]["state"] == "skipped"
    assert node.cmdb_id == ""


@pytest.mark.django_db
def test_push_conflict_skips_without_cmdb_id(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 42,
        "created": False,
        "updated": False,
        "ignored": False,
        "claimed": False,
        "conflict": LINK_CONFLICT,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "u"},
    )

    node.refresh_from_db()
    assert node.push_status["cmdb"]["state"] == "conflict"
    assert node.cmdb_id == ""


@pytest.mark.django_db
def test_push_cmdb_envelope_fields(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 1,
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )

    kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert kwargs["allowed_org_ids"] == [1]
    assert kwargs["operator"] == "alice"
    assert kwargs["source_module"] == "node_mgmt"
    assert kwargs["link_ids"]["node_id"] == node.id
    assert kwargs["raw"]["ip"] == node.ip
    assert kwargs["raw"]["name"] == node.name


@pytest.mark.django_db
def test_push_monitor_calls_monitor_linkage_without_notimplemented(mocker, node):
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")
    monitor.return_value.ingest_from_source.return_value = {
        "id": "mon-1",
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )

    # 仅一侧关联时不做 mutual sync
    monitor.return_value.ingest_from_source.assert_called_once()
    kwargs = monitor.return_value.ingest_from_source.call_args.kwargs
    assert kwargs["allowed_org_ids"] == [1]
    assert kwargs["link_ids"]["node_id"] == node.id
    node.refresh_from_db()
    assert node.monitor_id == "mon-1"
    assert node.push_status["monitor"]["state"] == "ok"


@pytest.mark.django_db
def test_push_monitor_with_existing_cmdb_id_carries_link(mocker, node):
    node.cmdb_id = "1704"
    node.save(update_fields=["cmdb_id"])
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")
    monitor.return_value.ingest_from_source.return_value = {
        "id": "mon-9",
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 1704,
        "updated": True,
        "created": False,
        "ignored": False,
        "claimed": False,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )

    first_monitor_kwargs = monitor.return_value.ingest_from_source.call_args_list[0].kwargs
    assert first_monitor_kwargs["link_ids"]["node_id"] == node.id
    assert first_monitor_kwargs["link_ids"]["cmdb_id"] == "1704"
    node.refresh_from_db()
    assert node.monitor_id == "mon-9"
    # 两侧已齐：应再回写 CMDB（带 monitor_id）
    assert cmdb.return_value.ingest_from_source.call_count >= 1
    cmdb_kwargs = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert cmdb_kwargs["link_ids"]["monitor_id"] == "mon-9"
    assert cmdb_kwargs["link_ids"]["cmdb_id"] == "1704"


@pytest.mark.django_db
def test_push_both_targets_second_gets_first_id(mocker, node):
    cmdb = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb.return_value.ingest_from_source.return_value = {
        "id": 88,
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    monitor = mocker.patch("apps.node_mgmt.services.module_push.MonitorLinkage")
    monitor.return_value.ingest_from_source.return_value = {
        "id": "mon-88",
        "created": True,
        "updated": False,
        "ignored": False,
        "claimed": False,
    }
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.push_node(
        node.id,
        targets=["cmdb", "monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )

    # 主推 monitor（第一次）应已带上刚回填的 cmdb_id，且当时尚无 monitor_id
    main_monitor_kwargs = monitor.return_value.ingest_from_source.call_args_list[0].kwargs
    assert main_monitor_kwargs["link_ids"]["cmdb_id"] == "88"
    assert "monitor_id" not in main_monitor_kwargs["link_ids"]
    node.refresh_from_db()
    assert node.cmdb_id == "88"
    assert node.monitor_id == "mon-88"
    # mutual sync 会再推一次完整 link_ids 到两侧
    assert cmdb.return_value.ingest_from_source.call_count >= 2
    assert monitor.return_value.ingest_from_source.call_count >= 2
    last_cmdb = cmdb.return_value.ingest_from_source.call_args.kwargs
    assert last_cmdb["link_ids"]["monitor_id"] == "mon-88"
