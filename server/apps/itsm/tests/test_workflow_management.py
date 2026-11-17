"""流程列表导入及版本操作契约。"""
import json

import pytest
from django.urls import resolve

from apps.itsm.models import Workflow, WorkflowVersion
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.api import workflows
from apps.itsm.views.m2 import enable_version, workflow_import

pytestmark = pytest.mark.django_db


def test_global_import_requires_no_existing_workflow():
    assert resolve("/api/v1/itsm/api/workflows/import/").func is workflow_import
    response = workflow_import(request("post", {"key": "demo", "name": "测试", "design": {"nodes": [], "edges": []}}, permissions=["workflow-Add"]))
    assert response.status_code == 200
    created = Workflow.objects.get(pk=json.loads(response.content)["data"]["id"])
    assert created.key.startswith("demo_") and created.current_version_id is None
    assert not created.versions.get().is_published
    assert workflow_import(request("post", {}, permissions=["workflow-View"])).status_code == 403


def test_list_displays_version_number_and_permissions():
    workflow = Workflow.objects.create(key="test", name="测试")
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=3, is_published=True)
    workflow.current_version = version
    workflow.save()
    response = workflows(request(permissions=["workflow-View"]))
    payload = json.loads(response.content)["data"]
    assert payload["items"][0]["current_version_no"] == 3
    assert payload["can_publish"] is False
    assert enable_version(request(permissions=["workflow-Publish"]), workflow.id, version.id).status_code == 405
    assert enable_version(request("post", permissions=["workflow-View"]), workflow.id, version.id).status_code == 403


def test_global_import_rejects_non_object_without_creating_records():
    assert workflow_import(request("post", [1], permissions=["workflow-Add"])).status_code == 400
    assert Workflow.objects.count() == 0
