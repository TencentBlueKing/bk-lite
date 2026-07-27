import importlib
from datetime import timedelta
from uuid import UUID

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


OLD_TARGET = [("cmdb", "0038_change_record_mirror_outbox")]
NEW_TARGET = [("cmdb", "0039_node_mgmt_sync_reconciliation")]
LATEST_TARGET = [("cmdb", "0042_collectmodels_system_code_unique")]


@pytest.mark.parametrize("config_count", [0, 1])
@pytest.mark.django_db(transaction=True)
def test_reconciliation_migration_handles_empty_and_singleton_states(config_count):
    executor = MigrationExecutor(connection)
    executor.migrate(OLD_TARGET)
    try:
        old_apps = executor.loader.project_state(OLD_TARGET).apps
        config_model = old_apps.get_model("cmdb", "NodeMgmtSyncConfig")
        run_model = old_apps.get_model("cmdb", "NodeMgmtSyncRun")
        if config_count == 1:
            config = config_model.objects.create(name="singleton")
            run_model.objects.create(task=config, run_type="sync", status="running")

        executor = MigrationExecutor(connection)
        executor.migrate(NEW_TARGET)
        new_apps = executor.loader.project_state(NEW_TARGET).apps
        migrated_configs = new_apps.get_model("cmdb", "NodeMgmtSyncConfig")
        migrated_runs = new_apps.get_model("cmdb", "NodeMgmtSyncRun")

        assert migrated_configs.objects.count() == config_count
        assert migrated_runs.objects.count() == config_count
        if config_count == 1:
            assert migrated_configs.objects.get().singleton_key == "default"
            assert migrated_runs.objects.get().status == "timeout"
    finally:
        MigrationExecutor(connection).migrate(LATEST_TARGET)


@pytest.mark.django_db(transaction=True)
def test_reconciliation_migration_consolidates_duplicate_configs_on_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip("pending trigger events is PostgreSQL-specific")

    executor = MigrationExecutor(connection)
    executor.migrate(OLD_TARGET)
    try:
        old_apps = executor.loader.project_state(OLD_TARGET).apps
        config_model = old_apps.get_model("cmdb", "NodeMgmtSyncConfig")
        run_model = old_apps.get_model("cmdb", "NodeMgmtSyncRun")

        keeper = config_model.objects.create(name="keeper")
        duplicate = config_model.objects.create(name="duplicate")
        now = timezone.now()
        config_model.objects.filter(pk=keeper.pk).update(created_at=now - timedelta(minutes=2))
        config_model.objects.filter(pk=duplicate.pk).update(created_at=now - timedelta(minutes=1))

        successful_run = run_model.objects.create(task=keeper, run_type="sync", status="success")
        running_run = run_model.objects.create(task=duplicate, run_type="collect", status="running")

        executor = MigrationExecutor(connection)
        executor.migrate(NEW_TARGET)
        new_apps = executor.loader.project_state(NEW_TARGET).apps
        migrated_configs = new_apps.get_model("cmdb", "NodeMgmtSyncConfig")
        migrated_runs = new_apps.get_model("cmdb", "NodeMgmtSyncRun")

        assert list(migrated_configs.objects.values_list("id", "singleton_key")) == [(keeper.pk, "default")]

        migrated_successful_run = migrated_runs.objects.get(pk=successful_run.pk)
        assert migrated_successful_run.task_id == keeper.pk
        assert migrated_successful_run.status == "success"
        assert migrated_successful_run.generation is not None

        migrated_running_run = migrated_runs.objects.get(pk=running_run.pk)
        assert migrated_running_run.task_id == keeper.pk
        assert migrated_running_run.status == "timeout"
        assert migrated_running_run.generation is not None
        assert migrated_running_run.deadline_at is not None
        assert migrated_running_run.finished_at is not None

        generations = list(migrated_runs.objects.order_by("id").values_list("generation", flat=True))
        MigrationExecutor(connection).migrate(NEW_TARGET)
        assert list(migrated_runs.objects.order_by("id").values_list("generation", flat=True)) == generations

        with pytest.raises(IntegrityError), transaction.atomic():
            migrated_configs.objects.create(singleton_key="default")
    finally:
        MigrationExecutor(connection).migrate(LATEST_TARGET)


@pytest.mark.django_db(transaction=True)
def test_reconciliation_migration_rolls_back_cleanly_and_can_be_retried(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("pending trigger events is PostgreSQL-specific")

    executor = MigrationExecutor(connection)
    executor.migrate(OLD_TARGET)
    try:
        old_apps = executor.loader.project_state(OLD_TARGET).apps
        config_model = old_apps.get_model("cmdb", "NodeMgmtSyncConfig")
        run_model = old_apps.get_model("cmdb", "NodeMgmtSyncRun")
        keeper = config_model.objects.create(name="keeper")
        duplicate = config_model.objects.create(name="duplicate")
        run_model.objects.create(task=keeper, run_type="sync", status="running")
        run_model.objects.create(task=duplicate, run_type="collect", status="running")

        migration_module = importlib.import_module("apps.cmdb.migrations.0039_node_mgmt_sync_reconciliation")
        with monkeypatch.context() as scoped_patch:
            scoped_patch.setattr(migration_module.uuid, "uuid4", lambda: UUID("00000000-0000-0000-0000-000000000001"))
            with pytest.raises(IntegrityError):
                MigrationExecutor(connection).migrate(NEW_TARGET)

        assert ("cmdb", "0039_node_mgmt_sync_reconciliation") not in MigrationExecutor(
            connection
        ).recorder.applied_migrations()
        assert config_model.objects.count() == 2
        assert run_model.objects.filter(status="running").count() == 2
        with connection.cursor() as cursor:
            columns = {
                field.name
                for field in connection.introspection.get_table_description(cursor, config_model._meta.db_table)
            }
        assert "singleton_key" not in columns

        executor = MigrationExecutor(connection)
        executor.migrate(NEW_TARGET)
        new_apps = executor.loader.project_state(NEW_TARGET).apps
        assert new_apps.get_model("cmdb", "NodeMgmtSyncConfig").objects.count() == 1
        assert new_apps.get_model("cmdb", "NodeMgmtSyncRun").objects.filter(status="timeout").count() == 2
    finally:
        MigrationExecutor(connection).migrate(LATEST_TARGET)
