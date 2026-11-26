import json

import pytest

from apps.itsm.models import TicketLog, TicketTask
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as sample_fixture
from apps.itsm.views.tickets import operate_ticket, ticket_detail

sample = sample_fixture
pytestmark = pytest.mark.django_db
APPLY = ["ticket-View", "ticket-Add"]


def test_applicant_can_submit_only_own_submission_step(sample):
    ticket, task = sample
    task.node_id, task.assignee = "submit", "owner"
    task.save()
    version = ticket.workflow_version
    node = version.design["nodes"][0]
    node["required_opinion_actions"] = ["submit"]
    version.save()
    detail = ticket_detail(request("get", {"task_id": task.pk}, "owner", APPLY), ticket.pk)
    assert detail.status_code == 200
    values = json.loads(detail.content)["data"]
    row = next(row for row in values["tasks"] if row["id"] == task.pk)
    assert row["can_operate"] and row["allowed_actions"] == ["submit"]
    assert row["required_opinion_actions"] == ["submit"] and values["allowed_actions"] == []

    def post(action, **kwargs):
        return operate_ticket(request("post", {"task_id": task.pk, "action": action, **kwargs}, "owner", APPLY), ticket.pk)

    for action in ("claim", "save", "approve", "withdraw", "urge"):
        assert post(action).status_code == 403
    assert json.loads(post("submit").content)["result"] is False
    assert json.loads(post("submit", opinion="已核对").content)["result"] is True
    assert post("submit", opinion="重试").status_code == 403
    assert list(TicketLog.objects.filter(task=task, action="submit").values_list("operator", flat=True)) == ["owner"]


@pytest.mark.parametrize(
    "node_type,actor,assignee,permissions",
    [
        ("approval", "owner", "owner", APPLY),
        ("handle", "owner", "owner", APPLY),
        ("submit", "owner", "handler", APPLY),
        ("submit", "handler", "handler", APPLY),
        ("submit", "owner", "owner", ["ticket-View"]),
        ("submit", "owner", "owner", ["ticket-Add"]),
    ],
)
def test_application_permission_cannot_extend_to_other_tasks(sample, node_type, actor, assignee, permissions):
    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["type"] = node_type
    version.save()
    task.assignee = assignee
    task.save()
    detail = ticket_detail(request("get", {}, actor, permissions), ticket.pk)
    if detail.status_code == 200:
        row = next(row for row in json.loads(detail.content)["data"]["tasks"] if row["id"] == task.pk)
        assert not row["can_operate"] and not row["allowed_actions"]
    result = operate_ticket(request("post", {"task_id": task.pk, "action": "submit"}, actor, permissions), ticket.pk)
    assert result.status_code == 403
    assert TicketTask.objects.get(pk=task.pk).status == "pending"


@pytest.mark.parametrize("blocked", ["subprocess", "disabled_button"])
def test_matching_node_name_cannot_override_process_origin_or_enabled_actions(sample, blocked):
    ticket, task = sample
    task.assignee, task.node_id = "owner", "submit"
    if blocked == "subprocess":
        task.process_instance_id = "child"
    else:
        version = ticket.workflow_version
        version.design["nodes"][0]["actions"] = []
        version.save()
    task.save()
    response = ticket_detail(request("get", {}, "owner", APPLY), ticket.pk)
    row = next(row for row in json.loads(response.content)["data"]["tasks"] if row["id"] == task.pk)
    assert row["allowed_actions"] == [] and not row["can_operate"]
    response = operate_ticket(request("post", {"action": "submit", "task_id": task.pk}, "owner", APPLY), ticket.pk)
    assert response.status_code == 403
