"""门户编排、数据范围和服务申请授权。"""
import json
from unittest.mock import patch

import pytest

from apps.itsm.models import HandlerGroup, Service, ServiceFavorite, ServiceRecent, Workflow, WorkflowVersion
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.services import service_favorite, service_portal, service_use
from apps.itsm.views.tickets import ticket_form, tickets

pytestmark = pytest.mark.django_db
PERMS = ["portal-View", "ticket-View", "ticket-Add"]


def req(method="get", payload=None, user="owner", domain="domain.com", permissions=None):
    return request(method, payload, user, permissions or PERMS, domain=domain)


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


@pytest.fixture
def service():
    flow = Workflow.objects.create(name="申请流程", key="portal_test")
    version = WorkflowVersion.objects.create(workflow=flow, version_no=1, is_published=True, design={"nodes": [], "edges": []})
    flow.current_version = version
    flow.save()
    return Service.objects.create(name="受限服务", workflow=flow, visibility="restricted", visible_users=["owner"], is_hot=True)


def test_restricted_service_every_entry_checks_visibility(service):
    ServiceFavorite.objects.create(service=service, username="outsider")
    ServiceRecent.objects.create(service=service, username="outsider")
    assert data(service_portal(req()))["services"][0]["id"] == service.id
    portal = data(service_portal(req(user="outsider")))
    assert all(not portal[key] for key in ["services", "recents", "favorites", "hots"])
    assert service_use(req("post", user="outsider"), service.id).status_code == 404
    assert service_favorite(req("post", user="outsider"), service.id).status_code == 404
    assert ticket_form(req(user="outsider"), service.workflow.current_version_id).status_code == 403
    payload = {"workflow_version_id": service.workflow.current_version_id, "form_data": {"title": "越权"}}
    with patch("apps.itsm.views.tickets._service") as engine:
        assert tickets(req("post", payload, user="outsider")).status_code == 403
        assert not engine.called
        payload["service_id"] = service.id
        assert tickets(req("post", payload, user="outsider")).status_code == 404


def test_group_and_domain_and_disabled(service):
    group = HandlerGroup.objects.create(name="服务用户组", members=["member"], leaders=["leader"])
    service.visible_groups = [group.id]
    service.save()
    for username in ["member", "leader"]:
        assert data(service_portal(req(user=username)))["services"]
    assert not data(service_portal(req(user="member", domain="other")))["services"]
    service.is_enabled = False
    service.save()
    assert not data(service_portal(req()))["services"]
    assert service_use(req("post"), service.id).status_code == 404


def test_layout_permission_validation_and_roundtrip():
    from apps.itsm.views.portal_workbench import portal_layout

    config = {"title": "团队服务台", "subtitle": "按需申请", "background": "", "widgets": [{"type": "services", "width": 12}, {"type": "todo", "width": 6}]}
    assert portal_layout(req("put", config)).status_code == 403
    manager = req("put", config, permissions=["portal-View", "workflow-Edit"])
    assert data(portal_layout(manager))["title"] == config["title"]
    assert data(portal_layout(req())) == config
    untouched = data(portal_layout(req(domain="other")))
    assert untouched["title"] == "服务工作台"
    assert untouched["subtitle"] == "发现所需服务，让每一次协作更高效"
    assert untouched["background"] == "blue"
    assert untouched["title"] != config["title"]
    assert untouched["widgets"] == [
        {"type": "stats", "width": 12},
        {"type": "quick", "width": 6},
        {"type": "todo", "width": 6},
        {"type": "services", "width": 6},
        {"type": "tickets", "width": 6},
        {"type": "announcements", "width": 6},
        {"type": "trend", "width": 6},
        {"type": "recents", "width": 6},
        {"type": "favorites", "width": 6},
    ]
    config["widgets"].append({"type": "script", "width": 12})
    assert portal_layout(req("put", config, permissions=["workflow-Edit"])).status_code == 400


def test_portal_dashboard_does_not_leak_tickets(service):
    from apps.itsm.models import Ticket, TicketStatus
    from apps.itsm.views.portal_workbench import portal_dashboard

    state = TicketStatus.objects.create(key="new", name="新建")
    Ticket.objects.create(sn="PORTAL-1", title="自己的工单", creator="owner", workflow=service.workflow, status=state)
    Ticket.objects.create(sn="PORTAL-2", title="别人的工单", creator="other", workflow=service.workflow, status=state)
    result = data(portal_dashboard(req()))
    assert result["stats"]["total"] == 1
    assert len(result["trend"]) == 14
    assert [item["sn"] for item in result["tickets"]] == ["PORTAL-1"]
    assert data(portal_dashboard(req(permissions=["portal-View"])))["tickets"] == []


def test_restricted_empty_and_managers_are_not_automatically_applicants(service):
    service.visible_users = []
    service.save()
    assert not data(service_portal(req(permissions=["portal-View", "workflow-Edit"])))["services"]
    assert data(service_portal(req(permissions=["portal-View", "workflow-Edit"])))["can_manage"]
    assert not data(service_portal(req()))["can_manage"]
    assert service_favorite(req(), service.id).status_code == 405
    assert service_use(req(), service.id).status_code == 405


def test_inactive_workflow_and_explicit_wrong_service_block_form(service):
    factory_request = req()
    factory_request.GET = {"service_id": str(service.id + 99)}
    assert ticket_form(factory_request, service.workflow.current_version_id).status_code == 404
    service.workflow.is_enabled = False
    service.workflow.save()
    assert not data(service_portal(req()))["services"]
    assert ticket_form(req(), service.workflow.current_version_id).status_code == 403


@pytest.mark.parametrize("background", ["https://example.com/a.png", "data:image/svg+xml;base64,PHN2Zy8+", "data:image/png;base64,invalid"])
def test_reject_unsafe_background(background):
    from apps.itsm.views.portal_workbench import portal_layout

    value = {"title": "门户", "subtitle": "", "background": background, "widgets": []}
    assert portal_layout(req("put", value, permissions=["workflow-Edit"])).status_code == 400


def test_background_image_roundtrip_and_duplicate_widgets():
    import base64
    import io

    from PIL import Image

    from apps.itsm.views.portal_workbench import portal_layout

    content = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(content, format="PNG")
    background = "data:image/png;base64," + base64.b64encode(content.getvalue()).decode()
    value = {"title": "门户", "subtitle": "", "background": background, "widgets": []}
    assert data(portal_layout(req("put", value, permissions=["workflow-Edit"])))["background"] == background
    value["widgets"] = [{"type": "services", "width": 6}] * 2
    assert portal_layout(req("put", value, permissions=["workflow-Edit"])).status_code == 400


def test_acl_validation_rejects_cross_domain_and_catalog_cycles():
    from apps.itsm.models import ServiceCatalog
    from apps.itsm.serializers.service import ServiceCatalogSerializer, ServiceSerializer

    group = HandlerGroup.objects.create(name="外部组", domain="other")
    serializer = ServiceSerializer(data={"name": "服务", "workflow_id": 999, "visible_groups": [group.id]}, context={"domain": "domain.com"})
    assert not serializer.is_valid()
    assert "visible_groups" in serializer.errors
    parent = ServiceCatalog.objects.create(name="父目录")
    child = ServiceCatalog.objects.create(name="子目录", parent=parent)
    serializer = ServiceCatalogSerializer(parent, data={"parent_id": child.id}, partial=True, context={"domain": "domain.com"})
    assert not serializer.is_valid()


def test_finished_timestamp_tracks_completion_and_reopen(service):
    from apps.itsm.models import Ticket, TicketStatus
    from apps.itsm.services.ticket.service import TicketService
    from apps.itsm.views.portal_workbench import portal_dashboard

    state = TicketStatus.objects.create(key="processing", name="处理中")
    TicketStatus.objects.create(key="finished", name="已完成")
    ticket = Ticket.objects.create(sn="PORTAL-FINISH", title="完成时间", creator="owner", workflow=service.workflow, status=state)
    engine = TicketService.__new__(TicketService)
    with patch("apps.itsm.services.triggers.fire_triggers"):
        engine._set_status(ticket, "finished")
    ticket.refresh_from_db()
    assert ticket.finished_at is not None
    assert data(portal_dashboard(req()))["trend"][-1]["finished"] == 1
    engine._set_status(ticket, "processing")
    ticket.refresh_from_db()
    assert ticket.finished_at is None
    assert data(portal_dashboard(req()))["trend"][-1]["finished"] == 0


def test_todo_matches_center_and_announcements_are_scoped(service):
    from apps.itsm.models import Ticket, TicketTask
    from apps.itsm.models.extend import Announcement
    from apps.itsm.views.portal_workbench import portal_dashboard

    ticket = Ticket.objects.create(sn="PORTAL-TODO", title="我的待办", creator="other", workflow=service.workflow, is_test=True)
    TicketTask.objects.create(ticket=ticket, node_id="a", assignee="owner", status="pending")
    TicketTask.objects.create(ticket=ticket, node_id="b", assignee="owner", status="claimed")
    Announcement.objects.create(title="可见公告", content="内容")
    Announcement.objects.create(title="禁用公告", is_enabled=False)
    Announcement.objects.create(title="其他域", domain="other")
    result = data(portal_dashboard(req()))
    assert result["stats"]["todo"] == 1
    assert result["stats"]["total"] == 1
    assert [item["id"] for item in result["todo"]] == [ticket.id]
    assert [item["title"] for item in result["announcements"]] == ["可见公告"]


def test_application_preview_exposes_only_display_fields(service):
    version = service.workflow.current_version
    version.design = {
        "nodes": [
            {"id": "s", "type": "submit", "name": "提单", "secret": "not-public"},
            {"id": "a", "type": "approval", "name": "审批", "assignee": {"users": ["hidden"]}},
        ],
        "edges": [{"from": "s", "to": "a", "condition": "private"}],
    }
    version.save()
    result = data(ticket_form(req(), version.id))
    assert result["workflow_name"] == service.workflow.name
    assert result["creator"] == "owner"
    assert result["nodes"] == [
        {"id": "s", "type": "submit", "name": "提单", "state": "current"},
        {"id": "a", "type": "approval", "name": "审批", "state": "waiting"},
    ]
    assert result["edges"] == [{"from": "s", "to": "a"}]


def test_public_service_lookup_skips_unrelated_group_memberships(service, django_assert_num_queries):
    from apps.itsm.services.service_access import visible_services

    public = Service.objects.create(name="公开", workflow=service.workflow)
    group = HandlerGroup.objects.create(name="其他组", members=["owner"])
    service.visible_groups = [group.pk]
    service.save()
    with django_assert_num_queries(2):
        assert visible_services(req(), service_id=public.pk).get() == public


def test_directory_search_pages_respect_acl_and_catalog_descendants(service):
    from apps.itsm.models import ServiceCatalog

    parent = ServiceCatalog.objects.create(name="基础设施")
    child = ServiceCatalog.objects.create(name="主机", parent=parent)
    for index in range(13):
        Service.objects.create(name=f"主机{index}", workflow=service.workflow, catalog=child, description="Linux")
    service.description = "Linux"
    service.catalog = child
    service.save()
    response = data(
        service_portal(req(payload={"directory": 1, "catalog": parent.pk, "keyword": "linux", "page": 2, "page_size": 10}, user="viewer"))
    )
    assert response["total"] == 13
    assert len(response["items"]) == 3
    assert data(service_portal(req(payload={"service_id": service.pk})))["services"][0]["id"] == service.pk
