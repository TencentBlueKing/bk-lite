import json
from unittest.mock import patch

import pytest

from apps.itsm.models import TicketStatus
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as sample_fixture
from apps.itsm.views.tickets import ticket_detail

sample = sample_fixture
pytestmark = pytest.mark.django_db


def test_runtime_position_shows_exact_parallel_nodes_until_finished(sample):
    ticket, _ = sample
    ticket.tasks.all().delete()
    ticket.process_instance_id = "parent"
    ticket.save()
    with patch("apps.itsm.views.tickets._service") as service:
        service.return_value.client.active_activity_ids.return_value = {"approval_1", "submit", "unknown"}

        def detail():
            return json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]

        data = detail()
        assert {n["id"] for n in data["nodes"] if n.get("executing")} == {"approval_1", "submit"}
        assert {r["node_id"] for r in data["history"] if r.get("executing")} == {"approval_1", "submit"}
        ticket.status = TicketStatus.objects.get(key="finished")
        ticket.save()
        assert not any(n.get("executing") for n in detail()["nodes"])
        service.return_value.client.active_activity_ids.assert_called_once_with("parent")
