import json
from pathlib import Path

import pytest

from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views import api, m2
from apps.system_mgmt.management.commands.init_realm_resource import create_default_roles, create_resource
from apps.system_mgmt.models import App, Menu, Role


@pytest.mark.django_db
def test_initialized_designer_can_edit_drafts_without_running_or_publishing():
    config = json.loads(Path("support-files/system_mgmt/menus/itsm.json").read_text())
    app = App.objects.create(name="itsm", display_name="ITSM")
    for _ in range(2):
        create_resource(app, config["menus"])
        create_default_roles(app, config["roles"])
    role = Role.objects.get(app="itsm", name="designer")
    grants = set(Menu.objects.filter(id__in=role.menu_list).values_list("name", flat=True))
    assert grants == {"workflow-View", "workflow-Add", "workflow-Draft", "form-View", "form-Add", "form-Edit"}

    def call(view, method, payload, *args):
        return view(request(method, payload, "designer", grants), *args)

    def data(response):
        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["result"], body
        return body["data"]

    form_id = data(call(api.forms, "post", {"name": "表单", "key": "test_form"}))["id"]
    workflow_id = data(call(api.workflows, "post", {"name": "流程", "key": "test_flow", "form_id": form_id}))["id"]
    data(call(api.form_detail, "put", {"schema": {"fields": []}}, form_id))
    data(call(api.workflow_design, "post", {"nodes": [{"id": "start"}]}, workflow_id))
    assert data(call(api.workflow_design, "get", {}, workflow_id))["can_publish"] is False
    assert data(call(api.form_detail, "get", {}, form_id))["can_publish"] is False
    for view, args in [(api.publish_form, [form_id]), (api.publish_workflow, [workflow_id]), (m2.statuses, [])]:
        assert call(view, "post", {}, *args).status_code == 403

    grants.add("form-Publish")
    assert data(call(api.form_detail, "get", {}, form_id))["can_publish"] is True
    assert data(call(api.workflow_design, "get", {}, workflow_id))["can_publish"] is False
    grants.add("workflow-Publish")
    assert data(call(api.workflow_design, "get", {}, workflow_id))["can_publish"] is True
