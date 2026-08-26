"""统一 OpenAPI 网关：作业脚本执行、状态与详情双租户契约。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution, Target
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

EXECUTE_URL = "/openapi/v1/job-mgmt/script-execute"
STATUS_URL = "/openapi/v1/job-mgmt/job-status"
DETAIL_URL = "/openapi/v1/job-mgmt/job-detail"


@pytest.fixture
def tenant():
    team = Group.objects.create(name="job-exec-a")
    other_team = Group.objects.create(name="job-exec-b")
    user = User.objects.create(username="job-exec-a", domain="a.test.com")
    SystemUser.objects.create(username=user.username, domain=user.domain, group_list=[team.id])
    token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        api_secret=UserAPISecret.hash_api_secret(token),
        team=team.id,
    )
    other_user = User.objects.create(username="job-exec-b", domain="b.test.com")
    SystemUser.objects.create(
        username=other_user.username,
        domain=other_user.domain,
        group_list=[other_team.id],
    )
    other_token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=other_user.username,
        domain=other_user.domain,
        api_secret=UserAPISecret.hash_api_secret(other_token),
        team=other_team.id,
    )
    target = Target.objects.create(name="web-01", ip="10.0.0.1", team=[team.id])
    other_target = Target.objects.create(name="db-01", ip="10.0.0.2", team=[other_team.id])
    return SimpleNamespace(
        team=team,
        other_team=other_team,
        user=user,
        token=token,
        other_user=other_user,
        other_token=other_token,
        target=target,
        other_target=other_target,
    )


def _auth(tenant):
    return {"HTTP_AUTHORIZATION": f"Bearer {tenant.token}"}


def _other_auth(tenant):
    return {"HTTP_AUTHORIZATION": f"Bearer {tenant.other_token}"}


def _execute_body(tenant, **overrides):
    payload = {
        "name": "补丁安装",
        "target_source": "manual",
        "target_list": [{"target_id": tenant.target.id, "name": tenant.target.name, "ip": tenant.target.ip}],
        "script_type": "shell",
        "script_content": "echo hello",
    }
    payload.update(overrides)
    return payload


def test_api_tenant_can_execute_script_on_own_target(tenant):
    with patch("apps.job_mgmt.nats_api.DangerousChecker.check_command") as mock_check, patch(
        "apps.job_mgmt.nats_api.execute_script_task.delay"
    ) as mock_delay:
        mock_check.return_value = MagicMock(can_execute=True, forbidden=[])
        mock_delay.return_value.id = "celery-1"
        response = APIClient().post(EXECUTE_URL, _execute_body(tenant), format="json", **_auth(tenant))

    assert response.status_code == 200, response.json()
    execution = JobExecution.objects.get(id=response.json()["data"]["task_id"])
    assert execution.team == [tenant.team.id]
    assert execution.created_by == tenant.user.username[:32]
    assert execution.executor_user == tenant.user.username
    assert execution.script_content == "echo hello"
    mock_delay.assert_called_once()


def test_api_tenant_cannot_execute_script_on_other_tenant_target(tenant):
    with patch("apps.job_mgmt.nats_api.execute_script_task.delay") as mock_delay:
        response = APIClient().post(
            EXECUTE_URL,
            _execute_body(
                tenant,
                target_list=[{"target_id": tenant.other_target.id, "name": tenant.other_target.name, "ip": tenant.other_target.ip}],
            ),
            format="json",
            **_auth(tenant),
        )

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"
    assert not JobExecution.objects.filter(name="补丁安装").exists()
    mock_delay.assert_not_called()


def test_script_execute_scope_reject_logs_stable_template(tenant):
    with patch("apps.job_mgmt.openapi_api.logger.warning") as mock_log, patch("apps.job_mgmt.nats_api.execute_script_task.delay") as mock_delay:
        response = APIClient().post(
            EXECUTE_URL,
            _execute_body(
                tenant,
                target_list=[{"target_id": tenant.other_target.id, "name": tenant.other_target.name, "ip": tenant.other_target.ip}],
            ),
            format="json",
            **_auth(tenant),
        )

    assert response.status_code == 403
    mock_delay.assert_not_called()
    template, user, domain, team_id, target_source, target_count, target_ids, reason = mock_log.call_args.args
    assert "%s" in template
    assert "user=%s" in template
    assert user == tenant.user.username
    assert domain == tenant.user.domain
    assert team_id == tenant.team.id
    assert target_source == "manual"
    assert target_count == 1
    assert target_ids == [tenant.other_target.id]
    formatted = template % (user, domain, team_id, target_source, target_count, target_ids, reason)
    assert tenant.user.username in formatted
    assert str(tenant.other_target.id) in formatted
    assert "无权访问该组织" in reason


def test_script_execute_forged_team_is_rejected(tenant):
    with patch("apps.job_mgmt.nats_api.execute_script_task.delay") as mock_delay:
        response = APIClient().post(
            EXECUTE_URL,
            _execute_body(tenant, team=[tenant.other_team.id]),
            format="json",
            **_auth(tenant),
        )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    mock_delay.assert_not_called()


def test_api_tenant_can_read_own_job_status(tenant):
    own = JobExecution.objects.create(
        name="own",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.RUNNING,
        team=[tenant.team.id],
        total_count=2,
        success_count=1,
    )
    foreign = JobExecution.objects.create(
        name="foreign",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.SUCCESS,
        team=[tenant.other_team.id],
    )
    response = APIClient().post(
        STATUS_URL,
        {"task_ids": [own.id, foreign.id, 99999]},
        format="json",
        **_auth(tenant),
    )

    assert response.status_code == 200, response.json()
    by_id = {item["task_id"]: item for item in response.json()["data"]}
    assert by_id[own.id]["status"] == ExecutionStatus.RUNNING
    assert by_id[foreign.id] == {"task_id": foreign.id, "status": "not_found"}
    assert by_id[99999] == {"task_id": 99999, "status": "not_found"}


def test_api_tenant_cannot_read_other_org_job_status(tenant):
    own = JobExecution.objects.create(
        name="own",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.RUNNING,
        team=[tenant.team.id],
    )
    response = APIClient().post(
        STATUS_URL,
        {"task_ids": [own.id]},
        format="json",
        **_other_auth(tenant),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"] == [{"task_id": own.id, "status": "not_found"}]


def test_job_status_forged_team_is_rejected(tenant):
    response = APIClient().post(
        STATUS_URL,
        {"task_ids": [1], "team": [tenant.other_team.id]},
        format="json",
        **_auth(tenant),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_read_own_job_detail(tenant):
    own = JobExecution.objects.create(
        name="own-detail",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.SUCCESS,
        team=[tenant.team.id],
        script_content="echo secret",
        execution_results=[{"stdout": "ok"}],
    )
    response = APIClient().get(DETAIL_URL, {"task_id": own.id}, **_auth(tenant))

    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["task_id"] == own.id
    assert data["script_content"] == "echo secret"
    assert data["detail_limited"] is False


def test_api_tenant_cannot_read_other_org_job_detail(tenant):
    own = JobExecution.objects.create(
        name="hidden-detail",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.SUCCESS,
        team=[tenant.team.id],
        script_content="echo secret",
    )
    response = APIClient().get(DETAIL_URL, {"task_id": own.id}, **_other_auth(tenant))

    assert response.status_code == 400
    body = response.json()
    assert body["result"] is False
    assert body["code"] == "BUSINESS_REJECTED"
    assert body["message"] == "任务不存在"
    assert "script_content" not in (body.get("data") or {})


def test_job_detail_forged_team_is_rejected(tenant):
    response = APIClient().get(
        DETAIL_URL,
        {"task_id": 1, "team": tenant.other_team.id},
        **_auth(tenant),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
