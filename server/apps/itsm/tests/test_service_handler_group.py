from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.itsm.models import HandlerGroup, Service, Ticket, Workflow, WorkflowVersion
from apps.itsm.serializers import ServiceSerializer
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.views.services import _service_item
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db
DOMAIN = "local.example"


@pytest.fixture
def configured_service():
    workflow = Workflow.objects.create(name="请求", key="request", domain=DOMAIN)
    nodes = [{"id": "dispatch", "type": "approval", "multi": {"mode": "any"}, "assignee": {"source": "service_group", "value": []}}]
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={"nodes": nodes}, is_published=True, domain=DOMAIN)
    workflow.current_version = version
    workflow.save()
    return Service.objects.create(name="请求管理", workflow=workflow, is_enabled=False, domain=DOMAIN)


def edit(instance, **data):
    return ServiceSerializer(instance, data=data, context={"domain": DOMAIN}, partial=True)


def test_enable_requires_a_domain_group_with_active_members(configured_service):
    item = configured_service
    nobody = HandlerGroup.objects.create(domain=DOMAIN, name="过期组", members=["disabled", "expired", "foreign"])
    User.objects.create(domain=DOMAIN, username="disabled", disabled=True)
    User.objects.create(domain=DOMAIN, username="expired", account_expires_at=timezone.now() - timedelta(days=1))
    User.objects.create(domain="other.example", username="foreign")
    other = HandlerGroup.objects.create(domain="other.example", name="外域", members=["operator"])
    for candidate in [None, nobody.pk, other.pk]:
        assert not edit(item, is_enabled=True, handler_group=candidate).is_valid()
    assert edit(item, is_enabled=False, handler_group=None).is_valid()

    User.objects.create(domain=DOMAIN, username="operator")
    nobody.members += ["operator"]
    nobody.save()
    change = edit(item, is_enabled=True, handler_group=nobody.pk)
    assert change.is_valid(), change.errors
    change.save()
    assert ServiceSerializer(item).data["handler_group"] == nobody.pk
    assert ServiceSerializer(item).data["requires_handler_group"]
    assert "handler_group" not in _service_item(item)
    assert "requires_handler_group" not in _service_item(item)
    assert TicketService()._assignee_variables(item.workflow.current_version, "creator", {}, service_id=item.pk) == {
        "itsm_assignees_dispatch": ["operator"]
    }


def test_invalid_group_blocks_creation_before_persist_or_engine_call(configured_service):
    svc = TicketService(Mock())
    for service in (None, configured_service):
        with pytest.raises(ValueError, match="处理组|停用"):
            svc.create(configured_service.workflow.current_version, {"title": "无效分派"}, "me", service=service)
    assert not Ticket.objects.exists()
    svc.client.start_process.assert_not_called()


def test_old_preset_is_not_enabled_or_started_and_existing_ticket_is_untouched(configured_service):
    from importlib import import_module
    from types import SimpleNamespace

    from django.apps import apps
    from django.db import connection

    item = configured_service
    version = item.workflow.current_version
    item.workflow.key = "itsm_request"
    item.workflow.domain = "domain.com"
    item.workflow.save()
    version.domain = "domain.com"
    version.workflow = item.workflow
    version.created_by = "system"
    version.design = {
        "nodes": [
            {"id": "approve", "assignee": {"source": "users", "value": ["alice", "bob"]}},
            {"id": "handle", "assignee": {"source": "users", "value": ["handler"]}},
        ]
    }
    version.save()
    item.domain = "domain.com"
    item.is_enabled = True
    item.save()
    original_draft = WorkflowVersion.objects.create(workflow=item.workflow, version_no=2, design={"name": "管理员草稿"})
    import_module("apps.itsm.migrations.0029_service_handler_group").disable_legacy_presets(apps, SimpleNamespace(connection=connection))
    item.refresh_from_db()
    assert not item.is_enabled
    original_draft.refresh_from_db()
    assert original_draft.design == {"name": "管理员草稿"} and not original_draft.is_published
    change = ServiceSerializer(item, data={"is_enabled": True}, partial=True, context={"domain": item.domain})
    assert not change.is_valid() and "示例账号" in str(change.errors)
    with pytest.raises(ValueError, match="示例账号"):
        TicketService(Mock()).create(version, {"title": "绕过门户"}, "admin", service=item)
    assert not Ticket.objects.exists()


def test_group_change_is_checked_again_before_next_assignment(configured_service):
    svc = configured_service
    approved = User.objects.create(domain=DOMAIN, username="current")
    User.objects.create(domain=DOMAIN, username="next")
    group = HandlerGroup.objects.create(domain=DOMAIN, members=["current", "next"])
    change = edit(svc, is_enabled=True, handler_group=group.pk)
    assert change.is_valid()
    change.save()
    approved.disabled = True
    approved.save()
    assert TicketService()._assignee_variables(svc.workflow.current_version, "admin", {}, service_id=svc.pk) == {"itsm_assignees_dispatch": ["next"]}
    group.members = []
    group.save()
    with pytest.raises(ValueError, match="有效成员"):
        TicketService()._assignee_variables(svc.workflow.current_version, "admin", {}, service_id=svc.pk)


def test_publishing_service_group_node_takes_unbound_services_offline(configured_service):
    from unittest.mock import patch

    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.api import publish_workflow

    item = configured_service
    item.is_enabled = True
    item.save()
    nodes = [{"id": "start", "type": "start"}, *item.workflow.current_version.design["nodes"], {"id": "end", "type": "end"}]
    design = {"nodes": nodes, "edges": [{"from": "start", "to": "dispatch"}, {"from": "dispatch", "to": "end"}]}
    version = WorkflowVersion.objects.create(workflow=item.workflow, version_no=2, design=design, domain=DOMAIN)
    with patch("apps.itsm.views.api.FlowableClient") as client:
        client.return_value.deploy_bpmn.return_value = {"id": "deployment"}
        client.return_value.definition_for_deployment.return_value = "definition"
        response = publish_workflow(request("post", {}, "designer", ["workflow-Publish"], domain=DOMAIN), item.workflow_id)
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.workflow.current_version == version
    assert not item.is_enabled


def test_manager_options_and_implicit_service_choice_are_domain_scoped(configured_service):
    from apps.itsm.services.service_access import check_service_request
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.services import ServiceView

    item = configured_service
    user = User.objects.create(domain=DOMAIN, username="agent")
    group = HandlerGroup.objects.create(domain=DOMAIN, name="本域", members=[user.username])
    HandlerGroup.objects.create(domain=DOMAIN, name="空组")
    HandlerGroup.objects.create(domain="other", name="外域组", members=[user.username])
    manager = request(permissions=["workflow-Edit"], domain=DOMAIN)
    view = ServiceView().get(manager).data
    assert view["eligible_handler_groups"] == [{"id": group.pk, "name": "本域"}]
    assert view["requires_handler_group_workflow_ids"] == [item.workflow_id]
    assert view["items"][0]["requires_handler_group"]
    item.is_enabled = True
    item.handler_group = group
    item.save()
    requestor = request(username="applicant", domain=DOMAIN)
    version = item.workflow.current_version
    assert check_service_request(requestor, version) == item
    second = Service.objects.create(domain=DOMAIN, name="另一个", workflow=item.workflow, handler_group=group, visibility="restricted")
    assert check_service_request(requestor, version) == item
    second.visibility = "all"
    second.save()
    with pytest.raises(ValueError, match="请选择具体服务"):
        check_service_request(requestor, version)
    assert check_service_request(requestor, version, second.pk) == second


def test_inflight_group_ticket_keeps_its_service_binding(configured_service):
    from apps.itsm.models import TicketStatus
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.services import ServiceView

    item = configured_service
    User.objects.create(domain=DOMAIN, username="agent")
    group = HandlerGroup.objects.create(domain=DOMAIN, members=["agent"])
    binding = edit(item, is_enabled=True, handler_group=group.pk)
    assert binding.is_valid()
    binding.save()
    version = item.workflow.current_version
    ticket = Ticket.objects.create(sn="OPEN-GROUP", service=item, workflow=item.workflow, workflow_version=version, domain=DOMAIN)
    item.workflow.current_version = WorkflowVersion.objects.create(
        workflow=item.workflow, version_no=2, design={"nodes": []}, is_published=True, domain=DOMAIN
    )
    item.workflow.save()
    another = Workflow.objects.create(key="another", domain=DOMAIN)
    for payload in ({"handler_group": None, "is_enabled": False}, {"workflow_id": another.pk}):
        change = edit(item, **payload)
        assert not change.is_valid() and "在办工单" in str(change.errors)
    req = request(permissions=["workflow-Edit"], domain=DOMAIN)
    req.GET = {"id": item.pk}
    denied = ServiceView().delete(req)
    assert denied.status_code == 400 and "在办工单" in str(denied.data)
    disable = edit(item, is_enabled=False)
    assert disable.is_valid()
    disable.save()
    assert TicketService()._assignee_variables(version, "admin", {}, service_id=item.pk) == {"itsm_assignees_dispatch": ["agent"]}
    ticket.status = TicketStatus.objects.create(key="finished", is_terminal=True, domain=DOMAIN)
    ticket.save()
    assert ServiceView().delete(req).status_code == 200


def test_ordinary_ticket_does_not_prevent_service_removal(configured_service):
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.services import ServiceView

    item = configured_service
    version = item.workflow.current_version
    version.design = {"nodes": [{"id": "handle", "type": "handle", "assignee": {"source": "users", "value": ["alice"]}}]}
    version.save()
    Ticket.objects.create(sn="OPEN-ORDINARY", service=item, workflow=item.workflow, workflow_version=version, domain=DOMAIN)
    req = request(permissions=["workflow-Edit"], domain=DOMAIN)
    req.GET = {"id": item.pk}
    assert ServiceView().delete(req).status_code == 200


def test_service_cannot_enable_or_remain_enabled_on_unpublished_workflow(configured_service):
    item = configured_service
    draft_workflow = Workflow.objects.create(domain=DOMAIN, key="draft_flow")
    version = WorkflowVersion.objects.create(workflow=draft_workflow, domain=DOMAIN, version_no=1)
    item.is_enabled = True
    item.save()
    assert not edit(item, workflow_id=draft_workflow.pk).is_valid()
    item.workflow = draft_workflow
    item.is_enabled = False
    item.save()
    assert not edit(item, is_enabled=True, handler_group=None).is_valid()
    draft_workflow.current_version = version
    draft_workflow.save()
    assert not edit(item, is_enabled=True).is_valid()


def test_switching_back_to_group_version_disables_unbound_service(configured_service):
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.m2 import enable_version

    item = configured_service
    original = item.workflow.current_version
    normal = WorkflowVersion.objects.create(workflow=item.workflow, domain=DOMAIN, version_no=2, is_published=True, design={"nodes": []})
    item.workflow.current_version = normal
    item.workflow.save()
    item.is_enabled = True
    item.save()
    response = enable_version(request("post", {}, permissions=["workflow-Publish"], domain=DOMAIN), item.workflow_id, original.pk)
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.workflow.current_version == original and not item.is_enabled
