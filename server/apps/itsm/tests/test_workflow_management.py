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
    assert payload["items"][0]["published_version_no"] == 3
    assert payload["can_publish"] is False
    assert enable_version(request(permissions=["workflow-Publish"]), workflow.id, version.id).status_code == 405
    assert enable_version(request("post", permissions=["workflow-View"]), workflow.id, version.id).status_code == 403


def test_global_import_rejects_non_object_without_creating_records():
    assert workflow_import(request("post", [1], permissions=["workflow-Add"])).status_code == 400
    assert Workflow.objects.count() == 0


def test_draft_inherits_selected_published_design_and_repeated_creation_preserves_edits():
    from apps.itsm.views.api import workflow_design

    workflow = Workflow.objects.create(key="vm_draft", name="虚拟机申请")
    schema = {"version": 1, "fields": [{"key": "machines", "type": "table", "children": [{"key": "size", "type": "number"}]}]}
    design = {"nodes": [{"id": "start"}], "edges": [], "form_schema": schema}
    active = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=design, is_published=True)
    workflow.current_version = active
    workflow.save()
    create = {"draft_from_version": active.version_no}
    response = workflow_design(request("put", create, permissions=["workflow-Edit"]), workflow.pk)
    assert response.status_code == 200
    draft = workflow.versions.get(is_published=False)
    assert draft.design == design
    draft.design["form_schema"]["fields"] = []
    draft.save()
    workflow_design(request("put", create, permissions=["workflow-Edit"]), workflow.pk)
    draft.refresh_from_db()
    active.refresh_from_db()
    workflow.refresh_from_db()
    assert draft.design["form_schema"]["fields"] == []
    assert active.design == design and workflow.current_version_id == active.id
    assert workflow.versions.count() == 2


def test_snapshot_only_workflow_recovers_missing_draft_schema_but_keeps_explicit_empty_fields():
    from apps.itsm.views.api import workflow_design

    workflow = Workflow.objects.create(key="old_vm_draft", name="历史草稿")
    schema = {"version": 1, "fields": [{"key": "cpu", "type": "number"}]}
    active = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={"form_schema": schema}, is_published=True)
    workflow.current_version = active
    workflow.save()
    draft = WorkflowVersion.objects.create(workflow=workflow, version_no=2, design={"nodes": [{"id": "edited"}]})
    read = request(permissions=["workflow-Edit"])
    result = json.loads(workflow_design(read, workflow.pk).content)["data"]
    assert result["nodes"] == draft.design["nodes"] and result["form_schema"] == schema
    draft.design["form_schema"] = {"version": 1, "fields": []}
    draft.save()
    assert json.loads(workflow_design(read, workflow.pk).content)["data"]["form_schema"]["fields"] == []


def test_copy_published_version_to_independent_editable_workflow():
    from apps.itsm.views.api import duplicate_workflow_version

    original = Workflow.objects.create(key="published", name="原流程")
    schema = {"fields": [{"key": "cost", "label": "费用", "type": "number"}]}
    version = WorkflowVersion.objects.create(
        workflow=original, version_no=4, is_published=True, design={"nodes": [], "edges": [], "form_schema": schema}
    )
    original.current_version = version
    original.save()
    assert duplicate_workflow_version(request("post", permissions=["workflow-Edit"]), original.pk, 4).status_code == 403
    assert duplicate_workflow_version(request("post", permissions=["workflow-Add"]), original.pk, 4).status_code == 403
    response = duplicate_workflow_version(request("post", permissions=["workflow-Add", "workflow-Edit"]), original.pk, 4)
    assert response.status_code == 200
    clone = Workflow.objects.get(pk=json.loads(response.content)["data"]["id"])
    assert clone.name == "原流程（副本）" and clone.current_version_id is None
    assert clone.form.current_version.schema == schema
    assert clone.versions.get().version_no == 1 and not clone.versions.get().is_published
    original.refresh_from_db()
    assert original.current_version_id == version.id and original.versions.count() == 1
