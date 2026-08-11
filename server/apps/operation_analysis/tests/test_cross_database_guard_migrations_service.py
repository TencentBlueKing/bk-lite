from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from apps.core.tests.migration_helpers import migrate_to, migrated_from

OLD_TARGET = [("operation_analysis", "0021_datasource_builtin_fields")]
NEW_TARGET = [("operation_analysis", "0025_execution_guard_constraints")]


def _table_columns(table_name):
    with connection.cursor() as cursor:
        return {column.name for column in connection.introspection.get_table_description(cursor, table_name)}


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_existing_share_and_report_execution_data_survives_guard_upgrade_and_rollback():
    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        ShareLink = old_apps.get_model("operation_analysis", "DashboardShareLink")
        Subscription = old_apps.get_model("operation_analysis", "DashboardReportSubscription")
        Execution = old_apps.get_model("operation_analysis", "DashboardReportExecution")

        active_link = ShareLink.objects.create(
            resource_type="dashboard",
            dashboard_instance_id=7001,
            tenant_domain="migration.example",
            space_id=71,
            sharer_username="migration-user",
            sharer_domain="migration.example",
            status="active",
            invalidation_reason="keep-active",
        )
        inactive_link = ShareLink.objects.create(
            resource_type="dashboard",
            dashboard_instance_id=7002,
            tenant_domain="migration.example",
            space_id=72,
            sharer_username="migration-user",
            sharer_domain="migration.example",
            status="dashboard_invalid",
            invalidation_reason="keep-invalid",
        )
        subscription = Subscription.objects.create(
            creator="migration-user",
            creator_domain="migration.example",
            name="existing-report-subscription",
            status="paused",
            recipient_email="migration@example.com",
            config={"preserve": True},
        )
        manual = Execution.objects.create(
            subscription=subscription,
            creator="migration-user",
            creator_domain="migration.example",
            trigger_type="manual_test",
            request_id="existing-manual-request",
            status="pending",
            error_message="preserve-manual",
        )
        scheduled_at = datetime(2026, 8, 7, 1, 30, tzinfo=UTC)
        scheduled = Execution.objects.create(
            subscription=subscription,
            creator="migration-user",
            creator_domain="migration.example",
            trigger_type="scheduled",
            request_id="existing-scheduled-request",
            scheduled_time_utc=scheduled_at,
            status="failed",
            error_message="preserve-scheduled",
        )

        new_apps = migrate_to(connection, NEW_TARGET)
        MigratedShareLink = new_apps.get_model("operation_analysis", "DashboardShareLink")
        MigratedExecution = new_apps.get_model("operation_analysis", "DashboardReportExecution")

        migrated_active = MigratedShareLink.objects.get(pk=active_link.pk)
        migrated_inactive = MigratedShareLink.objects.get(pk=inactive_link.pk)
        assert (migrated_active.status, migrated_active.invalidation_reason, migrated_active.active_guard) == (
            "active",
            "keep-active",
            True,
        )
        assert (migrated_inactive.status, migrated_inactive.invalidation_reason, migrated_inactive.active_guard) == (
            "dashboard_invalid",
            "keep-invalid",
            None,
        )

        migrated_manual = MigratedExecution.objects.get(pk=manual.pk)
        migrated_scheduled = MigratedExecution.objects.get(pk=scheduled.pk)
        assert (migrated_manual.request_id, migrated_manual.error_message, migrated_manual.request_guard) == (
            "existing-manual-request",
            "preserve-manual",
            True,
        )
        assert (
            migrated_scheduled.request_id,
            migrated_scheduled.scheduled_time_utc,
            migrated_scheduled.error_message,
            migrated_scheduled.request_guard,
            migrated_scheduled.scheduled_guard,
        ) == (
            "existing-scheduled-request",
            scheduled_at,
            "preserve-scheduled",
            True,
            True,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedShareLink.objects.create(
                resource_type="dashboard",
                dashboard_instance_id=7001,
                tenant_domain="other.example",
                space_id=99,
                sharer_username="migration-user",
                sharer_domain="migration.example",
                status="active",
                active_guard=True,
            )
        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedExecution.objects.create(
                subscription_id=subscription.pk,
                creator="other-user",
                trigger_type="manual_test",
                request_id="existing-manual-request",
                request_guard=True,
            )

        rolled_back_apps = migrate_to(connection, OLD_TARGET)
        RolledBackShareLink = rolled_back_apps.get_model("operation_analysis", "DashboardShareLink")
        RolledBackExecution = rolled_back_apps.get_model("operation_analysis", "DashboardReportExecution")
        assert RolledBackShareLink.objects.get(pk=active_link.pk).invalidation_reason == "keep-active"
        assert RolledBackExecution.objects.get(pk=scheduled.pk).error_message == "preserve-scheduled"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_mysql_duplicate_active_share_preflight_can_be_fixed_and_retried():
    if connection.vendor != "mysql":
        pytest.skip("验证 MySQL 5.7 非事务 DDL 的失败恢复")

    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        ShareLink = old_apps.get_model("operation_analysis", "DashboardShareLink")
        identity = {
            "resource_type": "dashboard",
            "dashboard_instance_id": 7101,
            "space_id": 71,
            "sharer_username": "duplicate-user",
            "sharer_domain": "migration.example",
            "status": "active",
        }
        ShareLink.objects.create(**identity)
        duplicate = ShareLink.objects.create(**identity)

        try:
            with pytest.raises(RuntimeError, match="重复的有效画布分享链接"):
                MigrationExecutor(connection).migrate([("operation_analysis", "0023_cross_database_active_share_guard")])

            assert "active_guard" not in _table_columns(ShareLink._meta.db_table)
            assert (
                not MigrationRecorder(connection)
                .migration_qs.filter(app="operation_analysis", name="0023_cross_database_active_share_guard")
                .exists()
            )
        finally:
            duplicate.delete()

        migrated_apps = migrate_to(connection, NEW_TARGET)
        MigratedShareLink = migrated_apps.get_model("operation_analysis", "DashboardShareLink")
        assert MigratedShareLink.objects.get().active_guard is True


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("duplicate_kind", ["request", "schedule"])
def test_mysql_duplicate_report_execution_preflight_can_be_fixed_and_retried(duplicate_kind):
    if connection.vendor != "mysql":
        pytest.skip("验证 MySQL 5.7 非事务 DDL 的失败恢复")

    share_guard_target = [("operation_analysis", "0023_cross_database_active_share_guard")]
    with migrated_from(connection, share_guard_target, NEW_TARGET) as old_apps:
        Subscription = old_apps.get_model("operation_analysis", "DashboardReportSubscription")
        Execution = old_apps.get_model("operation_analysis", "DashboardReportExecution")
        subscription = Subscription.objects.create(
            creator="migration-user",
            name="duplicate-execution-subscription",
            config={},
        )
        execution_data = {
            "subscription": subscription,
            "creator": "migration-user",
            "trigger_type": "manual_test",
            "status": "pending",
        }
        if duplicate_kind == "request":
            execution_data["request_id"] = "duplicate-request"
            Execution.objects.create(**execution_data)
            duplicate = Execution.objects.create(**execution_data)
        else:
            execution_data.update(
                trigger_type="scheduled",
                scheduled_time_utc=datetime(2026, 8, 7, 2, 30, tzinfo=UTC),
            )
            Execution.objects.create(request_id="scheduled-request-a", **execution_data)
            duplicate = Execution.objects.create(request_id="scheduled-request-b", **execution_data)

        try:
            with pytest.raises(RuntimeError, match="重复幂等键或计划时间"):
                MigrationExecutor(connection).migrate(NEW_TARGET)

            columns = _table_columns(Execution._meta.db_table)
            assert "request_guard" not in columns
            assert "scheduled_guard" not in columns
            assert (
                not MigrationRecorder(connection).migration_qs.filter(app="operation_analysis", name="0024_cross_database_execution_guards").exists()
            )
        finally:
            duplicate.delete()

        migrated_apps = migrate_to(connection, NEW_TARGET)
        MigratedExecution = migrated_apps.get_model("operation_analysis", "DashboardReportExecution")
        migrated = MigratedExecution.objects.get()
        assert migrated.request_guard is True
        expected_scheduled_guard = True if duplicate_kind == "schedule" else None
        assert migrated.scheduled_guard is expected_scheduled_guard
