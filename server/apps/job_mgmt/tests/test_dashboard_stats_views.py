"""Dashboard 聚合接口视图测试：stats / job_type_distribution / execution_status_distribution。

许可中间件由本目录 conftest 的 ``_disable_license_guard`` 关闭，故可用 api_client 直打。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution, Playbook, ScheduledTask, Script, Target

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

STATS_URL = "/api/v1/job_mgmt/api/dashboard/stats/"
JOB_TYPE_URL = "/api/v1/job_mgmt/api/dashboard/job_type_distribution/"
STATUS_URL = "/api/v1/job_mgmt/api/dashboard/execution_status_distribution/"


def _make(status, job_type=JobType.SCRIPT):
    return JobExecution.objects.create(name="e", job_type=job_type, status=status, team=[1])


def _find(items, key_field, value):
    return next((item for item in items if item[key_field] == value), None)


class TestDashboardStats:
    def test_stats_aggregates_assets_and_executions(self, api_client):
        Script.objects.create(name="s", content="echo", team=[1])
        Playbook.objects.create(name="p", version="v1.0.0", team=[1])
        Target.objects.create(name="h1", ip="10.0.0.1", os_type="linux", team=[1])
        ScheduledTask.objects.create(name="c1", job_type=JobType.SCRIPT, is_enabled=True)
        ScheduledTask.objects.create(name="c2", job_type=JobType.SCRIPT, is_enabled=False)
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.FAILED)
        _make(ExecutionStatus.RUNNING)
        _make(ExecutionStatus.PENDING)

        resp = api_client.get(STATS_URL)

        assert resp.status_code == 200
        data = resp.data
        assert data["script_total"] == 1
        assert data["playbook_total"] == 1
        assert data["target_total"] == 1
        assert data["scheduled_task_total"] == 2
        assert data["scheduled_task_enabled"] == 1
        assert data["execution_total"] == 5
        assert data["execution_success"] == 2
        assert data["execution_failed"] == 1
        assert data["execution_running"] == 1
        assert data["execution_pending"] == 1

    def test_stats_empty_returns_zeros(self, api_client):
        resp = api_client.get(STATS_URL)
        assert resp.status_code == 200
        for key in (
            "target_total",
            "script_total",
            "playbook_total",
            "execution_total",
            "execution_success",
            "execution_failed",
            "execution_running",
            "execution_pending",
            "scheduled_task_total",
            "scheduled_task_enabled",
            "avg_duration_seconds",
        ):
            assert resp.data[key] == 0

    def test_stats_avg_duration_seconds(self, api_client):
        execution = _make(ExecutionStatus.SUCCESS)
        started = timezone.now()
        JobExecution.objects.filter(id=execution.id).update(started_at=started, finished_at=started + timedelta(seconds=10))

        resp = api_client.get(STATS_URL)

        assert resp.status_code == 200
        assert resp.data["avg_duration_seconds"] == 10.0


class TestJobTypeDistribution:
    def test_distribution_counts_by_type_desc(self, api_client):
        _make(ExecutionStatus.SUCCESS, job_type=JobType.SCRIPT)
        _make(ExecutionStatus.FAILED, job_type=JobType.SCRIPT)
        _make(ExecutionStatus.SUCCESS, job_type=JobType.FILE_DISTRIBUTION)

        resp = api_client.get(JOB_TYPE_URL)

        assert resp.status_code == 200
        script = _find(resp.data, "job_type", JobType.SCRIPT)
        file_dist = _find(resp.data, "job_type", JobType.FILE_DISTRIBUTION)
        assert script["count"] == 2
        assert script["job_type_display"]
        assert file_dist["count"] == 1
        assert resp.data[0]["count"] >= resp.data[-1]["count"]

    def test_distribution_empty(self, api_client):
        resp = api_client.get(JOB_TYPE_URL)
        assert resp.status_code == 200
        assert resp.data == []


class TestExecutionStatusDistribution:
    def test_distribution_counts_by_status(self, api_client):
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.FAILED)

        resp = api_client.get(STATUS_URL)

        assert resp.status_code == 200
        success = _find(resp.data, "status", ExecutionStatus.SUCCESS)
        failed = _find(resp.data, "status", ExecutionStatus.FAILED)
        assert success["count"] == 2
        assert success["status_display"]
        assert failed["count"] == 1

    def test_distribution_empty(self, api_client):
        resp = api_client.get(STATUS_URL)
        assert resp.status_code == 200
        assert resp.data == []
