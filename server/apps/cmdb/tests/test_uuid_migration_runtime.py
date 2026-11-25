from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django_celery_beat.models import PeriodicTask

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
    ensure_uuid_migration_periodic_task,
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


def test_ensure_uuid_migration_periodic_task_is_idempotent():
    first = ensure_uuid_migration_periodic_task()
    second = ensure_uuid_migration_periodic_task()

    assert first.pk == second.pk
    assert PeriodicTask.objects.filter(name=UUID_MIGRATION_PERIODIC_TASK_NAME).count() == 1
    task = PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME)
    assert task.task == UUID_MIGRATION_TASK
    assert task.enabled is True


def test_ensure_disables_periodic_task_after_migration_complete():
    ensure_uuid_migration_periodic_task()
    _mark_all_required_stages_complete()
    enabled = PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME)
    enabled.enabled = True
    enabled.save(update_fields=["enabled"])

    ensure_uuid_migration_periodic_task()

    task = PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME)
    assert task.enabled is False
    assert is_uuid_runtime_migration_complete() is True


def test_ensure_does_not_create_periodic_task_when_migration_complete():
    _mark_all_required_stages_complete()

    created = ensure_uuid_migration_periodic_task()

    assert created is None
    assert PeriodicTask.objects.filter(name=UUID_MIGRATION_PERIODIC_TASK_NAME).count() == 0


def test_runtime_task_skips_commands_when_already_complete(mocker, caplog):
    import logging

    ensure_uuid_migration_periodic_task()
    _mark_all_required_stages_complete()
    task = PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME)
    task.enabled = True
    task.save(update_fields=["enabled"])
    call_apply = mocker.patch("apps.cmdb.tasks.uuid_migration.call_command")

    with caplog.at_level(logging.INFO, logger="cmdb"):
        result = migrate_cmdb_instance_uuid_runtime()

    assert result == {"status": "done", "skipped": True}
    call_apply.assert_not_called()
    assert PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME).enabled is False
    messages = [record.getMessage() for record in caplog.records]
    assert "event=uuid_migration_skipped reason=already_complete" in messages


def test_runtime_task_keeps_retrying_until_verify_marks_runtime_done(mocker):
    _mark_all_required_stages_complete()
    CmdbUuidMigrationState.objects.filter(stage=RUNTIME_DONE_STAGE).delete()
    calls = []

    def _fake_call_command(name, **kwargs):
        calls.append((name, kwargs))

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)

    result = migrate_cmdb_instance_uuid_runtime()

    assert result == {"status": "done", "skipped": False}
    assert ("migrate_cmdb_instance_uuid_refs", {"verify": True}) in calls
    assert CmdbUuidMigrationState.objects.filter(stage=RUNTIME_DONE_STAGE, completed=True).exists()
    assert PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME).enabled is False


def test_new_stage_reopens_task_and_verify_failure_ignores_stale_runtime_done(mocker):
    ensure_uuid_migration_periodic_task()
    _mark_all_required_stages_complete()
    task = PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME)
    task.enabled = False
    task.save(update_fields=["enabled"])
    CmdbUuidMigrationState.objects.filter(stage="graph_instances").delete()

    def _fake_call_command(name, **kwargs):
        if name == "migrate_cmdb_instance_uuid_refs" and kwargs.get("apply"):
            CmdbUuidMigrationState.objects.update_or_create(
                stage="graph_instances",
                defaults={"cursor": "0", "completed": True},
            )
        if kwargs.get("verify"):
            raise RuntimeError("still dirty")

    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)

    reopened = ensure_uuid_migration_periodic_task()

    assert reopened.enabled is True
    assert not CmdbUuidMigrationState.objects.filter(stage=RUNTIME_DONE_STAGE).exists()

    result = migrate_cmdb_instance_uuid_runtime()

    assert result == {"status": "retry", "reason": "verify_failed"}
    assert PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME).enabled is True
    assert not CmdbUuidMigrationState.objects.filter(stage=RUNTIME_DONE_STAGE).exists()

    second = migrate_cmdb_instance_uuid_runtime()

    assert second == {"status": "retry", "reason": "verify_failed"}


def test_runtime_task_returns_locked_when_another_worker_holds_lock(mocker):
    mocker.patch("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task")
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
    assert PeriodicTask.objects.get(name=UUID_MIGRATION_PERIODIC_TASK_NAME).enabled is False
    assert cache.get(UUID_MIGRATION_LOCK_KEY) is None


def test_runtime_task_swallows_apply_failure_and_returns_retry(mocker):
    mocker.patch("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task")
    mocker.patch(
        "apps.cmdb.tasks.uuid_migration.call_command",
        side_effect=RuntimeError("graph unavailable"),
    )
    disable = mocker.patch("apps.cmdb.tasks.uuid_migration._disable_uuid_migration_periodic_task")
    mark = mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")

    result = migrate_cmdb_instance_uuid_runtime()

    assert result["status"] == "retry"
    assert result["reason"] == "apply_failed"
    mark.assert_not_called()
    disable.assert_not_called()
    assert cache.get(UUID_MIGRATION_LOCK_KEY) is None


def test_runtime_task_verify_failure_returns_retry_without_marking_done(mocker):
    def _fake_call_command(name, **kwargs):
        if kwargs.get("verify"):
            raise RuntimeError("still dirty")

    mocker.patch("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task")
    mocker.patch("apps.cmdb.tasks.uuid_migration.call_command", side_effect=_fake_call_command)
    mark = mocker.patch("apps.cmdb.tasks.uuid_migration.mark_uuid_runtime_migration_complete")
    disable = mocker.patch("apps.cmdb.tasks.uuid_migration._disable_uuid_migration_periodic_task")

    result = migrate_cmdb_instance_uuid_runtime()

    assert result["status"] == "retry"
    assert result["reason"] == "verify_failed"
    mark.assert_not_called()
    disable.assert_not_called()


def test_batch_init_cmdb_registers_runtime_task_without_sync_apply(mocker):
    from apps.core.management.commands.batch_init import Command

    ensure = mocker.patch(
        "apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task",
        return_value=SimpleNamespace(pk=1),
    )
    delay = mocker.patch("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.disable_display_field_backfill_periodic_task")
    mocker.patch("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay")
    mocker.patch("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", return_value=SimpleNamespace(pk=1, enabled=True))
    mocker.patch("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay")
    call_cmd = mocker.patch(
        "apps.core.management.commands.batch_init.call_command",
        return_value=None,
    )

    Command()._init_cmdb()

    ensure.assert_called_once_with()
    delay.assert_called_once_with()
    for args, kwargs in call_cmd.call_args_list:
        assert "migrate_cmdb_instance_uuid_refs" not in args
        assert "migrate_oa_cmdb_instance_uuid_refs" not in args
        assert kwargs.get("apply") is not True


def test_batch_init_skips_uuid_delay_when_migration_complete(mocker):
    from apps.core.management.commands.batch_init import Command

    mocker.patch(
        "apps.cmdb.services.uuid_migration_runtime.is_uuid_migration_periodic_retired",
        return_value=True,
    )
    ensure = mocker.patch("apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task")
    delay = mocker.patch("apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.disable_display_field_backfill_periodic_task")
    mocker.patch("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay")
    mocker.patch("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", return_value=SimpleNamespace(pk=1, enabled=True))
    mocker.patch("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay")
    mocker.patch("apps.core.management.commands.batch_init.call_command", return_value=None)

    Command()._init_cmdb()

    ensure.assert_called_once_with()
    delay.assert_not_called()


def test_batch_init_cmdb_continues_when_delay_fails(mocker):
    from apps.core.management.commands.batch_init import Command

    mocker.patch(
        "apps.cmdb.tasks.uuid_migration.ensure_uuid_migration_periodic_task",
        return_value=SimpleNamespace(pk=1),
    )
    mocker.patch(
        "apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime.delay",
        side_effect=RuntimeError("broker down"),
    )
    mocker.patch("apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields.delay")
    mocker.patch("apps.cmdb.tasks.display_field_backfill.disable_display_field_backfill_periodic_task")
    mocker.patch("apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape.delay")
    mocker.patch(
        "apps.core.management.commands.batch_init.call_command",
        return_value=None,
    )
    mocker.patch("apps.cmdb.tasks.ci_context.ensure_ci_context_rebuild_periodic_task", return_value=SimpleNamespace(pk=1, enabled=True))
    mocker.patch("apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime.delay")

    # 不得因投递失败而抛出并阻断启动
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
