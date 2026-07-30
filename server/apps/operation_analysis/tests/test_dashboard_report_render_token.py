import hashlib
from datetime import timedelta

import jwt
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
    DashboardReportRenderToken,
)
from apps.operation_analysis.services.render_token_service import (
    DashboardReportRenderTokenError,
    DashboardReportRenderTokenService,
)
from apps.system_mgmt.models import User as SystemUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def running_execution(authenticated_user):
    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        defaults={
            "display_name": authenticated_user.username,
            "email": "render-token@example.com",
            "password": "unused",
            "domain": authenticated_user.domain,
            "group_list": authenticated_user.group_list,
        },
    )
    directory = Directory.objects.create(name="Token 测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="Token 测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="Token 测试订阅",
        recipient_email="ops@example.com",
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=timezone.now(),
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        filter_values={},
    )
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        dashboard_name=dashboard.name,
        dashboard_updated_at=dashboard.updated_at,
        view_sets=[],
        filters=[],
        other={},
        widget_manifest=[],
    )
    return execution


@pytest.fixture
def another_running_execution(authenticated_user):
    directory = Directory.objects.create(name="另一 Token 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="另一 Token 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="另一 Token 订阅",
        recipient_email="ops@example.com",
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=timezone.now(),
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        filter_values={},
    )
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        dashboard_name=dashboard.name,
        dashboard_updated_at=dashboard.updated_at,
        view_sets=[],
        filters=[],
        other={},
        widget_manifest=[],
    )
    return execution


def test_issue_and_consume_render_token_once(running_execution, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")

    issued = DashboardReportRenderTokenService.issue(running_execution)

    record = DashboardReportRenderToken.objects.get(
        execution=running_execution
    )
    assert issued.plaintext
    assert record.token_hash == hashlib.sha256(
        issued.plaintext.encode()
    ).hexdigest()
    assert issued.plaintext != record.token_hash
    assert record.expires_at > timezone.now()
    assert record.consumed_at is None

    session_user = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    record.refresh_from_db()
    claims = jwt.decode(
        session_user["token"],
        "render-token-test-secret",
        algorithms=["HS256"],
    )
    assert record.consumed_at is not None
    assert claims["render_execution_id"] == running_execution.id

    with pytest.raises(DashboardReportRenderTokenError):
        DashboardReportRenderTokenService.consume(
            execution_id=running_execution.id,
            plaintext=issued.plaintext,
        )


def test_expired_render_token_is_rejected(running_execution):
    issued = DashboardReportRenderTokenService.issue(running_execution)
    DashboardReportRenderToken.objects.filter(
        execution=running_execution
    ).update(expires_at=timezone.now() - timedelta(seconds=1))

    with pytest.raises(DashboardReportRenderTokenError):
        DashboardReportRenderTokenService.consume(
            execution_id=running_execution.id,
            plaintext=issued.plaintext,
        )


def test_render_token_cannot_cross_execution(
    running_execution,
    another_running_execution,
):
    issued = DashboardReportRenderTokenService.issue(running_execution)

    with pytest.raises(DashboardReportRenderTokenError):
        DashboardReportRenderTokenService.consume(
            execution_id=another_running_execution.id,
            plaintext=issued.plaintext,
        )


def test_render_input_rejects_normal_session_and_accepts_bound_render_session(
    running_execution,
    authenticated_user,
    api_client,
    monkeypatch,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    authenticated_user.permission = {
        "ops-analysis": {"view-View"},
    }
    url = (
        "/api/v1/operation_analysis/api/dashboard_execution/"
        f"{running_execution.id}/render-input/"
    )

    ordinary_response = api_client.get(url)
    assert ordinary_response.status_code == 403

    issued = DashboardReportRenderTokenService.issue(running_execution)
    session_user = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    scoped_client = APIClient()
    scoped_client.force_authenticate(user=authenticated_user)
    scoped_response = scoped_client.get(
        url,
        HTTP_AUTHORIZATION=f"Bearer {session_user['token']}",
    )
    assert scoped_response.status_code == 200


def test_render_token_exchange_endpoint_consumes_token_once(
    running_execution,
    monkeypatch,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    url = (
        "/api/v1/operation_analysis/api/dashboard_execution/"
        f"{running_execution.id}/render-token-exchange/"
    )
    anonymous_client = APIClient()

    first = anonymous_client.post(
        url,
        {"token": issued.plaintext},
        format="json",
    )
    second = anonymous_client.post(
        url,
        {"token": issued.plaintext},
        format="json",
    )

    assert first.status_code == 200
    assert first.data["session_user"]["username"] == (
        running_execution.creator
    )
    assert second.status_code == 403
