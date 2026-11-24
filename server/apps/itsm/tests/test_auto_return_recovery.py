import pytest

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import Ticket, TicketStatus
from apps.itsm.tests import test_start_recovery

engine_setup = test_start_recovery.setup


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["initial", "reopen"])
@pytest.mark.parametrize("lost_callback", [False, True])
def test_node_auto_return_runs_after_round_commit_and_survives_lost_callback(engine_setup, kind, lost_callback):
    from contextlib import nullcontext
    from unittest.mock import patch

    from apps.itsm.services.ticket.manual_recovery import active_operations, reconcile_manual_operations

    service, version, engine = engine_setup
    version.design = {
        "nodes": [
            {"id": "submit", "type": "submit"},
            {"id": "review", "type": "approval", "fallback": "owner", "auto_return": {"field": "route", "value": "back"}},
        ]
    }
    version.save()
    engine.start_process.return_value = {"id": "instance"}
    engine.get_process_instance.side_effect = FlowableError(404, "")
    engine.list_tasks_including_children.return_value = [
        {"id": "review-task", "taskDefinitionKey": "review", "processInstanceId": "instance", "assignee": "owner"},
    ]
    observed = []

    def change_state(*_):
        current = Ticket.objects.get(process_instance_id="instance")
        observed.append((current.creation_state, list(current.start_attempts.values_list("state", flat=True))))
        engine.list_tasks_including_children.return_value = [
            {"id": "submit-task", "taskDefinitionKey": "submit", "processInstanceId": "instance", "assignee": "owner"},
        ]

    engine.change_state.side_effect = change_state
    lose = patch("apps.itsm.services.ticket.manual_recovery.advance") if lost_callback else nullcontext()
    with lose:
        if kind == "initial":
            ticket = service.create(version, {"route": "back"}, "owner", creation_key="begin", is_test=True)
        else:
            ticket = Ticket.objects.create(
                sn="REOPEN",
                title="重开",
                workflow=version.workflow,
                workflow_version=version,
                creator="owner",
                is_test=True,
                process_instance_id="old",
                status=TicketStatus.objects.get(key="finished"),
                form_data={"route": "back"},
            )
            service.operate(ticket, None, "reopen", {}, "owner")
    if lost_callback:
        engine.change_state.assert_not_called()
        assert active_operations(ticket).get().status == "prepared"
        assert reconcile_manual_operations(engine) == 1
    assert reconcile_manual_operations(engine) == 0
    assert observed == [("complete", ["complete"])]
    engine.change_state.assert_called_once_with("instance", ["review"], ["submit"])
    assert ticket.logs.filter(action="return", operator="system").count() == 1


@pytest.mark.django_db(transaction=True)
def test_rolled_back_node_sync_sends_nothing_and_early_scanner_waits(engine_setup):
    from unittest.mock import patch

    from django.db import transaction

    from apps.itsm.services.ticket.manual_recovery import active_operations, reconcile_manual_operations

    service, version, engine = engine_setup
    version.design = {
        "nodes": [
            {"id": "submit", "type": "submit"},
            {"id": "review", "type": "approval", "auto_return": {"field": "route", "value": "back"}},
        ]
    }
    version.save()
    ticket = Ticket.objects.create(
        sn="BOUND",
        title="创建中",
        workflow=version.workflow,
        workflow_version=version,
        creator="owner",
        is_test=True,
        process_instance_id="bound",
        creation_state="bound",
        form_data={"route": "back"},
    )
    engine.list_tasks_including_children.return_value = [
        {"id": "task", "taskDefinitionKey": "review", "processInstanceId": "bound", "assignee": "owner"},
    ]
    with pytest.raises(RuntimeError), transaction.atomic():
        service.sync_ticket(ticket)
        assert active_operations(ticket).get().status == "prepared"
        raise RuntimeError("同步事务回滚")
    assert not active_operations(ticket).exists()
    engine.change_state.assert_not_called()
    with patch("apps.itsm.services.ticket.manual_recovery.advance"):
        service.sync_ticket(ticket)
    assert reconcile_manual_operations(engine) == 0
    engine.change_state.assert_not_called()
    assert active_operations(ticket).get().status == "prepared"
