from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore
from apps.apm.models import ApmDeploymentEvent
from apps.apm.services.contracts import InferredDeploymentRelease
from apps.apm.services.deployments import (
    DeploymentEventRecorder,
    ObservedVersion,
    annotate_inferred_deployment_status,
    backfill_inferred_deployment_events,
)
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _observed_at():
    return datetime(2026, 8, 24, 12, tzinfo=UTC)


def _service(name="checkout"):
    create_application("shop", (10,))
    from apps.apm.services import DjangoTelemetryCatalogService
    from apps.apm.services.contracts import CatalogDiscovery

    return DjangoTelemetryCatalogService().discover(
        CatalogDiscovery("shop", name, "pod-a", "production", version="1.0.0", seen_at=_observed_at())
    ).service


def _observe(service, version, seen_at, environment="production"):
    return ObservedVersion(service=service, environment=environment, version=version, last_seen_at=seen_at)


def test_annotate_marks_version_regression_as_rollback():
    observed_at = _observed_at()
    releases = [
        InferredDeploymentRelease("shop", "checkout", "production", "1.0.0", observed_at - timedelta(days=2), observed_at - timedelta(hours=1)),
        InferredDeploymentRelease("shop", "checkout", "production", "0.9.0", observed_at - timedelta(hours=1), observed_at),
    ]
    annotated = annotate_inferred_deployment_status(releases, observed_at=observed_at)
    statuses = {item.version: status for item, status in annotated}
    assert statuses["1.0.0"] == "success"
    assert statuses["0.9.0"] == "rollback"


def test_recorder_creates_success_for_first_version_and_is_idempotent():
    service = _service()
    observed_at = _observed_at()
    recorder = DeploymentEventRecorder()

    first = recorder.record([_observe(service, "1.0.0", observed_at - timedelta(minutes=2))], observed_at=observed_at)
    second = recorder.record([_observe(service, "1.0.0", observed_at)], observed_at=observed_at)

    events = list(ApmDeploymentEvent.objects.filter(service=service).order_by("deployed_at"))
    assert first.created == 1
    assert second.created == 0
    assert len(events) == 1
    assert events[0].version == "1.0.0"
    assert events[0].status == ApmDeploymentEvent.Status.SUCCESS
    assert events[0].source == ApmDeploymentEvent.Source.INFERRED
    assert events[0].deployed_by == ""


def test_recorder_skips_empty_version():
    service = _service()
    observed_at = _observed_at()

    result = DeploymentEventRecorder().record([_observe(service, "  ", observed_at)], observed_at=observed_at)

    assert result.created == 0
    assert ApmDeploymentEvent.objects.count() == 0


def test_recorder_marks_overlapping_newer_version_in_progress_then_converges():
    service = _service()
    observed_at = _observed_at()
    recorder = DeploymentEventRecorder()
    recorder.record([_observe(service, "1.0.0", observed_at - timedelta(minutes=10))], observed_at=observed_at - timedelta(minutes=10))

    rolling = recorder.record(
        [
            _observe(service, "1.0.0", observed_at - timedelta(minutes=1)),
            _observe(service, "1.1.0", observed_at),
        ],
        observed_at=observed_at,
    )
    events = list(ApmDeploymentEvent.objects.filter(service=service).order_by("deployed_at"))
    assert rolling.created == 1
    assert [event.version for event in events] == ["1.0.0", "1.1.0"]
    assert events[1].status == ApmDeploymentEvent.Status.IN_PROGRESS

    settled = recorder.record([_observe(service, "1.1.0", observed_at + timedelta(minutes=5))], observed_at=observed_at + timedelta(minutes=5))
    events[1].refresh_from_db()
    assert settled.updated == 1
    assert events[1].status == ApmDeploymentEvent.Status.SUCCESS
    assert ApmDeploymentEvent.objects.filter(service=service).count() == 2


def test_recorder_marks_rollback_when_previous_version_has_left():
    service = _service()
    observed_at = _observed_at()
    recorder = DeploymentEventRecorder()
    recorder.record([_observe(service, "1.1.0", observed_at - timedelta(hours=1))], observed_at=observed_at - timedelta(hours=1))

    result = recorder.record([_observe(service, "1.0.0", observed_at)], observed_at=observed_at)

    events = list(ApmDeploymentEvent.objects.filter(service=service).order_by("deployed_at"))
    assert result.created == 1
    assert events[-1].version == "1.0.0"
    assert events[-1].status == ApmDeploymentEvent.Status.ROLLBACK


def test_recorder_does_not_mark_rollback_while_newer_version_still_reports():
    service = _service()
    observed_at = _observed_at()
    recorder = DeploymentEventRecorder()
    recorder.record([_observe(service, "1.1.0", observed_at - timedelta(minutes=10))], observed_at=observed_at - timedelta(minutes=10))

    recorder.record(
        [
            _observe(service, "1.1.0", observed_at),
            _observe(service, "1.0.0", observed_at),
        ],
        observed_at=observed_at,
    )

    assert list(ApmDeploymentEvent.objects.filter(service=service).values_list("version", "status")) == [
        ("1.1.0", ApmDeploymentEvent.Status.SUCCESS),
    ]


def test_recorder_converges_silent_in_progress_after_rolling_window():
    service = _service()
    observed_at = _observed_at()
    recorder = DeploymentEventRecorder()
    ApmDeploymentEvent.objects.create(
        service=service,
        environment="production",
        version="1.1.0",
        deployed_at=observed_at - timedelta(minutes=31),
        status=ApmDeploymentEvent.Status.IN_PROGRESS,
        source=ApmDeploymentEvent.Source.INFERRED,
    )

    result = recorder.record([], observed_at=observed_at)

    event = ApmDeploymentEvent.objects.get(service=service)
    assert result.updated == 1
    assert event.status == ApmDeploymentEvent.Status.SUCCESS


def test_recorder_does_not_mutate_reported_events():
    service = _service()
    observed_at = _observed_at()
    reported = ApmDeploymentEvent.objects.create(
        service=service,
        environment="production",
        version="1.0.0",
        deployed_at=observed_at - timedelta(minutes=31),
        deployed_by="alice",
        status=ApmDeploymentEvent.Status.IN_PROGRESS,
        source=ApmDeploymentEvent.Source.REPORTED,
    )

    DeploymentEventRecorder().record([_observe(service, "1.0.0", observed_at)], observed_at=observed_at)

    reported.refresh_from_db()
    assert reported.status == ApmDeploymentEvent.Status.IN_PROGRESS
    assert reported.deployed_by == "alice"


def test_recorder_prunes_inferred_events_older_than_retention():
    service = _service()
    observed_at = _observed_at()
    ApmDeploymentEvent.objects.create(
        service=service,
        environment="production",
        version="0.1.0",
        deployed_at=observed_at - timedelta(days=91),
        status=ApmDeploymentEvent.Status.SUCCESS,
        source=ApmDeploymentEvent.Source.INFERRED,
    )

    result = DeploymentEventRecorder().record([_observe(service, "1.0.0", observed_at)], observed_at=observed_at)

    assert result.pruned == 1
    assert list(ApmDeploymentEvent.objects.filter(service=service).values_list("version", flat=True)) == ["1.0.0"]


def test_backfill_writes_missing_events_and_moves_deployed_at_earlier():
    service = _service()
    observed_at = timezone.now()
    existing = ApmDeploymentEvent.objects.create(
        service=service,
        environment="production",
        version="1.1.0",
        deployed_at=observed_at - timedelta(hours=1),
        status=ApmDeploymentEvent.Status.IN_PROGRESS,
        source=ApmDeploymentEvent.Source.INFERRED,
    )
    store = InMemoryMetricStore(
        deployment_releases=[
            InferredDeploymentRelease(
                "shop",
                "checkout",
                "production",
                "1.0.0",
                observed_at - timedelta(days=2),
                observed_at - timedelta(days=1),
            ),
            InferredDeploymentRelease(
                "shop",
                "checkout",
                "production",
                "1.1.0",
                observed_at - timedelta(days=1),
                observed_at,
            ),
        ]
    )

    result = backfill_inferred_deployment_events(store, observed_at=observed_at)

    existing.refresh_from_db()
    versions = list(ApmDeploymentEvent.objects.filter(service=service).order_by("deployed_at").values_list("version", "status"))
    assert result.created == 1
    assert result.updated == 1
    assert existing.deployed_at == observed_at - timedelta(days=1)
    assert existing.status == ApmDeploymentEvent.Status.IN_PROGRESS
    assert versions[0] == ("1.0.0", ApmDeploymentEvent.Status.SUCCESS)


_BACKFILL_WRITE_BATCH = 500


def _inferred_releases(count: int, observed_at: datetime, *, namespace="shop", name="checkout"):
    base = observed_at - timedelta(days=1)
    return [
        InferredDeploymentRelease(
            namespace,
            name,
            "production",
            f"1.0.{index}",
            base + timedelta(seconds=index),
            observed_at,
        )
        for index in range(count)
    ]


def _backfill_table_query_count(captured: CaptureQueriesContext) -> int:
    return sum(
        1
        for query in captured.captured_queries
        if "apmservice" in query["sql"].lower() or "apmdeploymentevent" in query["sql"].lower()
    )


def _backfill_with_table_queries(releases, observed_at):
    store = InMemoryMetricStore(deployment_releases=releases)
    with CaptureQueriesContext(connection) as captured:
        result = backfill_inferred_deployment_events(store, observed_at=observed_at)
    return result, _backfill_table_query_count(captured)


def test_backfill_empty_releases_writes_nothing():
    service = _service()
    observed_at = timezone.now()

    result, table_queries = _backfill_with_table_queries([], observed_at)

    assert result.created == 0
    assert result.updated == 0
    assert table_queries == 0
    assert ApmDeploymentEvent.objects.filter(service=service).count() == 0


def test_backfill_table_queries_scale_by_batch_not_release_count():
    service = _service()
    observed_at = timezone.now()

    two_result, two_queries = _backfill_with_table_queries(_inferred_releases(2, observed_at), observed_at)
    assert two_result.created == 2
    ApmDeploymentEvent.objects.filter(service=service).delete()

    many_result, many_queries = _backfill_with_table_queries(_inferred_releases(10_000, observed_at), observed_at)

    assert many_result.created == 10_000
    assert ApmDeploymentEvent.objects.filter(service=service).count() == 10_000
    assert many_queries <= two_queries + (10_000 // _BACKFILL_WRITE_BATCH) * 6 + 16


def test_backfill_dedupes_normalized_duplicate_keys_to_earliest_seen():
    service = _service()
    observed_at = timezone.now()
    later = observed_at - timedelta(hours=1)
    earlier = observed_at - timedelta(hours=2)
    store = InMemoryMetricStore(
        deployment_releases=[
            InferredDeploymentRelease("shop", "checkout", "production", "1.0.0", later, later),
            InferredDeploymentRelease(" shop ", "checkout", "production", " 1.0.0 ", earlier, earlier),
        ]
    )

    result = backfill_inferred_deployment_events(store, observed_at=observed_at)
    events = list(ApmDeploymentEvent.objects.filter(service=service))

    assert result.created == 1
    assert len(events) == 1
    assert events[0].version == "1.0.0"
    assert events[0].deployed_at == earlier
    assert events[0].status == ApmDeploymentEvent.Status.SUCCESS


def test_backfill_skips_unknown_identity_and_empty_name_or_version():
    service = _service()
    observed_at = timezone.now()
    store = InMemoryMetricStore(
        deployment_releases=[
            InferredDeploymentRelease("other", "unknown", "production", "1.0.0", observed_at, observed_at),
            InferredDeploymentRelease("shop", "", "production", "1.0.0", observed_at, observed_at),
            InferredDeploymentRelease("shop", "checkout", "production", "", observed_at, observed_at),
        ]
    )

    result = backfill_inferred_deployment_events(store, observed_at=observed_at)

    assert result.created == 0
    assert ApmDeploymentEvent.objects.filter(service=service).count() == 0
