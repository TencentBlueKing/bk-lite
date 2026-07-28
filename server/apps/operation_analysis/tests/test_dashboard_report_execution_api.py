import pytest
from rest_framework.test import APIClient

from apps.base.models import User
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def grant_feature_permission(authenticated_user):
    authenticated_user.permission = {
        "ops-analysis": {"view-View"},
    }
    return authenticated_user


@pytest.fixture
def dashboard():
    directory = Directory.objects.create(name="执行测试目录", groups=[1])
    return Dashboard.objects.create(
        name="执行测试仪表盘",
        directory=directory,
        groups=[1],
        created_by="owner",
    )


@pytest.fixture
def subscription(authenticated_user, dashboard):
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="日报",
        recipient_email="ops@example.com",
    )


@pytest.fixture
def subscription_url():
    return "/api/v1/operation_analysis/api/dashboard_subscription/"


@pytest.fixture
def execution_url():
    return "/api/v1/operation_analysis/api/dashboard_execution/"


def grant_dashboard_view(monkeypatch, allowed=True):
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.can_view_dashboard",
        lambda request, dashboard: allowed,
    )


def test_creator_with_dashboard_view_can_execute_and_retrieve(
    api_client,
    subscription,
    subscription_url,
    execution_url,
    authenticated_user,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)

    create_response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert create_response.status_code == 201, create_response.data
    assert create_response.data["subscription"] == subscription.id
    assert create_response.data["dashboard"] == subscription.dashboard_id
    assert create_response.data["creator"] == authenticated_user.username
    assert create_response.data["trigger_type"] == "manual"
    assert create_response.data["status"] == "succeeded"
    assert create_response.data["started_at"] is not None
    assert create_response.data["finished_at"] is not None
    assert create_response.data["failure_stage"] == ""
    assert create_response.data["error_message"] == ""

    retrieve_response = api_client.get(
        f"{execution_url}{create_response.data['id']}/"
    )

    assert retrieve_response.status_code == 200
    assert retrieve_response.data == create_response.data


def test_user_without_dashboard_view_cannot_execute(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch, allowed=False)

    response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert response.status_code == 403, response.data


def test_user_cannot_execute_another_users_subscription(
    subscription,
    subscription_url,
    monkeypatch,
):
    other = User.objects.create_user(
        username="other",
        password="Password123!",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Default Team"}],
    )
    other.permission = {"ops-analysis": {"view-View"}}
    other_client = APIClient()
    other_client.force_authenticate(other)
    grant_dashboard_view(monkeypatch)

    response = other_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert response.status_code == 404


def test_superuser_cannot_execute_another_users_subscription(
    subscription,
    subscription_url,
    monkeypatch,
):
    superuser = User.objects.create_user(
        username="superuser",
        password="Password123!",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Default Team"}],
    )
    superuser.is_superuser = True
    superuser.permission = {"ops-analysis": {"view-View"}}
    superuser.save(update_fields=["is_superuser"])
    superuser_client = APIClient()
    superuser_client.force_authenticate(superuser)
    grant_dashboard_view(monkeypatch)

    response = superuser_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert response.status_code == 403
