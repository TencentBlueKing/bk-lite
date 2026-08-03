"""A9：Subscription 列表双状态摘要（scheduled / manual_test 独立）。"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def grant_feature_permission(authenticated_user):
    authenticated_user.permission = {
        "ops-analysis": {"view-View"},
    }
    return authenticated_user


@pytest.fixture(autouse=True)
def bind_current_team(api_client):
    api_client.cookies["current_team"] = "1"
    return api_client


@pytest.fixture
def dashboard():
    directory = Directory.objects.create(name="双状态目录", groups=[1])
    return Dashboard.objects.create(
        name="双状态仪表盘",
        directory=directory,
        groups=[1],
        created_by="owner",
    )


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="双状态通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def subscription_url():
    return "/api/v1/operation_analysis/api/dashboard_subscription/"


def _make_subscription(authenticated_user, dashboard, email_channel, **kwargs):
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name=kwargs.pop("name", "双状态订阅"),
        recipient_email="ops@example.com",
        email_channel=email_channel,
        **kwargs,
    )


def _make_execution(subscription, *, trigger_type, status, **kwargs):
    return DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=subscription.creator,
        trigger_type=trigger_type,
        status=status,
        **kwargs,
    )


def test_list_returns_independent_scheduled_and_manual_summaries(
    api_client,
    authenticated_user,
    dashboard,
    email_channel,
    subscription_url,
):
    sub = _make_subscription(authenticated_user, dashboard, email_channel)
    _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        status=DashboardReportExecution.Status.SUCCEEDED,
        scheduled_time_utc=timezone.now() - timedelta(days=1),
        finished_at=timezone.now() - timedelta(hours=20),
    )
    _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        status=DashboardReportExecution.Status.FAILED,
        request_id="manual-fail-1",
        failure_stage="delivery",
        error_code="smtp_rejected",
        error_message="收件被拒",
        finished_at=timezone.now() - timedelta(minutes=5),
    )

    response = api_client.get(
        subscription_url, {"dashboard_id": dashboard.id}
    )
    assert response.status_code == 200
    items = response.data if isinstance(response.data, list) else response.data["results"]
    assert len(items) == 1
    item = items[0]

    assert "latest_execution" not in item
    scheduled = item["latest_scheduled_execution"]
    manual = item["latest_manual_test_execution"]
    assert scheduled["status"] == "succeeded"
    assert scheduled["trigger_type"] == "scheduled"
    assert scheduled["scheduled_time_utc"] is not None
    assert manual["status"] == "failed"
    assert manual["trigger_type"] == "manual_test"
    assert manual["failure_stage"] == "delivery"
    assert manual["error_code"] == "smtp_rejected"
    assert manual["error_message"] == "收件被拒"
    assert "execution_id" in scheduled
    assert "execution_id" in manual


def test_list_returns_only_latest_scheduled(
    api_client,
    authenticated_user,
    dashboard,
    email_channel,
    subscription_url,
):
    sub = _make_subscription(authenticated_user, dashboard, email_channel)
    older = _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        status=DashboardReportExecution.Status.FAILED,
        scheduled_time_utc=timezone.now() - timedelta(days=3),
    )
    newer = _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        status=DashboardReportExecution.Status.SUCCEEDED,
        scheduled_time_utc=timezone.now() - timedelta(days=1),
    )

    response = api_client.get(
        subscription_url, {"dashboard_id": dashboard.id}
    )
    item = (
        response.data
        if isinstance(response.data, list)
        else response.data["results"]
    )[0]
    assert item["latest_scheduled_execution"]["execution_id"] == newer.id
    assert item["latest_scheduled_execution"]["status"] == "succeeded"
    assert item["latest_scheduled_execution"]["execution_id"] != older.id


def test_list_returns_only_latest_manual_test(
    api_client,
    authenticated_user,
    dashboard,
    email_channel,
    subscription_url,
):
    sub = _make_subscription(authenticated_user, dashboard, email_channel)
    _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        status=DashboardReportExecution.Status.SUCCEEDED,
        request_id="manual-old",
    )
    newer = _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        status=DashboardReportExecution.Status.FAILED,
        request_id="manual-new",
        error_message="新失败",
    )

    response = api_client.get(
        subscription_url, {"dashboard_id": dashboard.id}
    )
    item = (
        response.data
        if isinstance(response.data, list)
        else response.data["results"]
    )[0]
    assert item["latest_manual_test_execution"]["execution_id"] == newer.id
    assert item["latest_manual_test_execution"]["status"] == "failed"


def test_list_null_when_only_scheduled(
    api_client,
    authenticated_user,
    dashboard,
    email_channel,
    subscription_url,
):
    sub = _make_subscription(authenticated_user, dashboard, email_channel)
    _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        status=DashboardReportExecution.Status.SUCCEEDED,
        scheduled_time_utc=timezone.now(),
    )

    response = api_client.get(
        subscription_url, {"dashboard_id": dashboard.id}
    )
    item = (
        response.data
        if isinstance(response.data, list)
        else response.data["results"]
    )[0]
    assert item["latest_scheduled_execution"] is not None
    assert item["latest_manual_test_execution"] is None


def test_list_null_when_only_manual_test(
    api_client,
    authenticated_user,
    dashboard,
    email_channel,
    subscription_url,
):
    sub = _make_subscription(authenticated_user, dashboard, email_channel)
    _make_execution(
        sub,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        status=DashboardReportExecution.Status.PENDING,
        request_id="manual-only",
    )

    response = api_client.get(
        subscription_url, {"dashboard_id": dashboard.id}
    )
    item = (
        response.data
        if isinstance(response.data, list)
        else response.data["results"]
    )[0]
    assert item["latest_scheduled_execution"] is None
    assert item["latest_manual_test_execution"]["status"] == "pending"


def test_list_avoids_n_plus_one_for_execution_summaries(
    api_client,
    authenticated_user,
    dashboard,
    email_channel,
    subscription_url,
):
    for index in range(5):
        sub = _make_subscription(
            authenticated_user,
            dashboard,
            email_channel,
            name=f"订阅-{index}",
        )
        _make_execution(
            sub,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
            status=DashboardReportExecution.Status.SUCCEEDED,
            scheduled_time_utc=timezone.now() - timedelta(hours=index + 1),
        )
        _make_execution(
            sub,
            trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
            status=DashboardReportExecution.Status.FAILED,
            request_id=f"manual-{index}",
        )

    with CaptureQueriesContext(connection) as ctx:
        response = api_client.get(
            subscription_url, {"dashboard_id": dashboard.id}
        )
    assert response.status_code == 200
    items = (
        response.data
        if isinstance(response.data, list)
        else response.data["results"]
    )
    assert len(items) == 5

    execution_table_queries = [
        query["sql"]
        for query in ctx.captured_queries
        if "operation_analysis_dashboard_report_execution" in query["sql"].lower()
    ]
    # Prefetch：最多两次（scheduled / manual_test），不应随订阅数线性增长
    assert len(execution_table_queries) <= 2, (
        f"疑似 N+1：Execution 相关查询 {len(execution_table_queries)} 次，"
        f"SQL={execution_table_queries}"
    )
