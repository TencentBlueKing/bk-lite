import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.tests.migration_helpers import migrate_to, migrated_from

OLD_TARGET = [("apm", "0007_builtin_application")]
NEW_TARGET = [("apm", "0008_cross_database_outbox_guard")]


def _create_alert_event(apps, suffix):
    Alert = apps.get_model("apm", "ApmAlert")
    Event = apps.get_model("apm", "ApmEvent")
    now = timezone.now()
    alert = Alert.objects.create(
        external_id=f"alert-{suffix}",
        policy_id_snapshot="policy-existing",
        policy_name="existing-policy",
        service_namespace="existing-namespace",
        service_name="existing-service",
        environment="production",
        metric_type="p95",
        severity="warning",
        status="firing",
        organizations=[71],
        started_at=now,
        last_event_at=now,
    )
    return Event.objects.create(
        event_id=f"event-{suffix}",
        alert=alert,
        action="created",
        title="preserve-title",
        description="preserve-description",
        severity="warning",
        service="existing-service",
        item="p95",
        resource_id="resource-existing",
        resource_name="resource-name-existing",
        policy_id="policy-existing",
        environment="production",
        organizations=[71],
        occurred_at=now,
    )


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_existing_apm_outbox_data_survives_portable_unique_upgrade_and_rollback():
    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        Outbox = old_apps.get_model("apm", "ApmAlertOutbox")
        event = _create_alert_event(old_apps, "existing")
        outbox = Outbox.objects.create(
            event_key="existing-outbox",
            event=event,
            channel_id=7001,
            receivers=["migration-user"],
            recipients=["migration-user"],
            channel_name="existing-channel",
            channel_type="email",
            delivery_mode="message",
            title="preserve-outbox-title",
            body="preserve-outbox-body",
            payload={"preserve": True},
            delivery_status="pending",
            attempts=2,
        )

        new_apps = migrate_to(connection, NEW_TARGET)
        MigratedOutbox = new_apps.get_model("apm", "ApmAlertOutbox")
        migrated = MigratedOutbox.objects.get(pk=outbox.pk)
        assert (
            migrated.event_key,
            migrated.event_id,
            migrated.channel_id,
            migrated.receivers,
            migrated.recipients,
            migrated.title,
            migrated.body,
            migrated.payload,
            migrated.attempts,
        ) == (
            "existing-outbox",
            event.pk,
            7001,
            ["migration-user"],
            ["migration-user"],
            "preserve-outbox-title",
            "preserve-outbox-body",
            {"preserve": True},
            2,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            MigratedOutbox.objects.create(
                event_key="duplicate-event-channel",
                event_id=event.pk,
                channel_id=7001,
                payload={},
            )

        rolled_back_apps = migrate_to(connection, OLD_TARGET)
        RolledBackOutbox = rolled_back_apps.get_model("apm", "ApmAlertOutbox")
        assert RolledBackOutbox.objects.get(pk=outbox.pk).body == "preserve-outbox-body"


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_mysql_duplicate_apm_outbox_preflight_can_be_fixed_and_retried():
    if connection.vendor != "mysql":
        pytest.skip("验证 MySQL 5.7 非事务 DDL 的失败恢复")

    with migrated_from(connection, OLD_TARGET, NEW_TARGET) as old_apps:
        Outbox = old_apps.get_model("apm", "ApmAlertOutbox")
        event = _create_alert_event(old_apps, "duplicate")
        outbox_data = {"event": event, "channel_id": 7101, "payload": {}}
        Outbox.objects.create(event_key="outbox-duplicate-a", **outbox_data)
        duplicate = Outbox.objects.create(event_key="outbox-duplicate-b", **outbox_data)

        try:
            with pytest.raises(RuntimeError, match="重复 event/channel"):
                MigrationExecutor(connection).migrate(NEW_TARGET)

            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, Outbox._meta.db_table)
            assert "apm_outbox_event_channel_portable_unique" not in constraints
        finally:
            duplicate.delete()

        migrated_apps = migrate_to(connection, NEW_TARGET)
        MigratedOutbox = migrated_apps.get_model("apm", "ApmAlertOutbox")
        assert MigratedOutbox.objects.get().event_id == event.pk
