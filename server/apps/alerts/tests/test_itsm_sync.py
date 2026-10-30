from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.alerts.itsm.sync import sync_ticket
from apps.alerts.models.itsm import AlertItsmTicket
from apps.alerts.tests.test_itsm_client import response
from apps.alerts.tests.test_itsm_service import alert, configure_itsm, itsm_connection, prepare, rule  # noqa: F401


def linked(close=True, status="unassigned"):
    a = alert(status=status)
    r = rule()
    link = prepare(a)
    link.connection = "dev"
    link.instance_id = "test-itsm"
    link.ticket_id = "123"
    link.close_alert_on_ticket_closed = close
    link.save()
    return a, r, link


def closed_response():
    return response(
        {
            "code": "20000",
            "data": {
                "ticket": {
                    "id": "123",
                    "status": "finished",
                    "status_display": "已完成",
                    "title": "CPU",
                    "sn": "DE123",
                    "end_at": "2026-10-27T10:00:00+08:00",
                }
            },
        }
    )


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["unassigned", "pending", "processing", "auto_recovery", "resolved", "auto_close"])
def test_ended_ticket_is_displayed_closed_and_alert_status_stays(setup_itsm, status):
    a, _, link = linked(status=status)
    with patch("requests.Session.request", return_value=closed_response()):
        sync_ticket(link.pk)
    a.refresh_from_db()
    link.refresh_from_db()
    assert a.status == status
    assert link.status_label == "工单已关闭"
    assert link.is_closed is True
    assert link.close_result == "unprocessed"


@pytest.mark.django_db
def test_closed_ticket_never_closes_reopened_alert_twice(setup_itsm):
    a, _, link = linked()
    with patch("requests.Session.request", return_value=closed_response()):
        sync_ticket(link.pk)
        a.refresh_from_db()
        a.status = "unassigned"
        a.save()
        AlertItsmTicket.objects.filter(pk=link.pk).update(next_sync_at=timezone.now())
        sync_ticket(link.pk)
    a.refresh_from_db()
    assert a.status == "unassigned"


@pytest.mark.django_db
def test_sync_failure_preserves_last_status(setup_itsm):
    a, _, link = linked(close=False)
    link.ticket_status = "running"
    link.save()
    with patch("requests.Session.request", return_value=response({}, 404)):
        sync_ticket(link.pk)
    link.refresh_from_db()
    a.refresh_from_db()
    assert link.ticket_status == "running" and not link.is_closed
    assert link.sync_error
    assert a.status == "unassigned"


@pytest.mark.django_db
def test_ended_ticket_does_not_close_the_alert(setup_itsm):
    a, _, link = linked()
    with patch("requests.Session.request", return_value=closed_response()):
        sync_ticket(link.pk)
    a.refresh_from_db()
    link.refresh_from_db()
    assert a.status == "unassigned"
    assert link.close_attempts == 0
    assert link.close_result == "unprocessed"
