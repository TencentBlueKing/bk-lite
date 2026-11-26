from unittest.mock import Mock, patch

import pytest

from apps.itsm.models.integration import Integration, TodoDelivery
from apps.itsm.services.todo_sync import deliver, sync_todos
from apps.itsm.tests.test_review_regressions import sample as sample_fixture

sample = sample_fixture

pytestmark = pytest.mark.django_db


def test_todo_events_are_scoped_idempotent_and_close(sample):
    ticket, task = sample
    Integration.objects.create(name="目标", kind="todo", config={"url": "https://example.com/hook"})
    Integration.objects.create(name="其他租户", kind="todo", domain="other", config={"url": "https://example.com/other"})
    sync_todos(ticket.id)
    sync_todos(ticket.id)
    row = TodoDelivery.objects.get()
    assert row.payload["event"] == "create"
    assert row.payload["assignees"] == ["handler"]
    task.assignee = "next"
    task.save()
    sync_todos(ticket.id)
    assert TodoDelivery.objects.latest("id").payload["event"] == "update"
    task.status = "done"
    task.save()
    sync_todos(ticket.id)
    assert TodoDelivery.objects.latest("id").payload["event"] == "close"
    assert TodoDelivery.objects.count() == 3


def test_delivery_failure_retry_and_no_duplicate_success(sample):
    ticket, _ = sample
    Integration.objects.create(name="目标", kind="todo", config={"url": "https://example.com/hook"})
    sync_todos(ticket.id)
    row = TodoDelivery.objects.get()
    with patch("apps.itsm.services.todo_sync.safe_request", return_value=Mock(status_code=422)):
        deliver(row.id)
    row.refresh_from_db()
    assert row.status == "failed"
    response = Mock(status_code=204)
    with patch("apps.itsm.services.todo_sync.safe_request", return_value=response) as call:
        deliver(row.id)
        deliver(row.id)
        assert call.call_count == 1
        assert call.call_args.kwargs["allow_redirects"] is False
        assert call.call_args.kwargs["headers"]["Idempotency-Key"] == row.event_key
    row.refresh_from_db()
    assert row.status == "done"
    assert row.attempts == 2


def test_test_tickets_do_not_push(sample):
    ticket, _ = sample
    ticket.is_test = True
    ticket.save()
    Integration.objects.create(name="目标", kind="todo", config={"url": "https://example.com/hook"})
    sync_todos(ticket.id)
    assert not TodoDelivery.objects.exists()
