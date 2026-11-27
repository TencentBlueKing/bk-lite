import json
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.itsm.models import Service, TicketFormTemplate, Workflow, WorkflowVersion
from apps.itsm.views.services import service_form_templates

pytestmark = pytest.mark.django_db


def request(method="get", payload=None, *, username="owner", domain="domain.com"):
    factory = RequestFactory()
    if method == "get":
        req = factory.get("/", payload or {})
    elif method == "delete":
        req = factory.delete(f"/?id={(payload or {}).get('id', '')}")
    else:
        req = factory.post("/", data=json.dumps(payload or {}), content_type="application/json")
    req.user = SimpleNamespace(username=username, domain=domain, is_superuser=False, permission={"itsm": {"ticket-Add"}})
    return req


def result(response):
    return json.loads(response.content)["data"]


@pytest.fixture
def service():
    workflow = Workflow.objects.create(name="资源申请", key="resource")
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        is_published=True,
        design={
            "nodes": [{"id": "submit", "type": "submit", "field_perm": {"secret": "read"}}],
            "form_schema": {
                "fields": [
                    {"key": "title", "type": "input"},
                    {"key": "secret", "type": "input"},
                    {"key": "dynamic", "type": "select", "fetch": {"source": "integration"}},
                    {
                        "key": "machines",
                        "type": "table",
                        "children": [
                            {"key": "name", "type": "input"},
                            {"key": "hidden", "type": "input", "state": "hidden"},
                            {"key": "option", "type": "select", "fetch": {"source": "integration"}},
                        ],
                    },
                ]
            },
        },
    )
    workflow.current_version = version
    workflow.save(update_fields=["current_version"])
    return Service.objects.create(name="资源服务", workflow=workflow)


def test_save_multiple_partial_templates_scoped_to_owner_and_workflow(service):
    values = {
        "title": "一批资源",
        "secret": "private",
        "dynamic": "stale",
        "_field_receipts": {"dynamic": ["old"]},
        "machines": [{"name": "one", "hidden": "no", "option": "stale", "_itsm_row_ref": "old"}],
        "obsolete": "removed",
    }
    first = result(service_form_templates(request("post", {"name": "常用", "form_data": values}), service.id))
    second = result(service_form_templates(request("post", {"name": "另一份", "form_data": {"title": "第二份"}}), service.id))
    assert first["form_data"] == {"title": "一批资源", "machines": [{"name": "one"}]}
    assert first["id"] != second["id"]
    assert len(result(service_form_templates(request(), service.id))["items"]) == 2
    sibling = Service.objects.create(name="同流程的另一服务", workflow=service.workflow)
    assert len(result(service_form_templates(request(), sibling.id))["items"]) == 2
    assert result(service_form_templates(request(username="other"), service.id))["items"] == []
    assert TicketFormTemplate.objects.count() == 2


def test_reuse_after_schema_changes_and_restrict_delete(service):
    saved = result(service_form_templates(request("post", {"name": "常用", "form_data": {"title": "原标题"}}), service.id))
    version = service.workflow.current_version
    version.design["form_schema"]["fields"] = [{"key": "new_field", "type": "input"}]
    version.save(update_fields=["design"])
    listed = result(service_form_templates(request(), service.id))["items"][0]
    assert listed["form_data"] == {}
    assert listed["changed"] is True
    assert service_form_templates(request("delete", {"id": saved["id"]}, username="other"), service.id).status_code == 404
    assert service_form_templates(request("delete", {"id": saved["id"]}), service.id).status_code == 200


def test_hidden_or_disabled_service_cannot_read_templates(service):
    service.visibility = "restricted"
    service.visible_users = ["owner"]
    service.save(update_fields=["visibility", "visible_users"])
    assert service_form_templates(request(username="other"), service.id).status_code == 404
    service.is_enabled = False
    service.save(update_fields=["is_enabled"])
    assert service_form_templates(request(), service.id).status_code == 404
