import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import AtomDefinition, Workflow, WorkflowExecution, WorkflowVersion
from apps.workflow_orchestration.services.atom_registry import available_atom_catalog
from apps.workflow_orchestration.services.atoms import ATOM_CATALOG
from apps.workflow_orchestration.views import AtomDefinitionViewSet, WorkflowExecutionViewSet, WorkflowViewSet


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create(username="workflow-mvp-admin", domain="example.com", is_superuser=True)


def _request(factory, method, path, user, data=None):
    request = getattr(factory, method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def test_execution_exposes_only_the_confirmed_mvp_states():
    assert set(WorkflowExecution.Status.values) == {
        "QUEUED",
        "RUNNING",
        "WAITING_APPROVAL",
        "TERMINATING",
        "SUCCEEDED",
        "FAILED",
        "TIMED_OUT",
        "TERMINATED",
    }


@pytest.mark.django_db
def test_blank_workflow_starts_as_an_empty_editable_draft(superuser):
    response = WorkflowViewSet.as_view({"post": "create"})(
        _request(
            APIRequestFactory(),
            "post",
            "/workflows/",
            superuser,
            {"name": "空白流程", "starter": "blank"},
        )
    )

    assert response.status_code == 201
    assert response.data["definition"]["tasks"] == []
    assert response.data["canvas_metadata"]["trigger_nodes"] == []
    assert response.data["canvas_metadata"]["return_nodes"] == []
    assert response.data["canvas_metadata"]["edges"] == []


@pytest.mark.django_db
def test_empty_draft_must_add_nodes_before_validation(superuser):
    factory = APIRequestFactory()
    created = WorkflowViewSet.as_view({"post": "create"})(_request(factory, "post", "/workflows/", superuser, {"name": "待编排流程", "starter": "blank"}))

    response = WorkflowViewSet.as_view({"post": "validate"})(
        _request(factory, "post", f"/workflows/{created.data['id']}/validate/", superuser),
        pk=created.data["id"],
    )

    assert response.status_code == 400
    assert response.data["valid"] is False
    assert response.data["issues"] == [{"message": "流程必须包含 1 到 10 个触发节点", "code": "workflow_invalid"}]


@pytest.mark.django_db
def test_saving_a_draft_uses_revision_lock_and_overwrites_the_single_draft(superuser):
    workflow = Workflow.objects.create(name="巡检", team=[7], definition={"tasks": []})
    view = WorkflowViewSet.as_view({"patch": "partial_update"})
    factory = APIRequestFactory()

    saved = view(
        _request(factory, "patch", f"/workflows/{workflow.id}/", superuser, {"description": "第一次", "draft_revision": 0}),
        pk=workflow.id,
    )
    stale = view(
        _request(factory, "patch", f"/workflows/{workflow.id}/", superuser, {"description": "过期覆盖", "draft_revision": 0}),
        pk=workflow.id,
    )

    assert saved.status_code == 200
    assert saved.data["draft_revision"] == 1
    assert stale.status_code == 409
    workflow.refresh_from_db()
    assert workflow.description == "第一次"
    assert workflow.draft_revision == 1


@pytest.mark.django_db
def test_enable_and_disable_change_runtime_availability_without_creating_a_version(superuser, mocker):
    definition = {
        "name": "published",
        "version": 1,
        "schemaVersion": 2,
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": "notify",
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "body": "通知",
                },
            }
        ],
    }
    workflow = Workflow.objects.create(
        name="巡检",
        team=[7],
        status=Workflow.Status.PUBLISHED,
        current_version=1,
        definition=definition,
        enabled=False,
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition=definition, created_by="workflow-mvp-admin")
    mocker.patch(
        "apps.workflow_orchestration.views.available_atom_catalog",
        return_value={"bklite_notification": {"key": "bklite_notification", "enabled": True, "input_schema": {"type": "object"}}},
    )
    view = WorkflowViewSet.as_view({"post": "set_enabled"})

    response = view(
        _request(APIRequestFactory(), "post", f"/workflows/{workflow.id}/enabled/", superuser, {"enabled": True}),
        pk=workflow.id,
    )

    assert response.status_code == 200
    assert response.data["enabled"] is True
    workflow.refresh_from_db()
    assert workflow.enabled is True
    assert workflow.current_version == 1
    assert WorkflowVersion.objects.filter(workflow=workflow).count() == 1


@pytest.mark.django_db
def test_atom_catalog_rejects_online_creation(superuser):
    response = AtomDefinitionViewSet.as_view({"post": "create"})(
        _request(
            APIRequestFactory(),
            "post",
            "/atoms/",
            superuser,
            {"key": "custom.forbidden", "name": "不应创建", "category": "动作"},
        )
    )

    assert response.status_code == 405
    assert AtomDefinition.objects.count() == 0


@pytest.mark.django_db
def test_research_atom_is_available_without_organization_enablement():
    AtomDefinition.objects.create(
        key="custom.health_check",
        name="健康巡检",
        category="主机巡检",
        description="研发包原子",
        driver="WORKER",
        built_in=False,
        team=[],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        source_type=AtomDefinition.SourceType.PACKAGE,
    )

    assert "custom.health_check" in available_atom_catalog(7)
    assert "custom.health_check" in available_atom_catalog(8)
    assert not hasattr(AtomDefinitionViewSet, "set_status")


def test_execution_pause_and_resume_are_not_public_mvp_actions():
    assert not hasattr(WorkflowExecutionViewSet, "pause")
    assert not hasattr(WorkflowExecutionViewSet, "resume")


def test_public_mvp_catalog_excludes_arbitrary_http_and_includes_approved_opspilot_atoms():
    assert "bklite_http" not in ATOM_CATALOG
    assert {
        "bklite_agent",
        "bklite_intent_classification",
        "bklite_memory_read",
        "bklite_memory_write",
    }.issubset(ATOM_CATALOG)
