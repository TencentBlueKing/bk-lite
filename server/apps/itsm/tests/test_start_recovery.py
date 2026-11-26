from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.itsm.flowable.client import FlowableError, NoStartedInstance
from apps.itsm.models import Ticket, TicketLog, TicketStatus, Workflow, WorkflowVersion
from apps.itsm.models.ticket import TicketStartAttempt
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.services.ticket.start_recovery import confirm_not_started, reconcile_starts

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    workflow = Workflow.objects.create(key="flow", name="申请")
    version = WorkflowVersion.objects.create(
        workflow=workflow, version_no=1, process_definition_key="flow", process_definition_id="flow:1", is_published=True
    )
    for state in ("new", "processing", "finished"):
        TicketStatus.objects.create(key=state, name=state)
    engine = Mock()
    engine.list_tasks_including_children.return_value = []
    return TicketService(engine), version, engine


def test_reopen_timed_out_retries_only_lookup(setup):
    service, version, engine = setup
    ticket = Ticket.objects.create(
        sn="TEST001",
        title="单",
        creator="owner",
        workflow=version.workflow,
        workflow_version=version,
        process_instance_id="old",
        status=TicketStatus.objects.get(key="finished"),
    )
    engine.get_process_instance.side_effect = FlowableError(404, "finished")
    engine.start_process.side_effect = FlowableError(0, "lost reply")
    with pytest.raises(FlowableError):
        service.operate(ticket, None, "reopen", {"opinion": "再次申请"}, "owner")
    ticket.refresh_from_db()
    assert ticket.process_instance_id == "old" and ticket.status.key == "finished"
    with pytest.raises(PermissionError):
        service.operate(ticket, None, "reopen", {}, "outsider")
    engine.instance_for_business_key.return_value = "round-two"
    reconcile_starts(engine)
    ticket.refresh_from_db()
    assert ticket.process_instance_id == "round-two"
    assert ticket.status.key == "processing"
    assert TicketLog.objects.get(ticket=ticket, action="reopen").detail["opinion"] == "再次申请"
    key = engine.start_process.call_args.args[1]
    assert key != ticket.sn
    engine.instance_for_business_key.assert_called_with(key, "flow:1")
    assert engine.start_process.call_count == 1
    reconcile_starts(engine)
    assert TicketLog.objects.filter(ticket=ticket, action="reopen").count() == 1


def test_first_start_ambiguous_needs_explicit_confirmation(setup):
    service, version, engine = setup
    engine.start_process.side_effect = [FlowableError(0, "unknown"), {"id": "first"}]
    with pytest.raises(FlowableError):
        service.create(version, {}, "owner", creation_key="key")
    ticket = Ticket.objects.get()
    engine.instance_for_business_key.side_effect = NoStartedInstance()
    reconcile_starts(engine)
    assert engine.start_process.call_count == 1
    attempt = TicketStartAttempt.objects.get(ticket=ticket)
    with pytest.raises(ValueError):
        confirm_not_started(service, ticket, attempt.pk, "核对引擎与网关日志，未受理", "manager")
    TicketStartAttempt.objects.filter(pk=attempt.pk).update(sent_at=timezone.now() - timedelta(minutes=5))
    confirm_not_started(service, ticket, attempt.pk, "核对引擎与网关日志，未受理", "manager")
    ticket.refresh_from_db()
    assert ticket.process_instance_id == "first" and ticket.creation_state == "complete"
    assert TicketLog.objects.filter(ticket=ticket, action="start_reconcile", operator="manager").exists()
    assert engine.start_process.call_count == 2


def test_confirm_denied_without_both_permissions_and_ticket_scope(setup):
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.tickets import recover_start

    service, version, engine = setup
    engine.start_process.side_effect = FlowableError(0, "unknown")
    with pytest.raises(FlowableError):
        service.create(version, {}, "owner", creation_key="key")
    ticket = Ticket.objects.get()
    attempt = TicketStartAttempt.objects.get()
    args = {"action": "confirmed_not_started", "id": attempt.pk, "sent_at": attempt.sent_at.isoformat(), "reason": "核对"}
    assert recover_start(request("post", args, "owner", permissions=["ticket-View", "ticket-Operate"]), ticket.pk).status_code == 403
    perms = ["ticket-View", "ticket-Operate", "workflow-Edit"]
    assert recover_start(request("post", args, "other", permissions=perms), ticket.pk).status_code == 404
    assert recover_start(request("post", args, "owner", permissions=perms, domain="other"), ticket.pk).status_code == 404
    engine.start_process.assert_called_once()


def test_safe_connect_timeout_retries_without_human_decision(setup):
    from apps.itsm.flowable.client import FlowableNotSent

    service, version, engine = setup
    engine.start_process.side_effect = [FlowableNotSent(0, "no connection"), {"id": "accepted"}]
    with pytest.raises(FlowableNotSent):
        service.create(version, {}, "owner", creation_key="key")
    assert TicketStartAttempt.objects.get().state == "ready"
    assert reconcile_starts(engine) == 1
    assert Ticket.objects.get().process_instance_id == "accepted"


def test_reopen_stale_request_does_not_open_a_later_round(setup):
    service, version, engine = setup
    ended = TicketStatus.objects.get(key="finished")
    ticket = Ticket.objects.create(
        sn="RETRY1", title="单", creator="owner", workflow=version.workflow, workflow_version=version, process_instance_id="old", status=ended
    )
    engine.start_process.return_value = {"id": "second"}
    engine.get_process_instance.side_effect = FlowableError(404, "finished")
    service.operate(ticket, None, "reopen", {"reopen_from": "old"}, "owner")
    Ticket.objects.filter(pk=ticket.pk).update(status=ended)
    result = service.operate(ticket, None, "reopen", {"reopen_from": "old"}, "owner")
    assert result.status == ended and result.process_instance_id == "second"
    engine.start_process.assert_called_once()


def test_multiple_history_instances_never_authorizes_manual_replay(setup):
    service, version, engine = setup
    engine.start_process.side_effect = FlowableError(0, "lost reply")
    with pytest.raises(FlowableError):
        service.create(version, {}, "owner", creation_key="key")
    attempt = TicketStartAttempt.objects.get()
    TicketStartAttempt.objects.filter(pk=attempt.pk).update(sent_at=timezone.now() - timedelta(minutes=5))
    engine.instance_for_business_key.side_effect = FlowableError(409, "multiple")
    with pytest.raises(FlowableError):
        confirm_not_started(service, attempt.ticket, attempt.pk, "人工核对", "manager")
    assert TicketStartAttempt.objects.get().state == "sending"
    engine.start_process.assert_called_once()


def test_reopen_validates_transition_before_sending(setup):
    from apps.itsm.models import StatusTransition

    service, version, engine = setup
    finished = TicketStatus.objects.get(key="finished")
    StatusTransition.objects.create(from_status=finished, to_status=TicketStatus.objects.get(key="new"), name="仅允许退回新建")
    ticket = Ticket.objects.create(
        sn="TEST-GUARD",
        title="重开校验",
        creator="owner",
        workflow=version.workflow,
        workflow_version=version,
        process_instance_id="old",
        status=finished,
    )
    engine.get_process_instance.side_effect = FlowableError(404, "finished")
    engine.start_process.return_value = {"id": "unexpected"}
    with pytest.raises(ValueError):
        service.operate(ticket, None, "reopen", {"reopen_from": "old"}, "owner")
    engine.start_process.assert_not_called()
    assert not ticket.start_attempts.exists()


def test_reopen_http_requires_round_from_detail(setup):
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.tickets import operate_ticket

    _, version, _ = setup
    ticket = Ticket.objects.create(
        sn="OLD-REQUEST",
        title="重开轮次",
        creator="owner",
        workflow=version.workflow,
        workflow_version=version,
        process_instance_id="old",
        status=TicketStatus.objects.get(key="finished"),
    )
    response = operate_ticket(request("post", {"action": "reopen"}, username="owner"), ticket.pk)
    assert response.status_code == 409
    assert not ticket.start_attempts.exists()
