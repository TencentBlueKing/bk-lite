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
    MonitorAlert,
    MonitorPolicy,
    PolicyInstanceBaseline,
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


def test_remove_closes_active_alerts_and_preserves_alert_history(
    db,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    monitor_object = MonitorObject.objects.create(name="RemovalAlertHost", display_name="Removal Alert Host")
    instance = MonitorInstance.objects.create(id="('alert-host',)", name="alert-host", monitor_object=monitor_object)
    other_instance = MonitorInstance.objects.create(id="('other-host',)", name="other-host", monitor_object=monitor_object)
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="removal-alert-policy",
        source={"type": "instance", "values": [instance.id, other_instance.id]},
        algorithm="avg",
    )
    threshold_alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=instance.id,
        metric_instance_id="('alert-host', 'cpu')",
        alert_type="alert",
        status="new",
    )
    no_data_alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=instance.id,
        metric_instance_id="('alert-host', 'status')",
        alert_type="no_data",
        status="new",
    )
    historical_alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=instance.id,
        metric_instance_id="('alert-host', 'memory')",
        alert_type="alert",
        status="recovered",
    )
    unrelated_alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=other_instance.id,
        metric_instance_id="('other-host', 'cpu')",
        alert_type="alert",
        status="new",
    )
    notified = []
    _stub_node_mgmt(monkeypatch)
    monkeypatch.setattr(
        "apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier.notify_alerts",
        lambda self, alerts, action, operator="", reason="", **kwargs: notified.append(
            ([alert.id for alert in alerts], action, operator, reason)
        ),
    )

    with django_capture_on_commit_callbacks(execute=True):
        result = MonitorInstanceRemovalService.remove(
            [instance.id],
            operator="tester",
            reason="manual_instance_deleted",
        )

    threshold_alert.refresh_from_db()
    no_data_alert.refresh_from_db()
    historical_alert.refresh_from_db()
    unrelated_alert.refresh_from_db()
    assert result.closed_alert_count == 2
    assert threshold_alert.status == "closed"
    assert no_data_alert.status == "closed"
    assert threshold_alert.end_event_time is not None
    assert no_data_alert.end_event_time is not None
    assert threshold_alert.operation_logs[-1]["reason"] == "manual_instance_deleted"
    assert threshold_alert.operation_logs[-1]["operator"] == "tester"
    assert historical_alert.status == "recovered"
    assert unrelated_alert.status == "new"
    assert notified == [
        (
            [threshold_alert.id, no_data_alert.id],
            "closed",
            "tester",
            "manual_instance_deleted",
        )
    ]


def test_remove_cleans_only_deleted_instance_policy_baselines(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="RemovalBaselineHost", display_name="Removal Baseline Host")
    removed_instance = MonitorInstance.objects.create(
        id="('baseline-remove',)",
        name="baseline-remove",
        monitor_object=monitor_object,
    )
    kept_instance = MonitorInstance.objects.create(
        id="('baseline-keep',)",
        name="baseline-keep",
        monitor_object=monitor_object,
    )
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="removal-baseline-policy",
        source={"type": "instance", "values": [removed_instance.id, kept_instance.id]},
        algorithm="avg",
    )
    removed_baseline = PolicyInstanceBaseline.objects.create(
        policy=policy,
        monitor_instance_id=removed_instance.id,
        metric_instance_id="('baseline-remove', 'status')",
    )
    kept_baseline = PolicyInstanceBaseline.objects.create(
        policy=policy,
        monitor_instance_id=kept_instance.id,
        metric_instance_id="('baseline-keep', 'status')",
    )
    _stub_node_mgmt(monkeypatch)

    MonitorInstanceRemovalService.remove([removed_instance.id])

    assert not PolicyInstanceBaseline.objects.filter(id=removed_baseline.id).exists()
    assert PolicyInstanceBaseline.objects.filter(id=kept_baseline.id).exists()


def test_remove_notifies_closed_alerts_with_their_policy_context(
    db,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    monitor_object = MonitorObject.objects.create(name="RemovalNotifyHost", display_name="Removal Notify Host")
    instance = MonitorInstance.objects.create(
        id="('notify-remove',)",
        name="notify-remove",
        monitor_object=monitor_object,
    )
    disabled_notice_policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="disabled-notice-policy",
        source={"type": "instance", "values": [instance.id]},
        algorithm="avg",
        notice=False,
    )
    enabled_notice_policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="enabled-notice-policy",
        source={"type": "instance", "values": [instance.id]},
        algorithm="avg",
        notice=True,
    )
    disabled_alert = MonitorAlert.objects.create(
        policy_id=disabled_notice_policy.id,
        monitor_instance_id=instance.id,
        metric_instance_id="('notify-remove', 'cpu')",
        status="new",
    )
    enabled_alert = MonitorAlert.objects.create(
        policy_id=enabled_notice_policy.id,
        monitor_instance_id=instance.id,
        metric_instance_id="('notify-remove', 'memory')",
        status="new",
    )
    notify_calls = []

    class RecordingNotifier:
        def __init__(self, policy=None):
            self.policy = policy

        def notify_alerts(self, alerts, action, **kwargs):
            notify_calls.append(
                (
                    self.policy.id if self.policy else None,
                    [alert.id for alert in alerts],
                    action,
                )
            )

    _stub_node_mgmt(monkeypatch)
    monkeypatch.setattr(
        "apps.monitor.services.monitor_instance_removal.AlertLifecycleNotifier",
        RecordingNotifier,
    )

    with django_capture_on_commit_callbacks(execute=True):
        MonitorInstanceRemovalService.remove([instance.id])

    assert notify_calls == [
        (disabled_notice_policy.id, [disabled_alert.id], "closed"),
        (enabled_notice_policy.id, [enabled_alert.id], "closed"),
    ]


def test_remove_closes_and_notifies_alerts_in_bounded_batches(
    db,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    monitor_object = MonitorObject.objects.create(name="RemovalBatchHost", display_name="Removal Batch Host")
    instance = MonitorInstance.objects.create(
        id="('batch-remove',)",
        name="batch-remove",
        monitor_object=monitor_object,
    )
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="batch-removal-policy",
        source={"type": "instance", "values": [instance.id]},
        algorithm="avg",
    )
    alerts = [
        MonitorAlert.objects.create(
            policy_id=policy.id,
            monitor_instance_id=instance.id,
            metric_instance_id=f"('batch-remove', 'metric-{index}')",
            status="new",
        )
        for index in range(3)
    ]
    notify_batches = []
    _stub_node_mgmt(monkeypatch)
    monkeypatch.setattr(MonitorInstanceRemovalService, "ALERT_BATCH_SIZE", 2)
    monkeypatch.setattr(
        "apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier.notify_alerts",
        lambda self, batch, action, **kwargs: notify_batches.append([alert.id for alert in batch]),
    )

    with django_capture_on_commit_callbacks(execute=True):
        result = MonitorInstanceRemovalService.remove([instance.id])

    assert result.closed_alert_count == 3
    assert notify_batches == [[alerts[0].id, alerts[1].id], [alerts[2].id]]


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
    alert = MonitorAlert.objects.create(
        policy_id=0,
        monitor_instance_id=instance.id,
        metric_instance_id="('keep-me', 'cpu')",
        alert_type="alert",
        status="new",
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
    alert.refresh_from_db()
    assert alert.status == "new"


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
