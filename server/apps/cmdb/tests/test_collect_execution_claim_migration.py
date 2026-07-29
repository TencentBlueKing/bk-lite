import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_execution_claim_token_migration_is_nullable_and_preserves_existing_tasks():
    old_target = [("cmdb", "0039_node_mgmt_sync_reconciliation")]
    new_target = [("cmdb", "0040_collectmodels_execution_claim_token")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    try:
        old_apps = executor.loader.project_state(old_target).apps
        old_task = old_apps.get_model("cmdb", "CollectModels").objects.create(
            name="claim-migration-task",
            task_type="protocol",
            driver_type="protocol",
            model_id="mysql",
            cycle_value_type="cycle",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        migrated = new_apps.get_model("cmdb", "CollectModels").objects.get(id=old_task.id)

        assert migrated.execution_claim_token is None
    finally:
        MigrationExecutor(connection).migrate(new_target)
