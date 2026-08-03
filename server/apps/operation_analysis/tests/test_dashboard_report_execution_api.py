import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.base.models import User
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.execution_orchestrator import (
    ExecutionOrchestrator,
)
from apps.operation_analysis.services.render_token_service import (
    DashboardReportRenderTokenService,
)
from apps.system_mgmt.models import Channel
from apps.system_mgmt.models import User as SystemUser


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
def email_channel():
    return Channel.objects.create(
        name="执行邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def subscription(authenticated_user, dashboard, email_channel):
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        team_id=1,
        name="日报",
        recipient_email="ops@example.com",
        email_channel=email_channel,
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


_REQUEST_ID_SEQ = 0


def post_execute(api_client, subscription_url, subscription_id, request_id=None):
    global _REQUEST_ID_SEQ
    if request_id is None:
        _REQUEST_ID_SEQ += 1
        request_id = f"req-{_REQUEST_ID_SEQ}"
    return api_client.post(
        f"{subscription_url}{subscription_id}/execute/",
        {"request_id": request_id},
        format="json",
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

    create_response = post_execute(
        api_client, subscription_url, subscription.id, "req-main-1"
    )

    assert create_response.status_code == 201, create_response.data
    assert create_response.data == {
        "execution_id": create_response.data["execution_id"],
        "status": "pending",
        "request_id": "req-main-1",
        "created": True,
    }

    retrieve_response = api_client.get(
        f"{execution_url}{create_response.data['execution_id']}/"
    )

    assert retrieve_response.status_code == 200
    assert retrieve_response.data["subscription"] == subscription.id
    assert retrieve_response.data["dashboard"] == subscription.dashboard_id
    assert retrieve_response.data["creator"] == authenticated_user.username
    assert retrieve_response.data["trigger_type"] == "manual_test"
    assert retrieve_response.data["request_id"] == "req-main-1"
    assert retrieve_response.data["status"] == "pending"
    assert retrieve_response.data["started_at"] is None
    assert retrieve_response.data["finished_at"] is None
    assert retrieve_response.data["failure_stage"] == ""
    assert retrieve_response.data["error_code"] == ""
    assert retrieve_response.data["error_message"] == ""
    assert retrieve_response.data["attempt_count"] == 0
    assert retrieve_response.data["snapshot"] == {
        "dashboard_id": subscription.dashboard_id,
        "resource_type": "dashboard",
        "resource_id": subscription.dashboard_id,
        "resource_display_label": "仪表盘",
        "creator_id": authenticated_user.username,
        "creator_domain": authenticated_user.domain,
        "creator_timezone": "Asia/Shanghai",
        "subscription_id": subscription.id,
        "subscription_name": "日报",
        "recipient_email": "ops@example.com",
        "trigger_type": "manual_test",
        "email_channel_id": subscription.email_channel_id,
        "execution_team_id": subscription.team_id,
        "scheduled_time_utc": None,
        "schedule_timezone": "",
        "scheduled_local_time": "",
        "subscription_version": subscription.version,
        "subscription_revision": subscription.revision,
        "filter_values": {
            "environment": "production",
            "time_range": "last_7_days",
        },
        "filter_semantics": {
            "environment": {
                "value_kind": "static",
                "value": "production",
            },
            "time_range": {
                "value_kind": "static",
                "value": "last_7_days",
            },
        },
        "created_at": retrieve_response.data["snapshot"]["created_at"],
    }


def test_same_username_in_other_domain_cannot_read_execution(
    api_client,
    authenticated_user,
    subscription,
    execution_url,
):
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=authenticated_user.username,
        creator_domain="other.example",
    )

    response = api_client.get(f"{execution_url}{execution.id}/")

    assert response.status_code == 404


def test_user_without_dashboard_view_cannot_execute(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
):
    grant_dashboard_view(monkeypatch, allowed=False)

    response = post_execute(
        api_client, subscription_url, subscription.id
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
    create_response = post_execute(
        api_client, subscription_url, subscription.id
    )
    execution_id = create_response.data["execution_id"]

    subscription.name = "改名后的订阅"
    subscription.recipient_email = "changed@example.com"
    subscription.config = {
        "filter_values": {
            "environment": "staging",
            "time_range": "today",
        }
    }
    subscription.save(
        update_fields=["name", "recipient_email", "config", "updated_at"]
    )

    retrieve_response = api_client.get(f"{execution_url}{execution_id}/")

    assert retrieve_response.status_code == 200
    snapshot = retrieve_response.data["snapshot"]
    assert snapshot["subscription_name"] == "日报"
    assert snapshot["recipient_email"] == "ops@example.com"
    assert snapshot["trigger_type"] == "manual_test"
    assert snapshot["filter_values"] == {
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

    response = post_execute(
        api_client, subscription_url, subscription.id
    )

    assert response.status_code == 201, response.data
    assert response.data["status"] == "failed"
    execution = DashboardReportExecution.objects.get(
        id=response.data["execution_id"]
    )
    assert execution.failure_stage == "snapshot"
    assert execution.error_code == "filter_invalid"
    assert "filter_values" in execution.error_message
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

    response = post_execute(
        api_client, subscription_url, subscription.id
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
    response = post_execute(
        api_client, subscription_url, subscription.id
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


def test_unknown_terminal_state_records_finished_at(
    subscription,
):
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=subscription.creator,
    )
    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()

    DashboardReportExecutionService.transition(
        execution,
        DashboardReportExecution.Status.UNKNOWN,
    )
    assert execution.status == DashboardReportExecution.Status.UNKNOWN
    assert execution.finished_at is not None


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

    response = post_execute(
        api_client, subscription_url, subscription.id
    )

    assert response.status_code == 201, response.data
    assert response.status_code == 201
    assert response.data["status"] == "pending"


def test_manual_execute_dispatches_render_task_after_commit(
    api_client,
    subscription,
    subscription_url,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    grant_dashboard_view(monkeypatch)
    dispatched = []
    monkeypatch.setattr(
        "apps.operation_analysis.tasks.tasks."
        "render_dashboard_report_task.delay",
        lambda execution_id: dispatched.append(execution_id),
    )

    with django_capture_on_commit_callbacks(execute=True):
        response = post_execute(
            api_client, subscription_url, subscription.id
        )

    assert response.status_code == 201
    assert response.data["status"] == "pending"
    assert dispatched == [response.data["execution_id"]]


def test_running_execution_exposes_only_frozen_render_input(
    api_client,
    subscription,
    execution_url,
    authenticated_user,
):
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        status=DashboardReportExecution.Status.RUNNING,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=subscription.dashboard_id,
        creator_id=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=subscription.email_channel_id,
        scheduled_time_utc=None,
        schedule_timezone="",
        scheduled_local_time="",
        subscription_version=subscription.version,
        subscription_revision=subscription.revision,
        execution_team_id=subscription.team_id,
        filter_values={"environment": "production"},
    )
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=subscription.dashboard_id,
        dashboard_name="冻结仪表盘",
        dashboard_updated_at=subscription.dashboard.updated_at,
        view_sets=[{"i": "chart-1", "valueConfig": {"chartType": "line"}}],
        filters=[{"id": "environment"}],
        other={"title": "冻结标题"},
        widget_manifest=[
            {
                "widget_id": "chart-1",
                "widget_type": "line",
                "datasource_id": 17,
            }
        ],
    )
    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        domain=authenticated_user.domain,
        defaults={
            "display_name": authenticated_user.username,
            "email": "render-session@example.com",
            "password": "unused",
            "group_list": authenticated_user.group_list,
        },
    )
    issued = DashboardReportRenderTokenService.issue(execution)
    session_user = DashboardReportRenderTokenService.consume(
        execution_id=execution.id,
        plaintext=issued.plaintext,
    )

    response = api_client.get(
        f"{execution_url}{execution.id}/render-input/",
        HTTP_AUTHORIZATION=f"Bearer {session_user['token']}",
    )

    assert response.status_code == 200
    assert response.data == {
        "execution_id": execution.id,
        "input_snapshot": {
            "dashboard_id": subscription.dashboard_id,
            "resource_type": "dashboard",
            "resource_id": subscription.dashboard_id,
            "resource_display_label": "仪表盘",
            "creator_id": authenticated_user.username,
            "creator_domain": authenticated_user.domain,
            "creator_timezone": "Asia/Shanghai",
            "subscription_id": subscription.id,
            "subscription_name": subscription.name,
            "recipient_email": subscription.recipient_email,
            "trigger_type": execution.trigger_type,
            "email_channel_id": subscription.email_channel_id,
            "execution_team_id": subscription.team_id,
            "scheduled_time_utc": None,
            "schedule_timezone": "",
            "scheduled_local_time": "",
            "subscription_version": subscription.version,
            "subscription_revision": subscription.revision,
            "filter_values": {"environment": "production"},
            "filter_semantics": {},
            "created_at": response.data["input_snapshot"]["created_at"],
        },
        "render_snapshot": {
            "dashboard_id": subscription.dashboard_id,
            "dashboard_name": "冻结仪表盘",
            "dashboard_updated_at": (
                response.data["render_snapshot"]["dashboard_updated_at"]
            ),
            "resource_type": "dashboard",
            "resource_id": subscription.dashboard_id,
            "render_schema_version": 1,
            "resource_display_label": "仪表盘",
            "view_sets": [
                {"i": "chart-1", "valueConfig": {"chartType": "line"}}
            ],
            "filters": [{"id": "environment"}],
            "other": {"title": "冻结标题"},
            "widget_manifest": [
                {
                    "widget_id": "chart-1",
                    "widget_type": "line",
                    "datasource_id": 17,
                }
            ],
            "created_at": response.data["render_snapshot"]["created_at"],
        },
    }


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
        {"request_id": "req-other"},
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
        {"request_id": "req-super"},
        format="json",
    )

    assert response.status_code == 403
