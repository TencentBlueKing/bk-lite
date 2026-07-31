import pytest

from apps.operation_analysis.models.models import Dashboard, Directory
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
    directory = Directory.objects.create(name="调度CRUD目录", groups=[1])
    return Dashboard.objects.create(
        name="调度CRUD仪表盘",
        directory=directory,
        groups=[1],
    )


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="调度通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def subscription_url():
    return "/api/v1/operation_analysis/api/dashboard_subscription/"


def grant_view(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.can_view_dashboard",
        lambda request, dashboard: True,
    )


def test_create_without_schedule_keeps_null_next_run(
    api_client, dashboard, subscription_url, email_channel, monkeypatch
):
    grant_view(monkeypatch)
    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "无调度",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["schedule_type"] is None
    assert response.data["next_run_at"] is None
    assert response.data["timezone"] is None
    assert response.data["version"] == 1


def test_create_with_daily_schedule_sets_future_next_run(
    api_client, dashboard, subscription_url, email_channel, monkeypatch
):
    grant_view(monkeypatch)
    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "schedule_type": "daily",
            "schedule_hour": 9,
            "schedule_minute": 0,
            "timezone": "Asia/Shanghai",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["schedule_type"] == "daily"
    assert response.data["timezone"] == "Asia/Shanghai"
    assert response.data["next_run_at"] is not None
    assert response.data["version"] == 1


def test_update_email_does_not_bump_version(
    api_client, dashboard, subscription_url, email_channel, monkeypatch
):
    grant_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "schedule_type": "daily",
            "schedule_hour": 9,
            "schedule_minute": 0,
            "timezone": "Asia/Shanghai",
        },
        format="json",
    ).data
    next_run = created["next_run_at"]
    updated = api_client.patch(
        f"{subscription_url}{created['id']}/",
        {"recipient_email": "new@example.com", "version": created["version"]},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["recipient_email"] == "new@example.com"
    assert updated.data["version"] == created["version"]
    assert updated.data["next_run_at"] == next_run


def test_update_schedule_bumps_version_and_recomputes(
    api_client, dashboard, subscription_url, email_channel, monkeypatch
):
    grant_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "schedule_type": "daily",
            "schedule_hour": 9,
            "schedule_minute": 0,
            "timezone": "Asia/Shanghai",
        },
        format="json",
    ).data
    updated = api_client.patch(
        f"{subscription_url}{created['id']}/",
        {
            "schedule_hour": 10,
            "version": created["version"],
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["schedule_hour"] == 10
    assert updated.data["version"] == created["version"] + 1
    assert updated.data["next_run_at"] != created["next_run_at"]


def test_timezone_is_independent_business_config(
    api_client, dashboard, subscription_url, email_channel, monkeypatch
):
    grant_view(monkeypatch)
    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "独立时区",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
            "schedule_type": "daily",
            "schedule_hour": 9,
            "schedule_minute": 0,
            "timezone": "America/New_York",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["timezone"] == "America/New_York"
