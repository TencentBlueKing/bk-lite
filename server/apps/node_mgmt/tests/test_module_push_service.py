import pytest
from django.core.cache import cache

from apps.node_mgmt.models import Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


@pytest.fixture(autouse=True)
def _locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "node-mgmt-module-push-service-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


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


def test_monitor_linkage_uses_local_ingest_client(mocker):
    """节点推送已在 server 进程内，监控 ingest 必须本进程执行。

    走真 NATS 时 handler 会再调 NodeMgmt 写采集配置，形成嵌套 RPC + Node 行锁自死锁，
    调用方超时三次后把 push_status 记为 skipped。
    """
    monitor_cls = mocker.patch("apps.node_mgmt.services.module_push.Monitor")
    monitor_cls.return_value.ingest_from_source.return_value = {"id": "mon-1", "created": True}
    from apps.node_mgmt.services.module_push import MonitorLinkage

    result = MonitorLinkage().ingest_from_source(source_module="node_mgmt")

    monitor_cls.assert_called_once_with(is_local_client=True)
    assert result["id"] == "mon-1"


def test_cmdb_linkage_uses_local_ingest_client(mocker):
    """节点推送已在 server 进程内，CMDB ingest 必须本进程执行。

    走真 NATS 时 sidecar 首次注册的 deferred push 会在 RPC 超时三次后
    把 push_status 记为 skipped，安装勾选无法自动落库。
    """
    cmdb_cls = mocker.patch("apps.node_mgmt.services.module_push.CMDB")
    cmdb_cls.return_value.ingest_from_source.return_value = {"id": "c1", "created": True}
    from apps.node_mgmt.services.module_push import CmdbLinkage

    result = CmdbLinkage().ingest_from_source(source_module="node_mgmt")

    cmdb_cls.assert_called_once_with(is_local_client=True)
    assert result["id"] == "c1"


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
    cmdb.assert_called_with(is_local_client=True)
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


def test_consume_deferred_push_matches_install_ip_without_node_id(mocker, node):
    from apps.node_mgmt.services.module_push import ModulePushService

    ModulePushService.remember_deferred_push(
        cloud_region_id=node.cloud_region_id,
        nodes=[{"ip": node.ip}],
        targets=["cmdb", "monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )
    push = mocker.patch.object(ModulePushService, "best_effort_push_node", return_value={"monitor": object()})

    result = ModulePushService.consume_deferred_push_for_node(node)

    assert result is not None
    push.assert_called_once_with(
        node.id,
        targets=["cmdb", "monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )
    from django.core.cache import cache

    from apps.node_mgmt.constants.installer import InstallerConstants

    assert cache.get(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:ip:{node.cloud_region_id}:{node.ip}") is None
    assert ModulePushService.consume_deferred_push_for_node(node) is None
    assert push.call_count == 1


def test_consume_deferred_push_from_install_task_result_when_cache_empty(mocker, node):
    from django.core.cache import cache

    from apps.node_mgmt.constants.installer import InstallerConstants
    from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
    from apps.node_mgmt.services.module_push import ModulePushService

    task = ControllerTask.objects.create(
        cloud_region=node.cloud_region,
        type="install",
        status="waiting",
        package_version_id=1,
    )
    ControllerTaskNode.objects.create(
        task=task,
        ip=node.ip,
        node_name=node.name,
        os="linux",
        port=22,
        username="root",
        password="x",
        status="waiting",
        result={
            InstallerConstants.MODULE_PUSH_TARGETS_KEY: ["monitor"],
            InstallerConstants.MODULE_PUSH_ACTOR_SCOPE_KEY: {
                "allowed_org_ids": [1],
                "operator": "bob",
            },
        },
    )
    cache.delete(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:ip:{node.cloud_region_id}:{node.ip}")
    cache.delete(f"{InstallerConstants.MODULE_PUSH_INTENT_CACHE_PREFIX}:node:{node.id}")
    push = mocker.patch.object(ModulePushService, "best_effort_push_node", return_value={"monitor": object()})

    result = ModulePushService.consume_deferred_push_for_node(node)

    assert result is not None
    push.assert_called_once_with(
        node.id,
        targets=["monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "bob"},
    )
    task_node = ControllerTaskNode.objects.get(task=task)
    assert task_node.result[InstallerConstants.MODULE_PUSH_CONSUMED_KEY] is True
    assert ModulePushService.consume_deferred_push_for_node(node) is None


def test_remember_deferred_push_log_template_and_params(caplog, node):
    import logging

    from apps.node_mgmt.services.module_push import ModulePushService

    caplog.set_level(logging.INFO, logger="node")
    count = ModulePushService.remember_deferred_push(
        cloud_region_id=node.cloud_region_id,
        nodes=[{"ip": node.ip, "node_id": "pending-1"}],
        targets=["cmdb", "monitor"],
        actor_scope={"allowed_org_ids": [1], "operator": "alice"},
    )

    assert count == 1
    records = [r for r in caplog.records if r.name == "node" and "remembered deferred push" in (r.msg or "")]
    assert len(records) == 1
    record = records[0]
    assert "%s" in record.msg
    assert record.args == (node.cloud_region_id, 1, ["cmdb", "monitor"])
    formatted = record.msg % record.args
    assert str(node.cloud_region_id) in formatted
    assert "cmdb" in formatted
    assert "monitor" in formatted
    assert "pending-1" not in formatted
    assert "password" not in formatted.lower()
