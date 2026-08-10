import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_system_code_migration_deduplicates_and_adds_unique_constraint():
    old_target = [("cmdb", "0041_nodemgmtsyncconfig_collect_dispatch_claim")]
    new_target = [("cmdb", "0042_collectmodels_system_code_unique")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    try:
        old_apps = executor.loader.project_state(old_target).apps
        tasks = old_apps.get_model("cmdb", "CollectModels")
        winner = tasks.objects.create(
            name="system-code-winner",
            task_type="host",
            driver_type="job",
            model_id="host",
            cycle_value_type="cycle",
            is_system=True,
            is_interval=True,
            system_code="node_mgmt_sync_host_collect_7",
        )
        loser = tasks.objects.create(
            name="system-code-loser",
            task_type="host",
            driver_type="job",
            model_id="host",
            cycle_value_type="cycle",
            is_system=True,
            is_interval=True,
            system_code="node_mgmt_sync_host_collect_7",
        )
        blank = tasks.objects.create(
            name="system-code-blank",
            task_type="host",
            driver_type="job",
            model_id="host",
            cycle_value_type="cycle",
            system_code="",
        )
        second_winner = tasks.objects.create(
            name="system-code-second-winner",
            task_type="host",
            driver_type="job",
            model_id="host",
            cycle_value_type="cycle",
            is_system=True,
            is_interval=True,
            system_code="node_mgmt_sync_host_collect_8",
        )
        second_loser = tasks.objects.create(
            name="system-code-second-loser",
            task_type="host",
            driver_type="job",
            model_id="host",
            cycle_value_type="cycle",
            is_system=True,
            is_interval=True,
            system_code="node_mgmt_sync_host_collect_8",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        migrated_tasks = new_apps.get_model("cmdb", "CollectModels")

        assert migrated_tasks.objects.get(pk=winner.pk).system_code == "node_mgmt_sync_host_collect_7"
        retired = migrated_tasks.objects.get(pk=loser.pk)
        assert retired.system_code is None
        assert retired.is_system is False
        assert retired.is_interval is False
        assert migrated_tasks.objects.get(pk=blank.pk).system_code is None
        assert migrated_tasks.objects.get(pk=second_winner.pk).system_code == "node_mgmt_sync_host_collect_8"
        second_retired = migrated_tasks.objects.get(pk=second_loser.pk)
        assert second_retired.system_code is None
        assert second_retired.is_system is False
        assert second_retired.is_interval is False
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                migrated_tasks.objects.create(
                    name="system-code-conflict",
                    task_type="host",
                    driver_type="job",
                    model_id="host",
                    cycle_value_type="cycle",
                    system_code="node_mgmt_sync_host_collect_7",
                )
    finally:
        MigrationExecutor(connection).migrate(new_target)
