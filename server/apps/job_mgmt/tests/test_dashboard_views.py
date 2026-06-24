"""Dashboard 视图测试（trend / success_rate_compare）

验证点：
- 未设置 current_team（无 team cookie）的已登录用户 → 403（AuthViewSet + HasPermission 守门）
- 普通用户只能看自己 team 的执行记录，看不到其他 team 的数据（team 隔离）
- 超管（su_client）可查看全量数据
- 基本功能：日期序列补齐、天数封顶、聚合计算
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

TREND_URL = "/api/v1/job_mgmt/api/dashboard/trend/"
RATE_URL = "/api/v1/job_mgmt/api/dashboard/success_rate_compare/"


def _make(status, team=None, created_offset_days=0):
    if team is None:
        team = [1]
    e = JobExecution.objects.create(name="e", job_type=JobType.SCRIPT, status=status, team=team)
    if created_offset_days:
        JobExecution.objects.filter(id=e.id).update(created_at=timezone.now() - timedelta(days=created_offset_days))
    return e


class TestDashboardAccessControl:
    """安全：HasPermission + AuthViewSet 确保 Dashboard 不再是裸 ViewSet。"""

    def test_trend_requires_current_team_cookie(self, api_client):
        """已登录但无 current_team cookie → 403，不返回任何数据（修复前是 200）。"""
        # api_client 不带 current_team cookie
        resp = api_client.get(TREND_URL)
        assert resp.status_code == 403

    def test_rate_requires_current_team_cookie(self, api_client):
        """已登录但无 current_team cookie → success_rate_compare 也须 403。"""
        resp = api_client.get(RATE_URL)
        assert resp.status_code == 403

    def test_unauthenticated_trend_returns_403(self):
        """完全未登录 → 403（DRF IsAuthenticated 拦截）。"""
        client = APIClient()
        resp = client.get(TREND_URL)
        assert resp.status_code in (401, 403)

    def test_unauthenticated_rate_returns_403(self):
        """完全未登录 → success_rate_compare 也须 403。"""
        client = APIClient()
        resp = client.get(RATE_URL)
        assert resp.status_code in (401, 403)


class TestDashboardTeamIsolation:
    """安全：普通用户的 Dashboard 数据必须按 team 过滤，不可见其他 team 的执行记录。"""

    def test_trend_only_shows_own_team_data(self, api_client, authenticated_user):
        """team=1 的用户看 trend，不应计入 team=2 的执行记录。"""
        authenticated_user.permission = {"job": {"job_record-View"}}
        api_client.cookies["current_team"] = "1"
        _make(ExecutionStatus.SUCCESS, team=[1])   # 可见
        _make(ExecutionStatus.SUCCESS, team=[2])   # 不可见

        resp = api_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        total = sum(day["execution_count"] for day in resp.data)
        assert total == 1  # 只有 team=1 的那条

    def test_rate_only_aggregates_own_team_data(self, api_client, authenticated_user):
        """team=1 的用户看 success_rate_compare，汇总应只含 team=1 的执行记录。"""
        authenticated_user.permission = {"job": {"job_record-View"}}
        api_client.cookies["current_team"] = "1"
        _make(ExecutionStatus.SUCCESS, team=[1])
        _make(ExecutionStatus.FAILED, team=[1])
        _make(ExecutionStatus.SUCCESS, team=[2])  # 不应计入

        resp = api_client.get(RATE_URL + "?days=7")
        assert resp.status_code == 200
        cur = resp.data["current_period"]
        assert cur["execution_total"] == 2  # 仅 team=1 的 2 条
        assert cur["success_count"] == 1
        assert cur["failed_count"] == 1


class TestDashboardTrend:
    def test_trend_returns_full_date_series(self, su_client):
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.FAILED)
        resp = su_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        assert len(resp.data) == 7  # 补齐完整 7 天序列

    def test_trend_caps_days_at_30(self, su_client):
        resp = su_client.get(TREND_URL + "?days=100")
        assert resp.status_code == 200
        assert len(resp.data) == 30

    def test_trend_includes_cancelled_count(self, su_client):
        _make(ExecutionStatus.CANCELLED)
        resp = su_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        assert "cancelled_count" in resp.data[0]
        assert resp.data[-1]["cancelled_count"] == 1  # 今日（序列末位）含 1 条已取消

    def test_trend_includes_daily_avg_duration(self, su_client):
        execution = _make(ExecutionStatus.SUCCESS)
        started = timezone.now()
        JobExecution.objects.filter(id=execution.id).update(started_at=started, finished_at=started + timedelta(seconds=10))
        resp = su_client.get(TREND_URL + "?days=7")
        assert resp.status_code == 200
        assert "avg_duration_seconds" in resp.data[0]
        assert resp.data[-1]["avg_duration_seconds"] == 10.0  # 今日平均时长 10s


class TestDashboardSuccessRateCompare:
    def test_rate_aggregates_current_period(self, su_client):
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.SUCCESS)
        _make(ExecutionStatus.FAILED)
        resp = su_client.get(RATE_URL + "?days=7")
        assert resp.status_code == 200
        cur = resp.data["current_period"]
        assert cur["execution_total"] == 3
        assert cur["success_count"] == 2
        assert cur["failed_count"] == 1
        assert cur["success_rate"] == round(2 / 3 * 100, 2)

    def test_rate_invalid_days_falls_back_to_7(self, su_client):
        resp = su_client.get(RATE_URL + "?days=999")
        assert resp.status_code == 200

    def test_rate_handles_empty(self, su_client):
        resp = su_client.get(RATE_URL)
        assert resp.status_code == 200
        assert resp.data["current_period"]["success_rate"] == 0
