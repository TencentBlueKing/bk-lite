import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.base.models import User
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.execution_orchestrator import (
    ExecutionOrchestrator,
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
        config={
            "filter_values": {
                "environment": "production",
                "time_range": "last_7_days",
            }
        },
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
    monkeypatch.setattr(
        "apps.operation_analysis.views.view."
        "DashboardModelViewSet.get_has_permission",
        lambda self, user, dashboard, team_id, **kwargs: allowed,
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
    assert create_response.data == {
        "execution_id": create_response.data["execution_id"],
        "status": "pending",
    }

    retrieve_response = api_client.get(
        f"{execution_url}{create_response.data['execution_id']}/"
    )

    assert retrieve_response.status_code == 200
    assert retrieve_response.data["subscription"] == subscription.id
    assert retrieve_response.data["dashboard"] == subscription.dashboard_id
    assert retrieve_response.data["creator"] == authenticated_user.username
    assert retrieve_response.data["trigger_type"] == "manual"
    assert retrieve_response.data["status"] == "pending"
    assert retrieve_response.data["started_at"] is None
    assert retrieve_response.data["finished_at"] is None
    assert retrieve_response.data["failure_stage"] == ""
    assert retrieve_response.data["error_message"] == ""
    assert retrieve_response.data["snapshot"] == {
        "dashboard_id": subscription.dashboard_id,
        "creator_id": authenticated_user.username,
        "subscription_id": subscription.id,
        "filter_values": {
            "environment": "production",
            "time_range": "last_7_days",
        },
        "created_at": retrieve_response.data["snapshot"]["created_at"],
    }


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


def test_subscription_changes_do_not_affect_existing_snapshot(
    api_client,
    subscription,
    subscription_url,
    execution_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    create_response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )
    execution_id = create_response.data["execution_id"]

    subscription.config = {
        "filter_values": {
            "environment": "staging",
            "time_range": "today",
        }
    }
    subscription.save(update_fields=["config", "updated_at"])

    retrieve_response = api_client.get(f"{execution_url}{execution_id}/")

    assert retrieve_response.status_code == 200
    assert retrieve_response.data["snapshot"]["filter_values"] == {
        "environment": "production",
        "time_range": "last_7_days",
    }


def test_snapshot_creation_failure_marks_execution_failed(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    subscription.config = {"filter_values": ["invalid"]}
    subscription.save(update_fields=["config", "updated_at"])

    response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["status"] == "failed"
    execution = DashboardReportExecution.objects.get(
        id=response.data["execution_id"]
    )
    assert execution.failure_stage == "snapshot"
    assert execution.error_message == "Execution Input Snapshot 创建失败"
    assert execution.started_at is None
    assert execution.finished_at is not None
    assert not hasattr(execution, "snapshot")


def test_unexpected_snapshot_creation_failure_marks_execution_failed(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)

    def raise_snapshot_error(cls, execution, source_subscription):
        raise RuntimeError("unexpected snapshot error")

    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_create_snapshot",
        classmethod(raise_snapshot_error),
    )

    response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert response.status_code == 201, response.data
    execution = DashboardReportExecution.objects.get(
        id=response.data["execution_id"]
    )
    assert execution.status == DashboardReportExecution.Status.FAILED
    assert execution.failure_stage == "snapshot"
    assert execution.error_message == "Execution Input Snapshot 创建失败"
    assert execution.started_at is None
    assert execution.finished_at is not None
    assert not hasattr(execution, "snapshot")


def test_execution_snapshot_cannot_be_updated(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )
    snapshot = DashboardReportExecutionSnapshot.objects.get(
        execution_id=response.data["execution_id"]
    )

    snapshot.filter_values = {"environment": "staging"}

    with pytest.raises(
        ValidationError,
        match="Execution Input Snapshot 创建后不可修改",
    ):
        snapshot.save()

    with pytest.raises(
        ValidationError,
        match="Execution Input Snapshot 创建后不可修改",
    ):
        DashboardReportExecutionSnapshot.objects.filter(pk=snapshot.pk).update(
            filter_values={"environment": "staging"}
        )


def test_execution_service_enforces_status_transitions(
    subscription,
):
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=subscription.creator,
    )

    with pytest.raises(
        ValidationError,
        match="不允许从 pending 转换到 succeeded",
    ):
        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.SUCCEEDED,
        )

    with pytest.raises(
        ValidationError,
        match="pending → running 必须通过 claim_execution",
    ):
        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.RUNNING,
        )

    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
    assert execution.status == DashboardReportExecution.Status.RUNNING
    assert execution.started_at is not None

    DashboardReportExecutionService.transition(
        execution,
        DashboardReportExecution.Status.SUCCEEDED,
    )
    assert execution.status == DashboardReportExecution.Status.SUCCEEDED
    assert execution.finished_at is not None

    with pytest.raises(ValidationError, match="不允许从 succeeded 转换到 failed"):
        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.FAILED,
        )


def test_manual_execute_does_not_run_orchestrator_in_request(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        ExecutionOrchestrator,
        "execute",
        classmethod(
            lambda cls, execution_id: pytest.fail(
                "execute API must not run the orchestrator"
            )
        ),
    )

    response = api_client.post(
        f"{subscription_url}{subscription.id}/execute/",
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.status_code == 201
    assert response.data["status"] == "pending"


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
