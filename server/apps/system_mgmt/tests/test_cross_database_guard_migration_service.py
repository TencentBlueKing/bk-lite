import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from apps.core.tests.migration_helpers import migrate_to, migrated_from

OLD_TARGET = [("system_mgmt", "0044_remove_builtin_webhook_domains")]
NEW_TARGET = [("system_mgmt", "0045_cross_database_running_guards")]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_existing_sync_run_data_survives_guard_upgrade_and_rollback():
    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        IntegrationInstance = old_apps.get_model("system_mgmt", "IntegrationInstance")
        UserSyncSource = old_apps.get_model("system_mgmt", "UserSyncSource")
        UserSyncRun = old_apps.get_model("system_mgmt", "UserSyncRun")
        IMChannel = old_apps.get_model("system_mgmt", "IMNotificationChannel")
        IMRun = old_apps.get_model("system_mgmt", "IMNotificationSyncRun")

        instance = IntegrationInstance.objects.create(
            name="existing-integration",
            provider_key="migration-provider",
            config={"preserve": "instance"},
            capability_status={"user_sync": "ready", "im_notification": "ready"},
            capability_enabled={"user_sync": True, "im_notification": True},
            team=[71],
        )
        source = UserSyncSource.objects.create(
            name="existing-user-sync",
            integration_instance=instance,
            root_group_name="existing-root",
            field_mapping={"username": "user_id"},
            business_config={"preserve": "source"},
        )
        running_user = UserSyncRun.objects.create(
            source=source,
            status="running",
            request_id="existing-user-running",
            summary="preserve-running-user",
            payload={"preserve": "running-user"},
        )
        finished_user = UserSyncRun.objects.create(
            source=source,
            status="success",
            request_id="existing-user-success",
            summary="preserve-success-user",
            payload={"preserve": "success-user"},
        )
        channel = IMChannel.objects.create(
            name="existing-im-channel",
            integration_instance=instance,
            status="ready",
            team=[71],
        )
        running_im = IMRun.objects.create(
            channel=channel,
            status="running",
            summary="preserve-running-im",
            payload={"preserve": "running-im"},
        )
        finished_im = IMRun.objects.create(
            channel=channel,
            status="failed",
            summary="preserve-failed-im",
            payload={"preserve": "failed-im"},
        )

        new_apps = migrate_to(connection, NEW_TARGET)
        MigratedUserRun = new_apps.get_model("system_mgmt", "UserSyncRun")
        MigratedIMRun = new_apps.get_model("system_mgmt", "IMNotificationSyncRun")

        migrated_running_user = MigratedUserRun.objects.get(pk=running_user.pk)
        migrated_finished_user = MigratedUserRun.objects.get(pk=finished_user.pk)
        assert (
            migrated_running_user.status,
            migrated_running_user.request_id,
            migrated_running_user.summary,
            migrated_running_user.payload,
            migrated_running_user.running_guard,
        ) == (
            "running",
            "existing-user-running",
            "preserve-running-user",
            {"preserve": "running-user"},
            True,
        )
        assert (migrated_finished_user.status, migrated_finished_user.summary, migrated_finished_user.running_guard) == (
            "success",
            "preserve-success-user",
            None,
        )

        migrated_running_im = MigratedIMRun.objects.get(pk=running_im.pk)
        migrated_finished_im = MigratedIMRun.objects.get(pk=finished_im.pk)
        assert (
            migrated_running_im.status,
            migrated_running_im.summary,
            migrated_running_im.payload,
            migrated_running_im.running_guard,
        ) == (
            "running",
            "preserve-running-im",
            {"preserve": "running-im"},
            True,
        )
        assert (migrated_finished_im.status, migrated_finished_im.summary, migrated_finished_im.running_guard) == (
            "failed",
            "preserve-failed-im",
            None,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedUserRun.objects.create(source_id=source.pk, status="running", running_guard=True)
        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedIMRun.objects.create(channel_id=channel.pk, status="running", running_guard=True)

        rolled_back_apps = migrate_to(connection, OLD_TARGET)
        RolledBackUserRun = rolled_back_apps.get_model("system_mgmt", "UserSyncRun")
        RolledBackIMRun = rolled_back_apps.get_model("system_mgmt", "IMNotificationSyncRun")
        assert RolledBackUserRun.objects.get(pk=running_user.pk).summary == "preserve-running-user"
        assert RolledBackIMRun.objects.get(pk=running_im.pk).summary == "preserve-running-im"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("run_kind", ["user", "im"])
def test_mysql_duplicate_running_run_preflight_can_be_fixed_and_retried(run_kind):
    if connection.vendor != "mysql":
        pytest.skip("验证 MySQL 5.7 非事务 DDL 的失败恢复")

    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        IntegrationInstance = old_apps.get_model("system_mgmt", "IntegrationInstance")
        instance = IntegrationInstance.objects.create(
            name="duplicate-running-integration",
            provider_key="migration-provider",
            config={},
            capability_status={"user_sync": "ready", "im_notification": "ready"},
            capability_enabled={"user_sync": True, "im_notification": True},
            team=[71],
        )
        if run_kind == "user":
            UserSyncSource = old_apps.get_model("system_mgmt", "UserSyncSource")
            Run = old_apps.get_model("system_mgmt", "UserSyncRun")
            relation = UserSyncSource.objects.create(
                name="duplicate-running-source",
                integration_instance=instance,
                root_group_name="existing-root",
                field_mapping={},
                business_config={},
            )
            relation_field = "source"
        else:
            IMChannel = old_apps.get_model("system_mgmt", "IMNotificationChannel")
            Run = old_apps.get_model("system_mgmt", "IMNotificationSyncRun")
            relation = IMChannel.objects.create(
                name="duplicate-running-channel",
                integration_instance=instance,
                status="ready",
                team=[71],
            )
            relation_field = "channel"
        run_data = {relation_field: relation, "status": "running", "payload": {}}
        Run.objects.create(**run_data)
        duplicate = Run.objects.create(**run_data)

        try:
            with pytest.raises(RuntimeError, match="存在重复运行记录"):
                MigrationExecutor(connection).migrate(NEW_TARGET)

            with connection.cursor() as cursor:
                user_columns = {
                    column.name
                    for column in connection.introspection.get_table_description(
                        cursor, old_apps.get_model("system_mgmt", "UserSyncRun")._meta.db_table
                    )
                }
                im_columns = {
                    column.name
                    for column in connection.introspection.get_table_description(
                        cursor,
                        old_apps.get_model("system_mgmt", "IMNotificationSyncRun")._meta.db_table,
                    )
                }
            assert "running_guard" not in user_columns
            assert "running_guard" not in im_columns
            assert not MigrationRecorder(connection).migration_qs.filter(app="system_mgmt", name="0045_cross_database_running_guards").exists()
        finally:
            duplicate.status = "failed"
            duplicate.save(update_fields=["status"])

        migrated_apps = migrate_to(connection, NEW_TARGET)
        model_name = "UserSyncRun" if run_kind == "user" else "IMNotificationSyncRun"
        MigratedRun = migrated_apps.get_model("system_mgmt", model_name)
        guards = list(MigratedRun.objects.order_by("id").values_list("status", "running_guard"))
        assert guards == [("running", True), ("failed", None)]
