from datetime import timedelta
import logging
from io import StringIO
from unittest import mock

import pytest
from django.utils import timezone

from apps.alerts.models import AlertOutbox
from apps.alerts.tasks.tasks import dispatch_pending_alert_outbox


pytestmark = pytest.mark.django_db


def _outbox(*, kind, status, created_at=None, updated_at=None):
    record = AlertOutbox.objects.create(kind=kind, payload={}, idempotency_key=f"{kind}-{status}-{AlertOutbox.objects.count()}", status=status,)
    timestamps = {}
    if created_at is not None:
        timestamps["created_at"] = created_at
    if updated_at is not None:
        timestamps["updated_at"] = updated_at
    if timestamps:
        AlertOutbox.objects.filter(pk=record.pk).update(**timestamps)
    return record


def test_dispatcher_emits_one_incident_im_backlog_snapshot_with_accurate_counts(monkeypatch,):
    now = timezone.now()
    _outbox(
        kind="incident_im_group.create",
        status=AlertOutbox.Status.PENDING,
        created_at=now - timedelta(seconds=90),
        updated_at=now,
    )
    _outbox(
        kind="incident_im_group.add_members", status=AlertOutbox.Status.DELIVERING,
    )
    _outbox(
        kind="incident_im_group.send_summary", status=AlertOutbox.Status.FAILED,
    )
    _outbox(
        kind="incident_im_group.create",
        status=AlertOutbox.Status.DELIVERED,
        created_at=now - timedelta(seconds=900),
        updated_at=now - timedelta(seconds=900),
    )
    _outbox(kind="notification", status=AlertOutbox.Status.PENDING)
    events = []
    monkeypatch.setattr(
        "apps.alerts.service.incident_im.observability.logger.info", lambda message, *args, **kwargs: events.append((message, kwargs.get("extra"))),
    )
    monkeypatch.setattr(
        "apps.alerts.tasks.tasks.deliver_alert_outbox.delay", lambda record_id: None,
    )
    monkeypatch.setattr(
        "apps.alerts.tasks.tasks.deliver_incident_im_add_members_outbox.delay", lambda record_id: None,
    )

    dispatch_pending_alert_outbox()

    snapshots = [extra for _, extra in events if extra and extra.get("event") == "incident_im_outbox_backlog"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["pending_count"] == 1
    assert snapshot["delivering_count"] == 1
    assert snapshot["failed_count"] == 1
    assert snapshot["oldest_pending_age_seconds"] >= 90


def test_dispatcher_logging_failure_does_not_block_scheduling(monkeypatch):
    record = _outbox(kind="incident_im_group.create", status=AlertOutbox.Status.PENDING,)
    scheduled = []
    monkeypatch.setattr(
        "apps.alerts.service.incident_im.observability.logger.info", mock.Mock(side_effect=RuntimeError("logger unavailable")),
    )
    monkeypatch.setattr(
        "apps.alerts.tasks.tasks.deliver_alert_outbox.delay", lambda record_id: scheduled.append(record_id),
    )

    result = dispatch_pending_alert_outbox()

    assert result["scheduled"] == 1
    assert scheduled == [record.pk]


def test_safe_incident_im_event_never_exposes_payload_and_never_raises(monkeypatch):
    from apps.alerts.service.incident_im.observability import emit_incident_im_event

    logged = []
    monkeypatch.setattr(
        "apps.alerts.service.incident_im.observability.logger.info", lambda message, *args, **kwargs: logged.append(kwargs["extra"]),
    )
    emit_incident_im_event(
        "incident_im_member_batch",
        group_id="group-1",
        incident_id=42,
        result="partial",
        joined_count=3,
        failed_count=1,
        invalid_count=1,
        forbidden_payload={"external_id": "ou_secret"},
    )

    assert logged == [
        {
            "event": "incident_im_member_batch",
            "group_id": "group-1",
            "incident_id": 42,
            "result": "partial",
            "joined_count": 3,
            "failed_count": 1,
            "invalid_count": 1,
        }
    ]
    monkeypatch.setattr(
        "apps.alerts.service.incident_im.observability.logger.info", mock.Mock(side_effect=RuntimeError("logger unavailable")),
    )
    emit_incident_im_event("incident_im_member_batch", group_id="group-1")


def test_incident_im_event_is_visible_with_message_only_formatter(monkeypatch):
    from apps.alerts.service.incident_im.observability import emit_incident_im_event

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    message_only_logger = logging.Logger("incident-im-observability-test")
    message_only_logger.addHandler(handler)
    monkeypatch.setattr(
        "apps.alerts.service.incident_im.observability.logger",
        message_only_logger,
    )

    emit_incident_im_event(
        "incident_im_member_batch",
        group_id="group-1",
        joined_count=3,
        failed_count=1,
        forbidden_payload={"external_id": "ou_secret"},
    )

    rendered = stream.getvalue()
    assert "event=incident_im_member_batch" in rendered
    assert "joined_count=3" in rendered
    assert "failed_count=1" in rendered
    assert "forbidden_payload" not in rendered
    assert "ou_secret" not in rendered
