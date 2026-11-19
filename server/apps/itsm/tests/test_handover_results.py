import json
from unittest.mock import Mock, call, patch

import pytest
from django.urls import resolve

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import TicketStatus, TicketTask
from apps.itsm.models.extend import Handover
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as sample_ticket
from apps.itsm.views.extend import resource_item, resources
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


def _post_handover(tasks):
    body = {"from_user": "handler", "to_user": "replacement", "ticket_ids": [task.ticket_id for task in tasks]}
    return resources(request("post", body, "admin", ["handover-Add"]), "handovers")


def _retry(handover_id, permissions=("handover-Add",), domain="domain.com", username="admin"):
    path = f"/api/handovers/{handover_id}/retry/"
    url = resolve(path, urlconf="apps.itsm.urls")
    return url.func(request("post", username=username, permissions=permissions, domain=domain), **url.kwargs)


def _statuses(response):
    assert response.status_code == 200, json.loads(response.content)
    data = json.loads(response.content)["data"]
    return data["id"], {item["task_id"]: item["status"] for item in data["results"]}


@pytest.fixture
def task_pair():
    first_ticket, first_task = sample_ticket.__wrapped__()
    first_task.flowable_task_id = "first"
    first_task.save(update_fields=["flowable_task_id"])
    second_ticket = TicketService().create(first_ticket.workflow_version, {"title": "第二张工单", "amount": 20}, "owner")
    second_task = TicketTask.objects.create(ticket=second_ticket, node_id=first_task.node_id, assignee="handler", flowable_task_id="second")
    User.objects.create(domain=first_ticket.domain, username="replacement", display_name="接替处理人")
    return first_task, second_task


@pytest.mark.parametrize("engine_status", [0, 408, 503])
def test_handover_reports_first_success_when_next_engine_response_times_out(task_pair, engine_status):
    first, second = task_pair
    ids = [first.ticket_id, second.ticket_id]
    engine = Mock()
    engine.update_task_assignee.side_effect = [{}, FlowableError(engine_status, "response not confirmed")]
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        response = _post_handover(task_pair)

    first.refresh_from_db()
    second.refresh_from_db()
    handover = Handover.objects.get()
    assert first.assignee == "replacement"
    assert second.assignee == "handler"
    assert handover.ticket_ids == ids
    assert engine.update_task_assignee.call_args_list == [call("first", "replacement"), call("second", "replacement")]
    assert _statuses(response) == (handover.id, {first.id: "succeeded", second.id: "unconfirmed"})
    assert handover.results == json.loads(response.content)["data"]["results"]
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        assert _statuses(_retry(handover.id)) == (handover.id, {first.id: "succeeded", second.id: "unconfirmed"})
    assert engine.update_task_assignee.call_count == 2


def test_handover_retries_failed_task_without_replaying_success(task_pair):
    first, second = task_pair
    engine = Mock()
    engine.update_task_assignee.side_effect = [{}, FlowableError(404, "task not found"), {}]
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        handover_id, states = _statuses(_post_handover(task_pair))
        assert states == {first.id: "succeeded", second.id: "failed"}
        assert _retry(handover_id, permissions=["handover-View"]).status_code == 403
        assert _retry(handover_id, domain="other.com").status_code == 404
        assert _statuses(_retry(handover_id, username="reviewer")) == (handover_id, {first.id: "succeeded", second.id: "succeeded"})
    assert engine.update_task_assignee.call_args_list == [
        call("first", "replacement"),
        call("second", "replacement"),
        call("second", "replacement"),
    ]
    assert first.ticket.logs.get(action="transfer").operator == "admin"
    assert second.ticket.logs.get(action="transfer").operator == "reviewer"
    response = resources(request(permissions=["handover-View", "handover-Add", "ticket-View"]), "handovers")
    data = json.loads(response.content)["data"]
    row = data["items"][0]
    assert data["can_add"] and data["can_retry"]
    assert row["created_at"]
    assert [item["status"] for item in row["results"]] == ["succeeded", "succeeded"]
    assert {first.ticket_id, second.ticket_id} == {item["ticket_id"] for item in row["results"]}
    change_target = request("patch", {"to_user": "another"}, permissions=["handover-Edit"])
    assert resource_item(change_target, "handovers", handover_id).status_code == 405
    can_retry_without_ticket_view = resources(request(permissions=["handover-View", "handover-Add"]), "handovers")
    data = json.loads(can_retry_without_ticket_view.content)["data"]
    assert (data["can_add"], data["can_retry"]) == (False, True)


def test_handover_rechecks_source_assignee_after_preflight(task_pair):
    first, second = task_pair
    engine = Mock()

    def change_other_task(_task_id, _assignee):
        TicketTask.objects.filter(pk=second.pk).update(assignee="new-assignee")
        return {}

    engine.update_task_assignee.side_effect = change_other_task
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        handover_id, states = _statuses(_post_handover(task_pair))
        assert states == {first.id: "succeeded", second.id: "skipped"}
        assert _statuses(_retry(handover_id)) == (handover_id, states)
    engine.update_task_assignee.assert_called_once_with("first", "replacement")
    second.refresh_from_db()
    assert second.assignee == "new-assignee"


def test_retry_resumes_only_pending_work_after_interruption(task_pair):
    first, second = task_pair
    handover = Handover.objects.create(
        from_user="handler",
        to_user="replacement",
        ticket_ids=[first.ticket_id, second.ticket_id],
        results=[
            {"ticket_id": first.ticket_id, "task_id": first.id, "status": "unconfirmed", "message": "结果待核对"},
            {"ticket_id": second.ticket_id, "task_id": second.id, "status": "pending", "message": "待执行"},
        ],
    )
    engine = Mock()
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        assert _statuses(_retry(handover.id)) == (handover.id, {first.id: "unconfirmed", second.id: "succeeded"})
    engine.update_task_assignee.assert_called_once_with("second", "replacement")


def test_handover_rejects_foreign_or_unavailable_tickets_before_engine_calls(task_pair):
    first, second = task_pair
    engine = Mock()
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        second.assignee = "another"
        second.save(update_fields=["assignee"])
        assert _post_handover(task_pair).status_code == 400
        assert _post_handover([]).status_code == 400
        second.ticket.domain = "other.com"
        second.ticket.save(update_fields=["domain"])
        assert _post_handover(task_pair).status_code == 403
        same = {"from_user": "handler", "to_user": "handler", "ticket_ids": [first.ticket_id]}
        assert resources(request("post", same, "admin", ["handover-Add"]), "handovers").status_code == 400
        payload = {**same, "to_user": "replacement"}
        assert resources(request("put", payload, "admin", ["handover-Edit"]), "handovers").status_code == 405
    assert not Handover.objects.exists()
    engine.update_task_assignee.assert_not_called()


def test_candidates_require_view_and_only_return_visible_tickets_for_source(task_pair):
    first, second = task_pair
    first.ticket.title = "待交接 A"
    first.ticket.save(update_fields=["title"])
    other = TicketService().create(first.ticket.workflow_version, {"title": "不该显示", "amount": 10}, "owner")
    TicketTask.objects.create(ticket=other, node_id=first.node_id, assignee="not-source")
    suspended = TicketService().create(first.ticket.workflow_version, {"title": "待交接但已挂起", "amount": 10}, "owner")
    suspended.status = TicketStatus.objects.create(key="suspended", name="挂起")
    suspended.save(update_fields=["status"])
    TicketTask.objects.create(ticket=suspended, node_id=first.node_id, assignee="handler")
    second.ticket.domain = "other.com"
    second.ticket.save(update_fields=["domain"])
    view = resolve("/api/handovers/candidates/", urlconf="apps.itsm.urls").func
    params = {"from_user": "handler", "q": "交接"}
    assert view(request(payload=params, username="handler", permissions=["handover-Add"])).status_code == 403
    assert view(request(payload=params, username="handler", permissions=["ticket-View"])).status_code == 403
    response = view(request(payload=params, username="handler", permissions=["handover-Add", "ticket-View"]))
    assert response.status_code == 200
    assert json.loads(response.content)["data"] == {"items": [{"id": first.ticket_id, "sn": first.ticket.sn, "title": "待交接 A"}], "count": 1}
    invisible = view(request(payload=params, username="outsider", permissions=["handover-Add", "ticket-View"]))
    assert json.loads(invisible.content)["data"] == {"items": [], "count": 0}
