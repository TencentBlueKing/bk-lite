import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import Workflow, WorkflowExecution
from apps.workflow_orchestration.views import WorkflowExecutionViewSet, WorkflowViewSet


@pytest.fixture
def scoped_user(db):
    user = get_user_model().objects.create(username="workflow-user", domain="example.com")
    user.group_list = [{"id": 7, "name": "Current"}]
    user.group_tree = []
    user.permission = {
        "workflow-orchestration": {
            "workflow-View",
            "workflow-Edit",
            "workflow-Execute",
        }
    }
    return user


def request(factory, method, path, user, data=None):
    value = getattr(factory, method)(path, data or {}, format="json")
    value.COOKIES["current_team"] = "7"
    force_authenticate(value, user=user)
    return value


@pytest.mark.django_db
def test_workflow_list_is_filtered_by_instance_data_rules_and_returns_permission(scoped_user, mocker):
    allowed = Workflow.objects.create(name="allowed", team=[7], definition={})
    Workflow.objects.create(name="denied", team=[7], definition={})
    mocker.patch(
        "apps.workflow_orchestration.permissions.get_permission_rules",
        return_value={"team": [], "instance": [{"id": allowed.id, "permission": ["View"]}]},
    )

    response = WorkflowViewSet.as_view({"get": "list"})(request(APIRequestFactory(), "get", "/workflows/", scoped_user))

    assert response.status_code == 200
    assert [item["id"] for item in response.data["items"]] == [allowed.id]
    assert response.data["items"][0]["permission"] == ["View"]


@pytest.mark.django_db
def test_workflow_write_requires_instance_operate_permission(scoped_user, mocker):
    workflow = Workflow.objects.create(name="read-only", team=[7], definition={})
    rules = mocker.patch(
        "apps.workflow_orchestration.permissions.get_permission_rules",
        return_value={"team": [], "instance": [{"id": workflow.id, "permission": ["View"]}]},
    )
    update = WorkflowViewSet.as_view({"patch": "partial_update"})

    denied = update(
        request(APIRequestFactory(), "patch", f"/workflows/{workflow.id}/", scoped_user, {"name": "changed"}),
        pk=workflow.id,
    )

    assert denied.status_code == 404
    workflow.refresh_from_db()
    assert workflow.name == "read-only"

    rules.return_value = {"team": [], "instance": [{"id": workflow.id, "permission": ["View", "Operate"]}]}
    allowed = update(
        request(APIRequestFactory(), "patch", f"/workflows/{workflow.id}/", scoped_user, {"name": "changed"}),
        pk=workflow.id,
    )

    assert allowed.status_code == 200
    assert allowed.data["permission"] == ["View", "Operate"]
    workflow.refresh_from_db()
    assert workflow.name == "changed"


@pytest.mark.django_db
def test_execution_visibility_inherits_workflow_data_permission(scoped_user, mocker):
    allowed_workflow = Workflow.objects.create(name="allowed", team=[7], definition={})
    denied_workflow = Workflow.objects.create(name="denied", team=[7], definition={})
    allowed_execution = WorkflowExecution.objects.create(workflow=allowed_workflow, workflow_version=1, team=[7])
    WorkflowExecution.objects.create(workflow=denied_workflow, workflow_version=1, team=[7])
    mocker.patch(
        "apps.workflow_orchestration.permissions.get_permission_rules",
        return_value={"team": [], "instance": [{"id": allowed_workflow.id, "permission": ["View"]}]},
    )

    response = WorkflowExecutionViewSet.as_view({"get": "list"})(request(APIRequestFactory(), "get", "/executions/", scoped_user))

    assert response.status_code == 200
    assert [item["id"] for item in response.data["items"]] == [str(allowed_execution.id)]
    assert response.data["items"][0]["permission"] == ["View"]
