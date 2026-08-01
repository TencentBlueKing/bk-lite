import pytest
from rest_framework.test import APIClient

from apps.base.models import User
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
    directory = Directory.objects.create(name="订阅测试目录", groups=[1])
    return Dashboard.objects.create(
        name="订阅测试仪表盘",
        directory=directory,
        groups=[1],
        created_by="owner",
    )


@pytest.fixture
def subscription_url():
    return "/api/v1/operation_analysis/api/dashboard_subscription/"


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="订阅邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


def grant_dashboard_view(monkeypatch, allowed=True):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.can_view_dashboard",
        lambda request, dashboard: allowed,
    )


def test_creator_with_dashboard_view_can_create_subscription(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)

    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["creator"] == authenticated_user.username
    assert response.data["status"] == "active"
    assert response.data["dashboard"] == dashboard.id


def test_user_without_dashboard_view_cannot_create_subscription(
    api_client, dashboard, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch, allowed=False)

    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    assert response.status_code == 403


def test_missing_dashboard_cannot_create_subscription(
    api_client, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch)

    response = api_client.post(
        subscription_url,
        {
            "dashboard": 999999,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "dashboard" in response.data


def test_paused_subscription_still_requires_dashboard_on_create(
    api_client, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch)

    response = api_client.post(
        subscription_url,
        {
            "name": "暂停的日报",
            "status": "paused",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "dashboard" in response.data


def test_creator_must_still_view_dashboard_to_update(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    grant_dashboard_view(monkeypatch, allowed=False)

    response = api_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {"name": "新日报"},
        format="json",
    )

    assert response.status_code == 403


def test_creator_can_delete_after_dashboard_view_is_lost(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    grant_dashboard_view(monkeypatch, allowed=False)
    authenticated_user.permission = {"ops-analysis": set()}

    response = api_client.delete(f"{subscription_url}{created.data['id']}/")

    assert response.status_code == 200
    from apps.operation_analysis.models.subscription_models import (
        DashboardReportSubscription,
    )

    assert not DashboardReportSubscription.objects.filter(
        pk=created.data["id"]
    ).exists()
    soft = DashboardReportSubscription.all_objects.get(pk=created.data["id"])
    assert soft.deleted_at is not None


def test_other_user_cannot_update_or_delete_subscription(
    api_client, dashboard, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    other = User.objects.create_user(
        username="other",
        password="Password123!",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Default Team"}],
    )
    other.permission = {"ops-analysis": {"view-View"}}
    other_client = APIClient()
    other_client.force_authenticate(other)

    update_response = other_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {"name": "越权修改"},
        format="json",
    )
    delete_response = other_client.delete(
        f"{subscription_url}{created.data['id']}/"
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404


def test_list_only_returns_current_users_subscriptions(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    own = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "自己的订阅",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )
    from apps.operation_analysis.models.subscription_models import (
        DashboardReportSubscription,
    )

    DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator="other",
        name="他人的订阅",
        recipient_email="other@example.com",
    )

    response = api_client.get(subscription_url, {"dashboard_id": dashboard.id})

    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [own.data["id"]]


def test_creator_can_update_subscription(
    api_client, dashboard, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    response = api_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {"name": "周报", "status": "paused"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == "周报"
    assert response.data["status"] == "paused"


def test_create_rejects_invalid_email(
    api_client, dashboard, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch)

    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "not-an-email",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "recipient_email" in response.data


def test_update_cannot_change_dashboard(
    api_client, dashboard, subscription_url, monkeypatch, email_channel
):
    grant_dashboard_view(monkeypatch)
    other_dashboard = Dashboard.objects.create(name="另一个仪表盘")
    created = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
            "email_channel": email_channel.id,
        },
        format="json",
    )

    response = api_client.patch(
        f"{subscription_url}{created.data['id']}/",
        {"dashboard": other_dashboard.id},
        format="json",
    )

    assert response.status_code == 400


def test_create_requires_email_channel(
    api_client, dashboard, subscription_url, monkeypatch
):
    grant_dashboard_view(monkeypatch)

    response = api_client.post(
        subscription_url,
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "recipient_email": "ops@example.com",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["email_channel"][0] == "报告订阅必须指定邮件通道"
