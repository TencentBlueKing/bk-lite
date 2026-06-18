"""Dashboard 视图测试（trend / success_rate_compare）"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

TREND_URL = "/api/v1/job_mgmt/api/dashboard/trend/"
RATE_URL = "/api/v1/job_mgmt/api/dashboard/success_rate_compare/"


def _make(status, created_offset_days=0):
    e = JobExecution.objects.create(name="e", job_type=JobType.SCRIPT, status=status, team=[1])
    if created_offset_days:
        JobExecution.objects.filter(id=e.id).update(created_at=timezone.now() - timedelta(days=created_offset_days))
    return e


class TestDashboardTrend:
    def test_trend_returns_full_date_series(self, api_client):
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.FAILED)
        resp = api_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        assert len(resp.data) == 7  # 补齐完整 7 天序列

    def test_trend_caps_days_at_30(self, api_client):
        resp = api_client.get(TREND_URL + "?days=100")
        assert resp.status_code == 200
        assert len(resp.data) == 30

    def test_trend_includes_cancelled_count(self, api_client):
        _make(ExecutionStatus.CANCELLED)
        resp = api_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        assert "cancelled_count" in resp.data[0]
        assert resp.data[-1]["cancelled_count"] == 1  # 今日（序列末位）含 1 条已取消

    def test_trend_includes_daily_avg_duration(self, api_client):
        execution = _make(ExecutionStatus.SUCCESS)
        started = timezone.now()
        JobExecution.objects.filter(id=execution.id).update(started_at=started, finished_at=started + timedelta(seconds=10))
        resp = api_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        assert "avg_duration_seconds" in resp.data[0]
        assert resp.data[-1]["avg_duration_seconds"] == 10.0  # 今日平均时长 10s


class TestDashboardSuccessRateCompare:
    def test_rate_aggregates_current_period(self, api_client):
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.FAILED)
        resp = api_client.get(RATE_URL + "?days=7")
        assert resp.status_code == 200
        cur = resp.data["current_period"]
        assert cur["execution_total"] == 3
        assert cur["success_count"] == 2
        assert cur["failed_count"] == 1
        assert cur["success_rate"] == round(2 / 3 * 100, 2)

    def test_rate_invalid_days_falls_back_to_7(self, api_client):
        resp = api_client.get(RATE_URL + "?days=999")
        assert resp.status_code == 200

    def test_rate_handles_empty(self, api_client):
        resp = api_client.get(RATE_URL)
        assert resp.status_code == 200
        assert resp.data["current_period"]["success_rate"] == 0
