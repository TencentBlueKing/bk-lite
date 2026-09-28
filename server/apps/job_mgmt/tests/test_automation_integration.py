import pytest

from apps.job_mgmt import nats_api
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution, Target

ACTOR = {"username": "operator", "domain": "example.com", "authorized_team_ids": [7]}


@pytest.mark.django_db
def test_automation_target_list_is_team_scoped_and_credential_free():
    allowed = Target.objects.create(
        name="allowed",
        ip="10.0.0.1",
        os_type="linux",
        team=[7],
        ssh_user="secret-user",
        ssh_password="secret-password",
    )
    Target.objects.create(name="other-team", ip="10.0.0.2", os_type="windows", team=[8])

    response = nats_api.list_automation_targets_local({}, ACTOR)

    assert response["result"] is True
    assert response["data"] == {
        "count": 1,
        "items": [
            {
                "target_id": allowed.id,
                "name": "allowed",
                "ip": "10.0.0.1",
                "os_type": "linux",
                "cloud_region_id": None,
            }
        ],
    }
    assert "secret-user" not in str(response)
    assert "secret-password" not in str(response)


@pytest.mark.django_db
def test_automation_target_list_rejects_cross_team_ids():
    other = Target.objects.create(name="other-team", ip="10.0.0.2", os_type="windows", team=[8])

    response = nats_api.list_automation_targets_local({"target_ids": [other.id]}, ACTOR)

    assert response == {"result": True, "data": {"count": 0, "items": []}}


def test_automation_integration_requires_trusted_actor_context():
    response = nats_api.list_automation_targets_local({}, {"authorized_team_ids": [7]})

    assert response == {"result": False, "message": "缺少可信执行上下文"}


@pytest.mark.django_db
def test_automation_script_validates_target_scope_and_records_actor(mocker):
    allowed = Target.objects.create(name="allowed", ip="10.0.0.1", os_type="linux", team=[7])
    denied = Target.objects.create(name="denied", ip="10.0.0.2", os_type="linux", team=[8])
    mocker.patch.object(nats_api, "dispatch_celery_task", return_value=True)
    payload = {
        "name": "health inspection",
        "target_source": "manual",
        "target_list": [{"target_id": allowed.id, "name": allowed.name, "ip": str(allowed.ip)}],
        "script_type": "shell",
        "script_content": "echo ok",
        "team": [7],
        "callback_type": "nats",
        "callback_subject": "bklite.workflow_orchestration.job_result",
    }

    accepted = nats_api.execute_automation_script_local(payload, ACTOR)
    denied_response = nats_api.execute_automation_script_local(
        {**payload, "target_list": [{"target_id": denied.id}], "team": [8]},
        ACTOR,
    )

    assert accepted["result"] is True
    execution = JobExecution.objects.get(id=accepted["data"]["task_id"])
    assert execution.executor_user == "operator"
    assert execution.domain == "example.com"
    assert denied_response == {"result": False, "message": "无权在目标组织执行作业"}


@pytest.mark.django_db
def test_automation_execution_queries_hide_cross_team_jobs():
    allowed = JobExecution.objects.create(name="allowed", job_type=JobType.SCRIPT, status=ExecutionStatus.SUCCESS, team=[7])
    denied = JobExecution.objects.create(name="denied", job_type=JobType.SCRIPT, status=ExecutionStatus.SUCCESS, team=[8])

    statuses = nats_api.get_automation_execution_statuses_local({"task_ids": [allowed.id, denied.id]}, ACTOR)
    detail = nats_api.get_automation_execution_detail_local({"task_id": denied.id}, ACTOR)

    assert [item["status"] for item in statuses["data"]] == [ExecutionStatus.SUCCESS, "not_found"]
    assert detail == {"result": False, "message": "任务不存在或无权访问"}
