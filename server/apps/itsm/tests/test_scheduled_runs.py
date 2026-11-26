import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import Ticket, Workflow, WorkflowVersion
from apps.itsm.models.extend import ScheduledTask
from apps.itsm.services import schedules
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views import extend

pytestmark = pytest.mark.django_db


@pytest.fixture
def workflow():
    workflow = Workflow.objects.create(key="schedule", name="定时建单测试", domain="domain.com")
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        domain=workflow.domain,
        version_no=1,
        is_published=True,
        process_definition_key="schedule-v1",
        design={"nodes": []},
    )
    workflow.current_version = version
    workflow.save()
    return workflow


@pytest.mark.parametrize("mode", ["once", "cron"])
def test_schedule_has_one_ticket_per_slot(workflow, mode):
    now = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
    due = now + timedelta(minutes=1)
    item = ScheduledTask.objects.create(
        name="定时建单",
        domain=workflow.domain,
        created_by="owner",
        cron="* * * * *",
        action=json.dumps({"task": "create_ticket", "workflow_id": workflow.id, "mode": mode, "once_at": due.isoformat()}),
    )
    schedules.register_schedule(item, now=now)
    service = Mock()
    service.create.side_effect = lambda version, data, creator, creation_key: Ticket.objects.create(
        sn=f"RUN-{Ticket.objects.count()}",
        title=data["title"],
        creator=creator,
        domain=workflow.domain,
        workflow=workflow,
        workflow_version=version,
        process_instance_id="flowable",
    )
    service_for = Mock(return_value=service)
    assert schedules.run_due(service_for, now=now) == 0
    assert schedules.run_due(service_for, now=due) == 1
    assert schedules.run_due(service_for, now=due) == 0
    ScheduledTask.objects.filter(pk=item.pk).update(next_run_at=due)
    assert schedules.run_due(service_for, now=due) == 0
    assert schedules.run_due(service_for, now=due + timedelta(minutes=1)) == (1 if mode == "cron" else 0)
    assert item.runs.filter(status="succeeded", ticket__isnull=False).count() == (2 if mode == "cron" else 1)


def test_schedule_uncertain_start_is_recorded_without_second_attempt(workflow):
    now = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
    item = ScheduledTask.objects.create(
        name="建单失败",
        domain=workflow.domain,
        created_by="owner",
        cron="* * * * *",
        action=json.dumps({"task": "create_ticket", "workflow_id": workflow.id, "mode": "cron"}),
    )
    schedules.register_schedule(item, now=now)
    service = Mock()
    service.create.side_effect = FlowableError(503, "private")
    due = now + timedelta(minutes=1)
    service_for = Mock(return_value=service)
    assert schedules.run_due(service_for, now=due) == 1
    assert schedules.run_due(service_for, now=due) == 0
    service.create.assert_called_once()
    assert item.runs.get().status == "failed"
    assert "private" not in item.runs.get().message


def test_schedule_validation_and_execution_history_permissions(workflow):
    action = {"task": "create_ticket", "workflow_id": workflow.id, "mode": "cron"}
    body = {"name": "定时", "cron": "invalid", "action": json.dumps(action)}
    actor = ["rule-Add", "rule-View", "ticket-Add"]
    assert extend.resources(request("post", body, username="owner", permissions=["rule-Add"]), "schedules").status_code == 403
    assert extend.resources(request("post", body, username="owner", permissions=actor), "schedules").status_code == 400
    assert (
        extend.resources(request("post", {**body, "cron": "* * * * *"}, username="owner", permissions=actor, domain="other"), "schedules").status_code
        == 400
    )
    assert not ScheduledTask.objects.exists()
    assert extend.resources(request("post", {**body, "cron": "* * * * *"}, username="owner", permissions=actor), "schedules").status_code == 200
    item = ScheduledTask.objects.get()
    ticket = Ticket.objects.create(
        sn="AUDIT",
        title="定时",
        domain=workflow.domain,
        creator="owner",
        workflow=workflow,
        workflow_version=workflow.current_version,
    )
    item.runs.create(schedule_name=item.name, due_at=item.next_run_at, status="succeeded", ticket=ticket, domain=item.domain)
    assert json.loads(extend.schedule_runs(request(permissions=actor)).content)["data"]["items"][0]["ticket_id"] is None
    assert json.loads(extend.schedule_runs(request(permissions=actor, domain="other")).content)["data"]["count"] == 0
    allowed = request(username="owner", permissions=[*actor, "ticket-View"])
    assert json.loads(extend.schedule_runs(allowed).content)["data"]["items"][0]["ticket_id"] == ticket.id
