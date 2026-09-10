from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution, Playbook, Script
from apps.job_mgmt.nats_api import get_job_usage_statistics

pytestmark = pytest.mark.django_db


def _user_info(team=1):
    return {"team": team, "include_children": False, "is_superuser": True}


def test_job_usage_statistics_scopes_to_selected_org_even_for_superuser():
    Script.objects.create(name="s1", content="echo", script_type="shell", team=[1])
    Script.objects.create(name="s2", content="echo", script_type="shell", team=[2])
    Playbook.objects.create(name="p1", team=[1])
    Playbook.objects.create(name="p2", team=[2])
    start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    end = start + timedelta(days=1)
    success = JobExecution.objects.create(name="ok", job_type=JobType.SCRIPT, status=ExecutionStatus.SUCCESS, team=[1])
    failed = JobExecution.objects.create(name="fail", job_type=JobType.SCRIPT, status=ExecutionStatus.FAILED, team=[1])
    other = JobExecution.objects.create(name="other", job_type=JobType.SCRIPT, status=ExecutionStatus.SUCCESS, team=[2])
    JobExecution.objects.filter(pk=success.pk).update(created_at=start + timedelta(hours=1))
    JobExecution.objects.filter(pk=failed.pk).update(created_at=start + timedelta(hours=1))
    JobExecution.objects.filter(pk=other.pk).update(created_at=start + timedelta(hours=1))

    result = get_job_usage_statistics(
        user_info=_user_info(),
        time=[start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")],
    )

    assert result["result"] is True
    assert result["data"]["job_count"] == 1
    assert result["data"]["template_count"] == 1
    assert result["data"]["execution_count"] == 2
    assert result["data"]["success_count"] == 1
    assert result["data"]["execution_success_rate"] == 50.0


def test_job_usage_statistics_forged_org_outside_group_tree_is_zero():
    Script.objects.create(name="other", content="echo", script_type="shell", team=[2])
    Playbook.objects.create(name="other-pb", team=[2])
    start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    end = start + timedelta(days=1)
    execution = JobExecution.objects.create(
        name="other-run",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.SUCCESS,
        team=[2],
    )
    JobExecution.objects.filter(pk=execution.pk).update(created_at=start + timedelta(hours=1))

    result = get_job_usage_statistics(
        user_info={
            "team": 2,
            "include_children": False,
            "is_superuser": True,
            "group_tree": [{"id": 1, "subGroups": []}],
        },
        time=[start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")],
    )

    assert result["result"] is True
    assert result["data"] == {
        "job_count": 0,
        "template_count": 0,
        "execution_count": 0,
        "success_count": 0,
        "execution_success_rate": 0,
    }
