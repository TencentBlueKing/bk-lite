import types

import pytest
from django.db import IntegrityError, transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import (
    CollectConfig,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorObjectOrganizationRule,
    MonitorPolicy,
)
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.monitor.services.node_mgmt import InstanceConfigService


def _stub_node_mgmt(monkeypatch, *, child_calls=None, base_calls=None):
    child_calls = child_calls if child_calls is not None else []
    base_calls = base_calls if base_calls is not None else []
    monkeypatch.setattr(
        "apps.monitor.services.monitor_instance_removal.NodeMgmt",
        lambda: types.SimpleNamespace(
            delete_child_configs=lambda ids: child_calls.append(list(ids)),
            delete_configs=lambda ids: base_calls.append(list(ids)),
        ),
    )
    return child_calls, base_calls


def test_remove_physically_deletes_instance_and_configs(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="RemovalHost", display_name="Removal Host")
    instance = MonitorInstance.objects.create(id="('remove-me',)", name="remove-me", monitor_object=monitor_object)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=1)
    rule = MonitorObjectOrganizationRule.objects.create(
        monitor_object=monitor_object,
        name="remove-rule",
        organizations=[1],
        rule={},
        monitor_instance_id=instance.id,
    )
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="remove-policy",
        source={"type": "instance", "values": [instance.id]},
        algorithm="avg",
    )
    child = CollectConfig.objects.create(
        id="remove-child",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )
    base = CollectConfig.objects.create(
        id="remove-base",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="agent",
        file_type="toml",
        is_child=False,
    )
    child_calls, base_calls = _stub_node_mgmt(monkeypatch)

    result = MonitorInstanceRemovalService.remove([instance.id])

    assert result.removed_ids == (instance.id,)
    assert not MonitorInstance.objects.filter(id=instance.id).exists()
    assert not CollectConfig.objects.filter(monitor_instance_id=instance.id).exists()
    assert not MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).exists()
    assert not MonitorObjectOrganizationRule.objects.filter(id=rule.id).exists()
    policy.refresh_from_db()
    assert policy.source == {"type": "instance", "values": []}
    assert policy.enable is False
    assert child_calls == [[child.id]]
    assert base_calls == [[base.id]]


def test_remove_remote_failure_keeps_database_state(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="RemovalFailure", display_name="Removal Failure")
    instance = MonitorInstance.objects.create(id="('keep-me',)", name="keep-me", monitor_object=monitor_object)
    config = CollectConfig.objects.create(
        id="keep-config",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="agent",
        file_type="toml",
        is_child=False,
    )
    monkeypatch.setattr(
        "apps.monitor.services.monitor_instance_removal.NodeMgmt",
        lambda: types.SimpleNamespace(
            delete_child_configs=lambda ids: None,
            delete_configs=lambda ids: (_ for _ in ()).throw(RuntimeError("rpc failed")),
        ),
    )

    with pytest.raises(BaseAppException, match="删除监控实例失败"):
        MonitorInstanceRemovalService.remove([instance.id])

    assert MonitorInstance.objects.filter(id=instance.id).exists()
    assert CollectConfig.objects.filter(id=config.id).exists()


def test_remove_rejects_oversized_batch_before_remote_call(db, monkeypatch):
    remote_called = False

    def build_node_mgmt():
        nonlocal remote_called
        remote_called = True
        return types.SimpleNamespace(delete_child_configs=lambda ids: None, delete_configs=lambda ids: None)

    monkeypatch.setattr("apps.monitor.services.monitor_instance_removal.NodeMgmt", build_node_mgmt)
    instance_ids = [f"instance-{index}" for index in range(MonitorInstanceRemovalService.MAX_BATCH_SIZE + 1)]

    with pytest.raises(BaseAppException, match="单次最多删除"):
        MonitorInstanceRemovalService.remove(instance_ids)

    assert remote_called is False


def test_remove_missing_instance_is_idempotent_without_remote_call(db, monkeypatch):
    remote_calls = []

    def build_node_mgmt():
        return types.SimpleNamespace(
            delete_child_configs=lambda ids: remote_calls.append(("child", ids)),
            delete_configs=lambda ids: remote_calls.append(("base", ids)),
        )

    monkeypatch.setattr("apps.monitor.services.monitor_instance_removal.NodeMgmt", build_node_mgmt)

    result = MonitorInstanceRemovalService.remove(["missing-instance"])

    assert result.removed_ids == ()
    assert result.missing_ids == ("missing-instance",)
    assert remote_calls == []


def test_prepare_rejects_active_instance_owned_by_other_object(db):
    old_object = MonitorObject.objects.create(name="OldObject", display_name="Old Object")
    new_object = MonitorObject.objects.create(name="NewObject", display_name="New Object")
    MonitorInstance.objects.create(id="('shared-id',)", name="old", monitor_object=old_object)

    with transaction.atomic(), pytest.raises(BaseAppException, match="监控实例标识已被占用"):
        InstanceConfigService._prepare_instances_for_creation(
            [{"instance_id": "shared-id", "instance_name": "new", "group_ids": [1]}],
            new_object.id,
            "host",
            "Telegraf",
            [],
        )


def test_create_reclaims_cross_object_tombstone(db, monkeypatch):
    old_object = MonitorObject.objects.create(name="DeletedObject", display_name="Deleted Object")
    new_object = MonitorObject.objects.create(name="ReplacementObject", display_name="Replacement Object")
    tombstone = MonitorInstance.objects.create(
        id="('reusable-id',)",
        name="deleted",
        monitor_object=old_object,
        is_deleted=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=tombstone, organization=9)
    _stub_node_mgmt(monkeypatch)
    monkeypatch.setattr("apps.monitor.services.node_mgmt.Controller", lambda data: types.SimpleNamespace(controller=lambda: None))

    InstanceConfigService.create_monitor_instance_by_node_mgmt(
        {
            "monitor_object_id": new_object.id,
            "collector": "Telegraf",
            "collect_type": "host",
            "configs": [],
            "instances": [{"instance_id": "reusable-id", "instance_name": "replacement", "group_ids": [1]}],
        }
    )

    instance = MonitorInstance.objects.get(id="('reusable-id',)")
    assert instance.monitor_object_id == new_object.id
    assert instance.name == "replacement"
    assert instance.is_deleted is False
    assert set(instance.monitorinstanceorganization_set.values_list("organization", flat=True)) == {1}


def test_prepare_rejects_duplicate_ids_in_one_request(db):
    monitor_object = MonitorObject.objects.create(name="DuplicateObject", display_name="Duplicate Object")
    instances = [
        {"instance_id": "duplicate", "instance_name": "one", "group_ids": [1]},
        {"instance_id": "duplicate", "instance_name": "two", "group_ids": [1]},
    ]

    with transaction.atomic(), pytest.raises(BaseAppException, match="请求中存在重复"):
        InstanceConfigService._prepare_instances_for_creation(instances, monitor_object.id, "host", "Telegraf", [])


def test_create_translates_unique_constraint_race(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="ConcurrentObject", display_name="Concurrent Object")

    def raise_integrity_error(*args, **kwargs):
        raise IntegrityError('duplicate key violates constraint "monitor_monitorinstance_pkey"')

    monkeypatch.setattr(InstanceConfigService, "_create_instances_in_db", raise_integrity_error)

    with pytest.raises(BaseAppException) as exc_info:
        InstanceConfigService.create_monitor_instance_by_node_mgmt(
            {
                "monitor_object_id": monitor_object.id,
                "collector": "Telegraf",
                "collect_type": "host",
                "configs": [],
                "instances": [{"instance_id": "race", "instance_name": "race", "group_ids": [1]}],
            }
        )

    assert "监控实例标识已被占用" in str(exc_info.value)
    assert "monitor_monitorinstance_pkey" not in str(exc_info.value)
