import pytest
from django.core.exceptions import ValidationError

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


def test_active_subscription_requires_dashboard():
    subscription = DashboardReportSubscription(
        dashboard=None,
        creator="owner",
        name="日报",
        status=DashboardReportSubscription.Status.ACTIVE,
        recipient_email="ops@example.com",
    )

    with pytest.raises(ValidationError):
        subscription.full_clean()


def test_phase_1a_rejects_terminated_status_from_api(
    api_client, monkeypatch
):
    from apps.operation_analysis.models.models import Dashboard, Directory

    directory = Directory.objects.create(name="状态测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="状态测试仪表盘",
        directory=directory,
        groups=[1],
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.can_view_dashboard",
        lambda request, dashboard: True,
    )

    response = api_client.post(
        "/api/v1/operation_analysis/api/dashboard_subscription/",
        {
            "dashboard": dashboard.id,
            "name": "日报",
            "status": "terminated",
            "recipient_email": "ops@example.com",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "status" in response.data
