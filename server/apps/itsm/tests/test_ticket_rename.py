import json

import pytest
from django.urls import resolve

from apps.itsm.models import TicketStatus
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as sample_fixture
from apps.itsm.views.tickets import ticket_detail

sample = sample_fixture
pytestmark = pytest.mark.django_db


def test_ticket_title_rename_is_scoped_and_audited(sample):
    ticket, _ = sample
    rename = resolve(f"/api/v1/itsm/api/tickets/{ticket.pk}/title/").func
    payload = {"title": " 新工单标题 "}
    assert rename(request("put", payload), ticket.pk).status_code == 404
    assert rename(request("put", payload, "owner", ["ticket-View"]), ticket.pk).status_code == 403
    for value in [" ", "字" * 201]:
        assert rename(request("put", {"title": value}, "owner"), ticket.pk).status_code == 400
    for user in ["owner", "handler"]:
        assert json.loads(ticket_detail(request(username=user), ticket.pk).content)["data"]["can_rename"]
        assert rename(request("put", payload, user), ticket.pk).status_code == 200
    ticket.refresh_from_db()
    assert ticket.title == "新工单标题"
    assert ticket.logs.filter(action="rename").count() == 1
    ticket.status = TicketStatus.objects.get(key="finished")
    ticket.save(update_fields=["status"])
    assert rename(request("put", payload, "owner"), ticket.pk).status_code == 403
