from unittest.mock import patch

import pytest

from apps.system_mgmt.models import Group
from apps.workflow.models import Workflow, WorkflowExecution, WorkflowVersion
from apps.workflow.openapi_api import openapi_workflow_execute_async, openapi_workflow_list
from apps.workflow.openapi_serializers import WorkflowExecuteAsyncRequestSerializer, WorkflowListRequestSerializer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def teams():
    return Group.objects.create(name="wf-exec-a"), Group.objects.create(name="wf-exec-b")


def _callback_context():
    return {
        "callback_url": "https://example.com/openapi/v1/itsm/openapi/v1/action_components/callback/",
        "callback_token": "tok-wf-async-1",
        "operator": "system",
        "timeout": 3600,
    }


def _create_workflows(own_team_id, other_team_id):
    own = Workflow.objects.create(
        name="ITSM 巡检",
        description="给 ITSM 选择",
        team=[own_team_id],
        definition={"tasks": []},
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(workflow=own, version=1, definition={"tasks": []}, canvas_metadata={})
    foreign = Workflow.objects.create(
        name="外组织流程",
        description="hidden",
        team=[other_team_id],
        definition={"tasks": []},
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(workflow=foreign, version=1, definition={"tasks": []}, canvas_metadata={})
    Workflow.objects.create(
        name="草稿不出现",
        team=[own_team_id],
        definition={"tasks": []},
        current_version=0,
        status=Workflow.Status.DRAFT,
        enabled=False,
    )
    return own, foreign


def test_api_tenant_can_list_own_workflows(teams):
    own_team, other_team = teams
    own, _foreign = _create_workflows(own_team.id, other_team.id)
    result = openapi_workflow_list(page=1, page_size=20, team=[own_team.id])
    names = [item["name"] for item in result["items"]]
    assert result["count"] == 1
    assert names == ["ITSM 巡检"]
    assert result["items"][0]["id"] == str(own.id)


def test_api_tenant_cannot_list_other_org_workflows(teams):
    own_team, other_team = teams
    _create_workflows(own_team.id, other_team.id)
    result = openapi_workflow_list(page=1, page_size=20, team=[other_team.id])
    names = [item["name"] for item in result["items"]]
    assert result["count"] == 1
    assert names == ["外组织流程"]
    assert "ITSM 巡检" not in names


def test_workflow_list_forged_team_is_rejected(teams):
    _own_team, other_team = teams
    serializer = WorkflowListRequestSerializer(data={"page": 1, "page_size": 20, "team": [other_team.id]})
    assert serializer.is_valid() is False
    assert "team" in serializer.errors


def test_api_tenant_can_execute_own_workflow_async(teams):
    own_team, other_team = teams
    own, _foreign = _create_workflows(own_team.id, other_team.id)
    execution = WorkflowExecution(id="11111111-1111-1111-1111-111111111111", workflow=own, workflow_version=1, team=[own_team.id])
    with patch("apps.workflow.openapi_api.SSRFValidator.validate_callback"), patch(
        "apps.workflow.permissions.get_permission_rules",
        return_value={"team": [own_team.id], "instance": []},
    ), patch("apps.workflow.openapi_api.start_execution", return_value=execution) as start:
        result = openapi_workflow_execute_async(
            str(own.id),
            _callback_context(),
            team=[own_team.id],
            user_info={"user": "alice", "domain": "a.test.com"},
        )

    assert result["accepted"] is True
    assert result["execution_id"] == str(execution.id)
    assert start.call_args.kwargs["async_callback_context"]["callback_token"] == "tok-wf-async-1"
    assert start.call_args.kwargs["async_callback_key"]


def test_api_tenant_cannot_replay_other_org_callback_token(teams):
    own_team, other_team = teams
    own, foreign = _create_workflows(own_team.id, other_team.id)
    stolen_key = "deadbeef" * 8
    WorkflowExecution.objects.create(
        workflow=foreign,
        workflow_version=1,
        team=[other_team.id],
        async_callback_key=stolen_key,
        started_by="bob",
        domain="b.test.com",
        definition_snapshot={"tasks": []},
        input={},
    )
    with patch("apps.workflow.openapi_api.SSRFValidator.validate_callback"), patch(
        "apps.workflow.permissions.get_permission_rules",
        return_value={"team": [own_team.id], "instance": []},
    ), patch("apps.workflow.openapi_api.hashlib.sha256") as sha256, patch("apps.workflow.openapi_api.start_execution") as start:
        sha256.return_value.hexdigest.return_value = stolen_key
        result = openapi_workflow_execute_async(
            str(own.id),
            _callback_context(),
            team=[own_team.id],
            user_info={"user": "alice", "domain": "a.test.com"},
        )

    assert result == {"result": False, "message": "流程不存在或不属于调用方组织"}
    start.assert_not_called()


def test_api_tenant_cannot_execute_other_org_workflow(teams):
    own_team, other_team = teams
    _own, foreign = _create_workflows(own_team.id, other_team.id)
    with patch("apps.workflow.openapi_api.SSRFValidator.validate_callback"), patch("apps.workflow.openapi_api.start_execution") as start:
        result = openapi_workflow_execute_async(
            str(foreign.id),
            _callback_context(),
            team=[own_team.id],
            user_info={"user": "alice", "domain": "a.test.com"},
        )

    assert result == {"result": False, "message": "流程不存在或不属于调用方组织"}
    start.assert_not_called()


def test_workflow_execute_async_forged_team_is_rejected(teams):
    _own_team, other_team = teams
    serializer = WorkflowExecuteAsyncRequestSerializer(
        data={
            "workflow_id": "1",
            "callback_context": _callback_context(),
            "team": [other_team.id],
        }
    )
    assert serializer.is_valid() is False
    assert "team" in serializer.errors


def test_openapi_list_requires_active_team():
    denied = openapi_workflow_list(team=[])
    assert denied["result"] is False


def test_openapi_execute_rejects_missing_operate(teams):
    own_team, other_team = teams
    own, _foreign = _create_workflows(own_team.id, other_team.id)
    with patch("apps.workflow.openapi_api.SSRFValidator.validate_callback"), patch(
        "apps.workflow.permissions.get_permission_rules",
        return_value={"team": [], "instance": [{"id": own.id, "permission": ["View"]}]},
    ), patch("apps.workflow.openapi_api.start_execution") as start:
        denied = openapi_workflow_execute_async(
            str(own.id),
            _callback_context(),
            team=[own_team.id],
            user_info={"user": "alice", "domain": "a.test.com"},
        )
    assert denied == {"result": False, "message": "缺少流程实例操作权限"}
    start.assert_not_called()
