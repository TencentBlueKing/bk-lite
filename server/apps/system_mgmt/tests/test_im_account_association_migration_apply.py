"""在 PostgreSQL 上把 0056 从空库和混合存量都跑一遍。"""

import uuid
from datetime import datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.system_mgmt.models import (
    IMAccountAssociation,
    IMNotificationChannel,
    IMNotificationSyncRun,
    IMNotificationUserMapping,
    IntegrationInstance,
    User,
)

OLD_TARGET = [("system_mgmt", "0055_operationlog_idempotency_key")]
NEW_TARGET = [("system_mgmt", "0056_im_account_association")]


def _leaves():
    executor = MigrationExecutor(connection)
    return [node for node in executor.loader.graph.leaf_nodes() if node[0] == "system_mgmt"]


def _applied():
    return set(MigrationExecutor(connection).loader.applied_migrations)


def _at(*parts):
    return timezone.make_aware(datetime(*parts))


def _columns(table):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return {column.name: column for column in description}


def _constraint_names(table):
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, table))


def _clear_im_rows():
    IMNotificationUserMapping.objects.all().delete()
    IMNotificationSyncRun.objects.all().delete()
    IMNotificationChannel.objects.all().delete()
    IMAccountAssociation.objects.all().delete()


def _assert_schema():
    channel_columns = _columns("system_mgmt_imnotificationchannel")
    mapping_columns = _columns("system_mgmt_imnotificationusermapping")
    run_columns = _columns("system_mgmt_imnotificationsyncrun")
    assert channel_columns["account_association_id"].null_ok is True
    assert "platform_match_field" not in channel_columns
    assert "schedule_config" not in channel_columns
    assert mapping_columns["account_association_id"].null_ok is False
    assert "channel_id" not in mapping_columns
    assert run_columns["account_association_id"].null_ok is False
    assert "channel_id" not in run_columns
    run_constraints = _constraint_names("system_mgmt_imnotificationsyncrun")
    assert "uniq_im_sync_run_guard_per_account_association" in run_constraints
    assert "uniq_im_sync_run_guard_per_channel" not in run_constraints
    if connection.vendor == "postgresql":
        assert "unique_running_im_account_association_sync_run" in run_constraints
        assert "unique_running_im_notification_sync_run_per_channel" not in run_constraints


def _user(prefix, name):
    return User.objects.create(
        user_id=str(uuid.uuid4()),
        username=f"{prefix}-{name}",
        display_name=name,
        email=f"{prefix}-{name}@example.com",
        password="",
        domain="domain.com",
    )


def _instance(prefix, name):
    return IntegrationInstance.objects.create(name=f"{prefix}-{name}", provider_key="feishu", enabled=True, status="ready")


def _channel(model, instance, name, **overrides):
    fields = {
        "name": name,
        "integration_instance_id": instance.id,
        "enabled": True,
        "status": "ready",
        "platform_match_field": "email",
        "external_match_field": "email",
        "external_receive_field": "user_id",
        "schedule_config": {"enabled": False},
        "team": [],
    }
    fields.update(overrides)
    return model.objects.create(**fields)


def _mapping(model, channel, user, identity):
    return model.objects.create(
        channel_id=channel.id,
        user_id=user.id,
        external_identity_key="user_id",
        external_identity_value=identity,
        external_receive_key="user_id",
    )


def _run(model, channel, status, started_at, finished_at=None, running_guard=None):
    return model.objects.create(
        channel_id=channel.id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        running_guard=running_guard,
        summary=status,
    )


def _old_schedule(channel_id, hour, minute):
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(minute),
        hour=str(hour),
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_current_timezone(),
    )
    return PeriodicTask.objects.create(
        name=f"im_notification_channel_{channel_id}",
        task="apps.system_mgmt.tasks.schedule_im_notification_sync",
        crontab=schedule,
        args=f"[{channel_id}]",
        enabled=True,
    )


def _seed(old_apps, prefix):
    channel_model = old_apps.get_model("system_mgmt", "IMNotificationChannel")
    mapping_model = old_apps.get_model("system_mgmt", "IMNotificationUserMapping")
    run_model = old_apps.get_model("system_mgmt", "IMNotificationSyncRun")
    instance_a = _instance(prefix, "甲")
    instance_b = _instance(prefix, "乙")
    shared = _user(prefix, "shared")
    winner = _user(prefix, "winner")
    extra = _user(prefix, "extra")
    other_user = _user(prefix, "other")

    earliest = _channel(
        channel_model,
        instance_a,
        f"{prefix}-定时更早",
        status="pending_sync",
        schedule_config={"enabled": True, "sync_time": "08:30"},
    )
    older = _channel(channel_model, instance_a, f"{prefix}-较早", schedule_config={"enabled": False})
    newer = _channel(
        channel_model,
        instance_a,
        f"{prefix}-较新",
        schedule_config={"enabled": True, "sync_time": "09:00"},
    )
    disabled = _channel(channel_model, instance_a, f"{prefix}-停用", enabled=False, status="disabled")
    phone = _channel(
        channel_model,
        instance_a,
        f"{prefix}-手机号",
        status="pending_sync",
        platform_match_field="phone",
        external_match_field="mobile",
        schedule_config={"enabled": True, "sync_time": "01:00"},
    )
    failed_only = _channel(
        channel_model,
        instance_a,
        f"{prefix}-只有失败",
        platform_match_field="username",
        external_match_field="username",
        schedule_config={"enabled": True, "sync_time": "not-a-time"},
    )
    empty_success = _channel(
        channel_model,
        instance_a,
        f"{prefix}-空成功",
        external_receive_field="open_id",
        schedule_config={"enabled": True, "sync_time": "09:00:00"},
    )
    other = _channel(channel_model, instance_b, f"{prefix}-另一实例")

    older_mapping = _mapping(mapping_model, older, shared, "shared-loser")
    older_identity_clash = _mapping(mapping_model, older, extra, "winner")
    newer_shared = _mapping(mapping_model, newer, shared, "shared-winner")
    newer_winner = _mapping(mapping_model, newer, winner, "winner")
    failed_mapping = _mapping(mapping_model, failed_only, extra, "failed-stray")
    other_mapping = _mapping(mapping_model, other, other_user, "other-user")

    older_success = _run(run_model, older, "success", _at(2026, 11, 1, 1), _at(2026, 11, 1, 2))
    older_running = _run(run_model, older, "running", _at(2026, 11, 2, 1), running_guard=True)
    newer_partial = _run(run_model, newer, "partial", _at(2026, 11, 5, 1), _at(2026, 11, 5, 2))
    newer_failed = _run(run_model, newer, "failed", _at(2026, 11, 6, 1), _at(2026, 11, 6, 2))
    newer_running = _run(run_model, newer, "running", _at(2026, 11, 7, 1), running_guard=True)
    failed_run = _run(run_model, failed_only, "failed", _at(2026, 11, 3, 1), _at(2026, 11, 3, 2))
    empty_run = _run(run_model, empty_success, "success", _at(2026, 11, 4, 1), _at(2026, 11, 4, 2))
    other_run = _run(run_model, other, "success", _at(2026, 11, 4, 3), _at(2026, 11, 4, 4))

    for channel in (earliest, older, newer, phone):
        _old_schedule(channel.id, 0, 0)

    return {
        "merged_channels": [earliest, older, newer, disabled],
        "phone": phone,
        "failed_only": failed_only,
        "empty_success": empty_success,
        "other": other,
        "kept_mappings": [newer_shared, newer_winner],
        "dropped_mappings": [older_mapping, older_identity_clash, failed_mapping],
        "other_mapping": other_mapping,
        "older_running": older_running,
        "newer_running": newer_running,
        "kept_runs": [older_success, older_running, newer_partial, newer_failed, newer_running],
        "failed_run": failed_run,
        "empty_run": empty_run,
        "other_run": other_run,
    }


def _task(name):
    return PeriodicTask.objects.filter(name=name).first()


@pytest.mark.django_db(transaction=True)
def test_im_account_association_migration_survives_empty_and_mixed_history():
    latest = _leaves()
    prefix = uuid.uuid4().hex[:8]
    if ("system_mgmt", "0056_im_account_association") in _applied():
        _clear_im_rows()
    try:
        MigrationExecutor(connection).migrate(OLD_TARGET)
        MigrationExecutor(connection).migrate(NEW_TARGET)
        _assert_schema()
        assert IMAccountAssociation.objects.count() == 0

        MigrationExecutor(connection).migrate(OLD_TARGET)
        old_apps = MigrationExecutor(connection).loader.project_state(OLD_TARGET).apps
        seeded = _seed(old_apps, prefix)

        MigrationExecutor(connection).migrate(NEW_TARGET)
        _assert_schema()

        earliest = IMAccountAssociation.objects.get(name=f"{prefix}-定时更早")
        assert earliest.status == "pending_sync"
        assert earliest.schedule_config == {"enabled": True, "sync_time": "08:30"}
        assert IMNotificationChannel.objects.get(id=seeded["merged_channels"][0].id).account_association_id == earliest.id
        assert IMNotificationChannel.objects.get(id=seeded["merged_channels"][0].id).status == "needs_resync"

        older = IMAccountAssociation.objects.get(name=f"{prefix}-较早")
        assert older.status == "ready"
        assert older.schedule_config == {"enabled": False}
        assert older.id != earliest.id
        assert set(IMNotificationUserMapping.objects.filter(account_association=older).values_list("id", flat=True)) == {
            seeded["dropped_mappings"][0].id,
            seeded["dropped_mappings"][1].id,
        }
        assert IMNotificationSyncRun.objects.get(id=seeded["older_running"].id).status == "running"
        assert IMNotificationSyncRun.objects.get(id=seeded["older_running"].id).account_association_id == older.id
        assert IMNotificationChannel.objects.get(id=seeded["merged_channels"][1].id).status == "ready"

        newer = IMAccountAssociation.objects.get(name=f"{prefix}-较新")
        assert newer.status == "ready"
        assert newer.schedule_config == {"enabled": True, "sync_time": "09:00"}
        assert set(IMNotificationUserMapping.objects.filter(account_association=newer).values_list("id", flat=True)) == {
            mapping.id for mapping in seeded["kept_mappings"]
        }
        assert set(IMNotificationSyncRun.objects.filter(account_association=newer).values_list("id", flat=True)) == {
            seeded["kept_runs"][2].id,
            seeded["kept_runs"][3].id,
            seeded["kept_runs"][4].id,
        }
        assert IMNotificationSyncRun.objects.get(id=seeded["newer_running"].id).status == "running"
        assert IMNotificationChannel.objects.get(id=seeded["merged_channels"][2].id).status == "ready"
        assert IMNotificationChannel.objects.get(id=seeded["merged_channels"][3].id).status == "disabled"

        disabled = IMAccountAssociation.objects.get(name=f"{prefix}-停用")
        assert disabled.status == "pending_sync"
        assert IMNotificationChannel.objects.get(id=seeded["merged_channels"][3].id).account_association_id == disabled.id

        assert not IMNotificationUserMapping.objects.filter(id=seeded["dropped_mappings"][2].id).exists()

        phone = IMAccountAssociation.objects.get(name=f"{prefix}-手机号")
        assert phone.status == "pending_sync"
        assert phone.schedule_config == {"enabled": True, "sync_time": "01:00"}
        assert IMNotificationChannel.objects.get(id=seeded["phone"].id).status == "needs_resync"

        failed = IMAccountAssociation.objects.get(name=f"{prefix}-只有失败")
        assert failed.status == "pending_sync"
        assert failed.schedule_config == {"enabled": True, "sync_time": "not-a-time"}
        assert IMNotificationSyncRun.objects.get(id=seeded["failed_run"].id).account_association_id == failed.id
        assert IMNotificationChannel.objects.get(id=seeded["failed_only"].id).status == "needs_resync"
        assert _task(f"im_account_association_{failed.id}") is None

        empty = IMAccountAssociation.objects.get(name=f"{prefix}-空成功")
        assert empty.status == "needs_resync"
        assert empty.external_receive_field == "open_id"
        assert not empty.user_mappings.exists()
        assert IMNotificationSyncRun.objects.get(id=seeded["empty_run"].id).account_association_id == empty.id
        assert IMNotificationChannel.objects.get(id=seeded["empty_success"].id).status == "needs_resync"

        other = IMAccountAssociation.objects.get(name=f"{prefix}-另一实例")
        assert other.id not in {earliest.id, older.id, newer.id}
        assert other.status == "ready"
        assert IMNotificationUserMapping.objects.get(id=seeded["other_mapping"].id).account_association_id == other.id
        assert IMNotificationSyncRun.objects.get(id=seeded["other_run"].id).account_association_id == other.id

        assert IMNotificationUserMapping.objects.filter(account_association__isnull=True).count() == 0
        assert IMNotificationSyncRun.objects.filter(account_association__isnull=True).count() == 0
        for channel in seeded["merged_channels"] + [seeded["phone"], seeded["failed_only"], seeded["empty_success"], seeded["other"]]:
            assert _task(f"im_notification_channel_{channel.id}") is None
        assert _task(f"im_account_association_{earliest.id}").crontab.hour == "8"
        assert _task(f"im_account_association_{earliest.id}").crontab.minute == "30"
        assert _task(f"im_account_association_{newer.id}").crontab.hour == "9"
        assert _task(f"im_account_association_{newer.id}").crontab.minute == "0"
        assert _task(f"im_account_association_{older.id}") is None
        assert _task(f"im_account_association_{phone.id}").crontab.hour == "1"
        assert _task(f"im_account_association_{empty.id}").crontab.hour == "9"
        assert _task(f"im_account_association_{empty.id}").crontab.minute == "0"
        assert _task(f"im_account_association_{other.id}") is None
    finally:
        MigrationExecutor(connection).migrate(latest)
