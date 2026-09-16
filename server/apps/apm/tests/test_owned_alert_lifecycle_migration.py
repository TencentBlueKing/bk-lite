import importlib
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.apps import apps as global_apps
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.utils import Error as DjangoDbError
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core.tests.migration_helpers import migrate_to, migrated_from

backfill_owned_events = importlib.import_module(
    "apps.apm.migrations.0003_apm_owned_alert_lifecycle"
).backfill_owned_events

OLD_TARGET = [("apm", "0002_ingest_source_identity_diagnostic")]
NEW_TARGET = [("apm", "0003_apm_owned_alert_lifecycle")]
RESTORE_TARGET = [("apm", "0018_apmevent_claim_assign_actions")]
QUERY_BUDGET_OUTBOX_COUNT = 100
FIRST_OCCURRED_AT = datetime(2026, 1, 1, 0, 0, tzinfo=dt_timezone.utc)
LATEST_OCCURRED_AT = datetime(2026, 1, 1, 1, 0, tzinfo=dt_timezone.utc)


def _apm_table_names():
    return {
        name
        for name in connection.introspection.table_names()
        if name.startswith("apm_")
    }


def _replay_apm_schema_from_zero():
    """0006 反向会因 ingest_source 约束无法从当前叶退回 0002，只能拆除后重放。"""
    models = list(global_apps.get_app_config("apm").get_models(include_auto_created=True))
    with connection.schema_editor() as editor:
        pending = [model for model in models if model._meta.db_table in _apm_table_names()]
        while pending:
            failed = []
            for model in pending:
                try:
                    editor.delete_model(model)
                except DjangoDbError:
                    failed.append(model)
            if len(failed) == len(pending):
                remaining = sorted(_apm_table_names())
                raise RuntimeError(f"无法拆除 APM 表: {remaining}")
            pending = [model for model in failed if model._meta.db_table in _apm_table_names()]
    MigrationRecorder(connection).migration_qs.filter(app="apm").delete()


def _normalize_sql(sql):
    return sql.replace('"', "").replace("`", "").lower()


def _count_get_or_create_lookups(queries):
    count = 0
    for query in queries:
        sql = _normalize_sql(query["sql"])
        if "limit 21" not in sql:
            continue
        if "apm_apmalert" in sql or "apm_apmevent" in sql:
            count += 1
    return count


def _create_service_and_policy(apps):
    now = timezone.now()
    service = apps.get_model("apm", "ApmService").objects.create(
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    policy = apps.get_model("apm", "ApmPolicy").objects.create(
        name="error-rate",
        environment="prod",
        metric_type="error_rate",
        comparator="gt",
        threshold="0.1",
        duration_window=60,
        recovery_window=60,
        severity="warning",
        service=service,
    )
    return service, policy


def _outbox_payload(*, external_id, action, occurred_at, policy_id, resource_id, value, title):
    return {
        "external_id": external_id,
        "action": action,
        "occurred_at": occurred_at.isoformat(),
        "rule_id": policy_id,
        "resource_id": resource_id,
        "labels": {
            "policy_name": "error-rate",
            "service_namespace": "shop",
            "service_name": "checkout",
            "environment": "prod",
        },
        "organizations": [10],
        "service": "checkout",
        "item": "error_rate",
        "severity": "warning",
        "value": value,
        "title": title,
        "description": title,
        "resource_name": "checkout-pod",
    }


def _create_outbox(apps, *, event_key, payload, created_at, next_retry_at=None):
    outbox = apps.get_model("apm", "ApmAlertOutbox").objects.create(
        event_key=event_key,
        payload=payload,
        delivery_status="pending",
        next_retry_at=next_retry_at,
    )
    apps.get_model("apm", "ApmAlertOutbox").objects.filter(pk=outbox.pk).update(created_at=created_at)
    outbox.refresh_from_db()
    return outbox


@pytest.mark.django_db(transaction=True)
def test_owned_alert_lifecycle_backfill_batches_queries_and_keeps_semantics():
    _replay_apm_schema_from_zero()
    with migrated_from(connection, OLD_TARGET, RESTORE_TARGET) as old_apps:
        service, policy = _create_service_and_policy(old_apps)
        created_at = timezone.now()
        retry_at = created_at + timedelta(minutes=5)

        _create_outbox(
            old_apps,
            event_key="alert-shared:created",
            payload=_outbox_payload(
                external_id="alert-shared",
                action="created",
                occurred_at=FIRST_OCCURRED_AT,
                policy_id=str(policy.id),
                resource_id=str(service.id),
                value="1.25",
                title="firing",
            ),
            created_at=created_at,
            next_retry_at=retry_at,
        )
        _create_outbox(
            old_apps,
            event_key="alert-shared:recovery",
            payload=_outbox_payload(
                external_id="alert-shared",
                action="recovery",
                occurred_at=LATEST_OCCURRED_AT,
                policy_id=str(policy.id),
                resource_id=str(service.id),
                value="0.01",
                title="recovered",
            ),
            created_at=created_at + timedelta(seconds=1),
            next_retry_at=retry_at,
        )
        _create_outbox(
            old_apps,
            event_key="alert-invalid:created",
            payload=_outbox_payload(
                external_id="alert-invalid",
                action="created",
                occurred_at=FIRST_OCCURRED_AT,
                policy_id="not-a-uuid",
                resource_id="also-bad",
                value="2.00",
                title="invalid-uuid",
            ),
            created_at=created_at + timedelta(seconds=2),
            next_retry_at=retry_at,
        )
        _create_outbox(
            old_apps,
            event_key="fallback-ext:created",
            payload={
                "action": "created",
                "occurred_at": FIRST_OCCURRED_AT.isoformat(),
                "rule_id": str(policy.id),
                "resource_id": str(service.id),
                "labels": {"service_name": "checkout"},
                "organizations": [10],
                "title": "fallback",
            },
            created_at=created_at + timedelta(seconds=3),
            next_retry_at=retry_at,
        )
        for index in range(QUERY_BUDGET_OUTBOX_COUNT):
            _create_outbox(
                old_apps,
                event_key=f"budget-{index}:created",
                payload=_outbox_payload(
                    external_id=f"budget-{index}",
                    action="created",
                    occurred_at=FIRST_OCCURRED_AT,
                    policy_id=str(policy.id),
                    resource_id=str(service.id),
                    value="0.50",
                    title=f"budget-{index}",
                ),
                created_at=created_at + timedelta(seconds=10 + index),
                next_retry_at=retry_at,
            )

        with CaptureQueriesContext(connection) as captured:
            new_apps = migrate_to(connection, NEW_TARGET)

        lookup_count = _count_get_or_create_lookups(captured.captured_queries)
        assert lookup_count < 10
        assert lookup_count * 10 < QUERY_BUDGET_OUTBOX_COUNT

        Alert = new_apps.get_model("apm", "ApmAlert")
        Event = new_apps.get_model("apm", "ApmEvent")
        Outbox = new_apps.get_model("apm", "ApmAlertOutbox")

        shared = Alert.objects.get(external_id="alert-shared")
        assert shared.status == "recovered"
        assert shared.policy_id == policy.id
        assert shared.service_id == service.id
        assert shared.last_event_at == LATEST_OCCURRED_AT
        assert shared.ended_at == LATEST_OCCURRED_AT
        assert shared.current_value == Decimal("0.01")
        assert shared.started_at == FIRST_OCCURRED_AT
        assert Event.objects.filter(alert=shared).count() == 2

        invalid = Alert.objects.get(external_id="alert-invalid")
        assert invalid.policy_id is None
        assert invalid.service_id is None
        assert invalid.policy_id_snapshot == "not-a-uuid"

        fallback = Alert.objects.get(external_id="fallback-ext")
        assert fallback.policy_id == policy.id
        assert Event.objects.filter(event_id="fallback-ext:created", alert=fallback).exists()

        assert Outbox.objects.exclude(delivery_status="delivered").count() == 0
        assert Outbox.objects.filter(next_retry_at__isnull=False).count() == 0
        assert Outbox.objects.filter(event_id__isnull=True).count() == 0
        assert Outbox.objects.count() == Event.objects.count() == QUERY_BUDGET_OUTBOX_COUNT + 4

        alert_count = Alert.objects.count()
        event_count = Event.objects.count()
        backfill_owned_events(new_apps, None)
        assert Alert.objects.count() == alert_count
        assert Event.objects.count() == event_count
        assert Outbox.objects.exclude(delivery_status="delivered").count() == 0
