"""Dashboard trend / success_rate_compare 自定义区间的视图层测试。

job_mgmt 接口经许可中间件会返回 403，故用 APIRequestFactory 直调 action 绕过。
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.views.dashboard import DashboardViewSet

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

_factory = APIRequestFactory()


def _call(action, user, **params):
    view = DashboardViewSet.as_view({"get": action})
    request = _factory.get("/", params)
    request.COOKIES["current_team"] = "1"
    user.permission = {"job": {"job_record-View"}}
    force_authenticate(request, user=user)
    return view(request)


def _make(status, offset_days=0):
    e = JobExecution.objects.create(name="e", job_type=JobType.SCRIPT, status=status, team=[1])
    if offset_days:
        JobExecution.objects.filter(id=e.id).update(created_at=timezone.now() - timedelta(days=offset_days))
    return e


def test_trend_days_capped_at_30(authenticated_user):
    resp = _call("trend", authenticated_user, days="100")
    assert resp.status_code == 200
    assert len(resp.data) == 30


def test_trend_custom_range_length_is_inclusive(authenticated_user):
    today = timezone.localdate()
    start = today - timedelta(days=9)  # 10 天闭区间
    resp = _call("trend", authenticated_user, start_date=start.isoformat(), end_date=today.isoformat())
    assert resp.status_code == 200
    assert len(resp.data) == 10


def test_trend_invalid_range_returns_400(authenticated_user):
    resp = _call("trend", authenticated_user, start_date="2026-01-07", end_date="2026-01-01")
    assert resp.status_code == 400
    assert "error" in resp.data


def test_trend_too_long_range_returns_400(authenticated_user):
    resp = _call("trend", authenticated_user, start_date="2026-01-01", end_date="2026-12-31")
    assert resp.status_code == 400


def test_success_rate_custom_range_current_vs_previous(authenticated_user):
    today = timezone.localdate()
    # 当前周期（最近 3 天，闭区间）：2 成功 1 失败 -> 66.67%
    _make(ExecutionStatus.SUCCESS, offset_days=0)
    _make(ExecutionStatus.SUCCESS, offset_days=1)
    _make(ExecutionStatus.FAILED, offset_days=2)
    # 上一周期（再往前 3 天）：1 成功 1 失败 -> 50%
    _make(ExecutionStatus.SUCCESS, offset_days=4)
    _make(ExecutionStatus.FAILED, offset_days=5)

    start = today - timedelta(days=2)  # 3 天闭区间
    resp = _call("success_rate_compare", authenticated_user, start_date=start.isoformat(), end_date=today.isoformat())
    assert resp.status_code == 200
    cur = resp.data["current_period"]
    assert cur["execution_total"] == 3
    assert cur["success_count"] == 2
    assert cur["failed_count"] == 1
    assert cur["success_rate"] == round(2 / 3 * 100, 2)
    assert resp.data["days"] == 3
    # 当前 66.67% 较上周期 50% 提升约 16.67
    assert resp.data["success_rate_increase"] == round(round(2 / 3 * 100, 2) - 50.0, 2)
