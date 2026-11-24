from unittest.mock import Mock, patch

import pytest
from django.test import RequestFactory

from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import Ticket, Workflow, WorkflowVersion
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.views.api import publish_workflow
from apps.itsm.views.ticket_operations import create_child


def test_full_engine_tree_and_short_pages():
    client = FlowableClient("", "", "")
    tasks = {"root": ["1", "2", "3"], "child": [], "deep": ["4"], "other": ["5"]}
    children = {"root": ["child", "other"], "child": ["deep"]}

    def page(method, path, params):
        rows = tasks[params["processInstanceId"]] if path.endswith("/tasks") else children.get(params["superProcessInstanceId"], [])
        offset = params.get("start", 0)
        return {"start": offset, "total": len(rows), "data": [{"id": id_} for id_ in rows[offset:offset + 1]]}

    client._request = page
    assert {item["id"] for item in client.list_tasks_including_children("root")} == set("12345")


@pytest.mark.parametrize("view", [publish_workflow, create_child])
@pytest.mark.parametrize("method", ["get", "head"])
def test_reads_cannot_mutate(view, method):
    assert view(getattr(RequestFactory(), method)("/"), 1).status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize("lost_reply", [False, True])
def test_start_recovers_without_replaying(lost_reply):
    workflow = Workflow.objects.create(key="same-key", name="版本绑定")
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={}, process_definition_key=workflow.key, flowable_deployment_id="dep1")
    client = Mock()
    client.definition_for_deployment.return_value = "same-key:1:stable"
    client.start_process.side_effect = [FlowableError(0, "") if lost_reply else {"id": "existing"}]
    client.instance_for_business_key.return_value = "existing"
    service = TicketService(client)
    with patch.object(service, "sync_ticket", side_effect=[None] if lost_reply else [FlowableError(502, ""), None]):
        with pytest.raises(FlowableError):
            service.create(version, {}, "owner", creation_key="attempt")
        ticket = Ticket.objects.get()
        result = service.create(version, {}, "owner", creation_key="attempt")
        assert result.pk == ticket.pk and result.process_instance_id == "existing"
        client.start_process.assert_called_once_with("same-key:1:stable", ticket.sn, {"initiator": "owner"})
        assert service.create(version, {}, "owner", creation_key="attempt").pk == ticket.pk


@pytest.mark.django_db
def test_published_version_is_reused_and_child_inherits_identity():
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.models import TicketRelation

    workflow = Workflow.objects.create(key="published", name="已发布")
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, is_published=True, flowable_deployment_id="existing")
    parent = Ticket.objects.create(workflow=workflow, workflow_version=version, title="测试单", sn="TEST", creator="owner", is_test=True)
    with patch("apps.itsm.views.api.FlowableClient") as engine:
        assert publish_workflow(request("post", permissions=["workflow-Publish"]), workflow.id).status_code == 200
        engine.assert_not_called()
    req = request("post", {"form_data": {"title": "子单"}}, username="owner", permissions=["ticket-Add"])
    client = Mock()
    client.definition_for_deployment.return_value = "published:1:existing"
    client.start_process.return_value = {"id": "child-instance"}
    client.list_tasks_including_children.return_value = [{"id": "submit", "taskDefinitionKey": "submit"}]
    with patch("apps.itsm.views.ticket_operations._service", return_value=TicketService(client)) as factory:
        assert create_child(req, parent.id).status_code == 200
        factory.assert_called_once_with(req)
    assert TicketRelation.objects.get(ticket=parent).related.is_test


@pytest.mark.django_db
def test_scheduler_drains_previously_claimed_slot_and_reconciles_interrupted_run():
    import json
    from datetime import timedelta
    from django.utils import timezone
    from apps.itsm.models.extend import ScheduledTask
    from apps.itsm.services import schedules

    due = timezone.now()
    item = ScheduledTask.objects.create(name="定时", created_by="owner", next_run_at=due,
        action=json.dumps({"mode": "once", "task": "remind", "once_at": due.isoformat()}))
    schedules._claim(item.pk, due)
    with patch("apps.itsm.services.notify.service.dispatch_notification", return_value={"site": {"result": True}}) as notify:
        assert schedules.run_due(Mock(), now=due) == 1
        assert item.runs.get().status == "succeeded"
        item.runs.update(status="running", updated_at=due - timedelta(hours=1))
        assert schedules.run_due(Mock(), now=due) == 0
        assert item.runs.get().status == "unconfirmed"
        notify.assert_called_once()


@pytest.mark.django_db
def test_subform_confirmation_survives_parent_failure():
    from apps.itsm.models import TicketRelation
    from apps.itsm.services.ticket.subforms import materialize_subforms

    parent_flow = Workflow.objects.create(key="parent", name="父单")
    parent_version = WorkflowVersion.objects.create(workflow=parent_flow, version_no=1)
    child_flow = Workflow.objects.create(key="child", name="子单")
    child_version = WorkflowVersion.objects.create(workflow=child_flow, version_no=1, is_published=True)
    form_data = {"details": [{"form_data": {"title": "子行"}}]}
    schema = {"fields": [{"key": "details", "type": "subProcessForm", "props": {"workflow_version_id": child_version.pk}}]}
    parent = Ticket.objects.create(workflow=parent_flow, workflow_version=parent_version, sn="PARENT", title="父单", form_data=form_data, creator="creator", is_test=True)
    materialize_subforms(TicketService(), parent, schema, parent.creator, initial=True)
    parent.refresh_from_db()
    materialize_subforms(TicketService(), parent, schema, parent.creator, initial=True)
    assert TicketRelation.objects.filter(ticket=parent).count() == 1
    assert Ticket.objects.get(workflow=child_flow).is_test


def test_definition_mismatch_and_partial_task_page_fail_closed():
    client = FlowableClient("", "", "")
    client._request = Mock(side_effect=[
        {"total": 1, "data": [{"id": "wrong", "deploymentId": "another", "key": "key"}]},
        {"total": 2, "data": [{"id": "task"}]}, {"total": 2, "start": 1, "data": []},
    ])
    with pytest.raises(FlowableError):
        client.definition_for_deployment("expected", "key")
    with pytest.raises(FlowableError):
        client.list_tasks("instance")


@pytest.mark.django_db
def test_deployed_version_waits_for_engine_before_finishing():
    workflow = Workflow.objects.create(name="引擎离线", key="offline")
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, process_definition_key=workflow.key,
        process_definition_id="offline:1:known", flowable_deployment_id="deployment")
    with pytest.raises(FlowableError):
        TicketService().create(version, {}, "creator", creation_key="same")
    ticket = Ticket.objects.get()
    assert ticket.creation_state == "prepared" and not ticket.process_instance_id
    engine = Mock()
    engine.start_process.return_value = {"id": "started"}
    engine.list_tasks_including_children.return_value = [{"id": "submit", "taskDefinitionKey": "submit"}]
    recovered = TicketService(engine).create(version, {}, "creator", creation_key="same")
    assert recovered.pk == ticket.pk and recovered.creation_state == "complete"
    engine.start_process.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["schedule-7", "email-3", "a" * 64, "长" * 128])
def test_http_creation_keys_are_isolated_from_internal_origins(key):
    import json

    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.tickets import tickets

    flow = Workflow.objects.create(name="申请", key="scope")
    version = WorkflowVersion.objects.create(workflow=flow, version_no=1, is_published=True)
    original = TicketService().create(version, {"title": "系统工单"}, "owner", creation_key=key)
    body = {"workflow_version_id": version.pk, "creation_key": key, "form_data": {"title": "手工工单"}}
    def submit(payload):
        return tickets(request("post", payload, username="owner", permissions=["ticket-View", "ticket-Add"]))

    response = json.loads(submit(body).content)
    assert response["result"] and response["data"]["id"] != original.pk
    assert json.loads(submit(body).content)["data"]["id"] == response["data"]["id"]
    assert submit({**body, "creation_key": "长" * 129}).status_code == 400
    assert Ticket.objects.count() == 2
