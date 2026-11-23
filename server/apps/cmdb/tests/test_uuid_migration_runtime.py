from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.cmdb.models.uuid_migration_state import CmdbUuidMigrationState
from apps.cmdb.services.uuid_migration_runtime import (
    REQUIRED_CMDB_UUID_STAGES,
    REQUIRED_OA_UUID_MODEL_NAMES,
    RUNTIME_DONE_STAGE,
    is_uuid_runtime_migration_complete,
    mark_uuid_runtime_migration_complete,
)
from apps.cmdb.tasks.uuid_migration import (
    UUID_MIGRATION_LOCK_KEY,
    UUID_MIGRATION_PERIODIC_TASK_NAME,
    UUID_MIGRATION_TASK,
    disable_uuid_migration_periodic_task,
    migrate_cmdb_instance_uuid_runtime,
)

pytestmark = pytest.mark.django_db


def _mark_all_required_stages_complete():
    for stage in REQUIRED_CMDB_UUID_STAGES:
        CmdbUuidMigrationState.objects.update_or_create(
            stage=stage,
            defaults={"cursor": "0", "completed": True},
        )
    from django.apps import apps as django_apps

    for model_name in REQUIRED_OA_UUID_MODEL_NAMES:
        try:
            django_apps.get_model("operation_analysis", model_name)
        except LookupError:
            continue
        CmdbUuidMigrationState.objects.update_or_create(
            stage=f"oa_uuid:{model_name}",
            defaults={"cursor": "0", "completed": True},
        )
    mark_uuid_runtime_migration_complete()


def _create_legacy_periodic_task(*, enabled=True):
    schedule = CrontabSchedule.objects.create(minute="*/5", hour="*", day_of_week="*", day_of_month="*", month_of_year="*")
    return PeriodicTask.objects.create(
        name=UUID_MIGRATION_PERIODIC_TASK_NAME,
        task=UUID_MIGRATION_TASK,
        crontab=schedule,
        enabled=enabled,
    )


def test_disable_uuid_migration_periodic_task_deletes_legacy_beat_entry():
    _create_legacy_periodic_task()

    disable_uuid_migration_periodic_task()
    disable_uuid_migration_periodic_task()

    assert PeriodicTask.objects.filter(name=UUID_MIGRATION_PERIODIC_TASK_NAME).count() == 0


def test_disable_is_a_no_op_when_periodic_task_is_absent():
    disable_uuid_migration_periodic_task()
    assert PeriodicTask.objects.filter(name=UUID_MIGRATION_PERIODIC_TASK_NAME).count() == 0


def test_runtime_task_does_not_recreate_periodic_task(mocker):
    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command")
    mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")

    migrate_cmdb_instance_uuid_runtime()

    assert PeriodicTask.objects.filter(name=UUID_MIGRATION_PERIODIC_TASK_NAME).count() == 0


def test_runtime_task_still_applies_when_already_complete(mocker):
    _mark_all_required_stages_complete()
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)
    mark = mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")

    result = migrate_cmdb_instance_uuid_runtime()

    assert result["status"] == "done"
    assert result["skipped"] is False
    assert ("migrate_cmdb_instance_uuid_refs", {"apply": True}) in calls
    assert ("migrate_cmdb_instance_uuid_refs", {"verify": True}) in calls
    mark.assert_called_once_with()


def test_runtime_task_returns_locked_when_another_worker_holds_lock(mocker):
    mocker.patch("apps.cmdb.tasks.uuid_migration.cache.add", return_value=False)
    call_apply = mocker.patch("apps.cmdb.tasks.uuid_migration.call_command")

    result = migrate_cmdb_instance_uuid_runtime()

    assert result["status"] == "locked"
    call_apply.assert_not_called()


def test_runtime_task_applies_and_marks_complete(mocker):
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)
    mark = mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")

    result = migrate_cmdb_instance_uuid_runtime()

    assert result == {"status": "done", "skipped": False}
    assert ("migrate_cmdb_instance_uuid_refs", {"apply": True}) in calls
    assert ("migrate_oa_cmdb_instance_uuid_refs", {"apply": True}) in calls
    assert ("migrate_cmdb_instance_uuid_refs", {"verify": True}) in calls
    assert ("migrate_oa_cmdb_instance_uuid_refs", {"verify": True}) in calls
    mark.assert_called_once_with()
    assert cache.get(UUID_MIGRATION_LOCK_KEY) is None


def test_runtime_task_swallows_apply_failure_and_returns_retry(mocker):
    mocker.patch(
        "apps.cmdb.tasks.uuid_migration.call_command",
        side_effect=RuntimeError("graph unavailable"),
    )

    result = migrate_cmdb_instance_uuid_runtime()

    assert result["status"] == "retry"
    assert result["reason"] == "apply_failed"
    assert cache.get(UUID_MIGRATION_LOCK_KEY) is None


def test_runtime_task_verify_failure_returns_retry_without_marking_done(mocker):
    def _fake_call_command(name, **kwargs):
        if kwargs.get("verify"):
            raise RuntimeError("still dirty")

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)
    mark = mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")

    result = migrate_cmdb_instance_uuid_runtime()

    assert result["status"] == "retry"
    assert result["reason"] == "verify_failed"
    mark.assert_not_called()


def test_management_command_runs_apply_then_verify(mocker):
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)

    call_command("migrate_cmdb_instance_uuid_runtime")

    assert ("migrate_cmdb_instance_uuid_refs", {"apply": True}) in calls
    assert ("migrate_oa_cmdb_instance_uuid_refs", {"apply": True}) in calls
    assert ("migrate_cmdb_instance_uuid_refs", {"verify": True}) in calls
    assert ("migrate_oa_cmdb_instance_uuid_refs", {"verify": True}) in calls


def test_management_command_apply_only_skips_verify(mocker):
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)
    mark = mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")

    call_command("migrate_cmdb_instance_uuid_runtime", apply=True)

    assert calls == [
        ("migrate_cmdb_instance_uuid_refs", {"apply": True}),
        ("migrate_oa_cmdb_instance_uuid_refs", {"apply": True}),
    ]
    mark.assert_not_called()


def test_management_command_verify_only(mocker):
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)

    call_command("migrate_cmdb_instance_uuid_runtime", verify=True)

    assert calls == [
        ("migrate_cmdb_instance_uuid_refs", {"verify": True}),
        ("migrate_oa_cmdb_instance_uuid_refs", {"verify": True}),
    ]


def test_management_command_dry_run(mocker):
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)

    call_command("migrate_cmdb_instance_uuid_runtime", dry_run=True)

    assert calls == [
        ("migrate_cmdb_instance_uuid_refs", {"dry_run": True}),
        ("migrate_oa_cmdb_instance_uuid_refs", {"dry_run": True}),
    ]


def test_batch_init_cmdb_disables_periodic_task_without_enqueue(mocker):
    from apps.core.management.commands.batch_init import Command

    disable = mocker.patch("apps.cmdb.tasks.uuid_migration.disable_uuid_migration_periodic_task")
    delay = mocker.patch("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task")
    mocker.patch("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay")
    mocker.patch("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", return_value=SimpleNamespace(pk=1, enabled=True))
    mocker.patch("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay")
    call_cmd = mocker.patch(
        "apps.core.management.commands.batch_init.call_command",
        return_value=None,
    )

    Command()._init_cmdb()

    disable.assert_called_once_with()
    delay.assert_not_called()
    for args, kwargs in call_cmd.call_args_list:
        assert "migrate_cmdb_instance_uuid_refs" not in args
        assert "migrate_oa_cmdb_instance_uuid_refs" not in args
        assert "migrate_cmdb_instance_uuid_runtime" not in args
        assert kwargs.get("apply") is not True


def test_batch_init_cmdb_continues_when_disable_fails(mocker):
    from apps.core.management.commands.batch_init import Command

    mocker.patch(
        "apps.cmdb.tasks.uuid_migration.disable_uuid_migration_periodic_task",
        side_effect=RuntimeError("beat table missing"),
    )
    mocker.patch("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.ensure_display_field_backfill_periodic_task")
    mocker.patch("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay")
    mocker.patch(
        "apps.core.management.commands.batch_init.call_command",
        return_value=None,
    )
    mocker.patch("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", return_value=SimpleNamespace(pk=1, enabled=True))
    mocker.patch("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay")

    Command()._init_cmdb()


def test_mark_and_detect_runtime_done_stage():
    assert is_uuid_runtime_migration_complete() is False
    mark_uuid_runtime_migration_complete()
    assert CmdbUuidMigrationState.objects.filter(stage=RUNTIME_DONE_STAGE, completed=True).exists()
    # 汇总标记不能单独跳过后续新增的必需 stage
    assert is_uuid_runtime_migration_complete() is False
    _mark_all_required_stages_complete()
    assert is_uuid_runtime_migration_complete() is True


def test_new_pg_leftover_stages_are_required():
    assert "subscription_snapshots" in REQUIRED_CMDB_UUID_STAGES
    assert "custom_reporting_pending" in REQUIRED_CMDB_UUID_STAGES
    assert "custom_reporting_cleanup" in REQUIRED_CMDB_UUID_STAGES
    assert "collect_instances" in REQUIRED_CMDB_UUID_STAGES
    assert "collect_result_snapshots" in REQUIRED_CMDB_UUID_STAGES
    assert "operation_snapshots" in REQUIRED_CMDB_UUID_STAGES
    assert "operation_outbox" in REQUIRED_CMDB_UUID_STAGES
    assert "monitor_cmdb_ids" in REQUIRED_CMDB_UUID_STAGES
    assert "node_cmdb_ids" in REQUIRED_CMDB_UUID_STAGES
    assert "NetworkTopology" not in REQUIRED_OA_UUID_MODEL_NAMES
