"""Phase 2：resource_type / resource_id 双写与过滤兼容。"""

import pytest

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.canvas_report.types import (
    DEFAULT_RENDER_SCHEMA_VERSION,
    RESOURCE_TYPE_DASHBOARD,
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
    directory = Directory.objects.create(name="绑定测试目录", groups=[1])
    return Dashboard.objects.create(
        name="绑定测试仪表盘",
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
        name="绑定邮件通道",
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


def _base_payload(email_channel, **extra):
    payload = {
        "name": "日报",
        "recipient_email": "ops@example.com",
        "email_channel": email_channel.id,
    }
    payload.update(extra)
    return payload


def test_create_with_dashboard_dual_writes_resource_fields(
    api_client,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    response = api_client.post(
        subscription_url,
        _base_payload(email_channel, dashboard=dashboard.id),
        format="json",
    )
    assert response.status_code == 201
    assert response.data["dashboard"] == dashboard.id
    assert response.data["resource_type"] == RESOURCE_TYPE_DASHBOARD
    assert response.data["resource_id"] == dashboard.id

    row = DashboardReportSubscription.objects.get(pk=response.data["id"])
    assert row.resource_type == RESOURCE_TYPE_DASHBOARD
    assert row.resource_id == dashboard.id
    assert row.dashboard_id == dashboard.id


def test_create_with_resource_fields_dual_writes_dashboard_fk(
    api_client,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    response = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            resource_type=RESOURCE_TYPE_DASHBOARD,
            resource_id=dashboard.id,
        ),
        format="json",
    )
    assert response.status_code == 201
    assert response.data["dashboard"] == dashboard.id
    assert response.data["resource_type"] == RESOURCE_TYPE_DASHBOARD
    assert response.data["resource_id"] == dashboard.id


def _make_screen(**view_sets_extra):
    from apps.operation_analysis.models.models import Screen

    view_sets = {
        "viewport": {"width": 1920, "height": 1080},
        "items": [],
        "filters": [],
    }
    view_sets.update(view_sets_extra)
    return Screen.objects.create(
        name=f"绑定测试大屏-{Screen.objects.count()}",
        groups=[1],
        view_sets=view_sets,
    )


def test_create_screen_subscription_without_dashboard_fk(
    api_client,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions."
        "can_view_canvas",
        lambda *args, **kwargs: True,
    )
    screen = _make_screen()
    response = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            resource_type="screen",
            resource_id=screen.id,
        ),
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["resource_type"] == "screen"
    assert response.data["resource_id"] == screen.id
    assert response.data["dashboard"] is None
    row = DashboardReportSubscription.objects.get(pk=response.data["id"])
    assert row.dashboard_id is None
    assert row.resource_type == "screen"
    assert row.resource_id == screen.id


def test_create_screen_subscription_missing_resource_returns_business_error(
    api_client,
    subscription_url,
    monkeypatch,
    email_channel,
):
    """Screen resource_id 不存在时返回业务错误，不得 500。"""
    from apps.operation_analysis.models.models import Screen

    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions."
        "can_view_canvas",
        lambda *args, **kwargs: True,
    )
    missing_id = 9_999_999
    assert not Screen.objects.filter(pk=missing_id).exists()
    response = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            resource_type="screen",
            resource_id=missing_id,
        ),
        format="json",
    )
    assert response.status_code == 403
    detail = response.data.get("detail", response.data)
    assert "源画布已不存在" in str(detail)


def test_create_screen_subscription_requires_view_permission(
    api_client,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions."
        "can_view_canvas",
        lambda *args, **kwargs: False,
    )
    screen = _make_screen()
    response = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            resource_type="screen",
            resource_id=screen.id,
        ),
        format="json",
    )
    assert response.status_code == 403


def test_screen_delete_terminates_subscriptions(
    api_client,
    subscription_url,
    monkeypatch,
    email_channel,
    authenticated_user,
):
    from apps.operation_analysis.services.canvas_report.registry import (
        get_canvas_report_adapter,
    )
    from apps.operation_analysis.services.canvas_report.types import (
        RESOURCE_TYPE_SCREEN,
    )

    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        "apps.operation_analysis.services.canvas_report.permissions."
        "can_view_canvas",
        lambda *args, **kwargs: True,
    )
    screen = _make_screen()
    create = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            name="大屏日报",
            resource_type="screen",
            resource_id=screen.id,
        ),
        format="json",
    )
    assert create.status_code == 201, create.data
    sub_id = create.data["id"]

    adapter = get_canvas_report_adapter(RESOURCE_TYPE_SCREEN)
    terminated = adapter.terminate_subscriptions_on_delete(
        screen,
        actor=authenticated_user.username,
        actor_domain=getattr(authenticated_user, "domain", "") or "",
    )
    assert terminated == 1
    row = DashboardReportSubscription.all_objects.get(pk=sub_id)
    assert row.status == DashboardReportSubscription.Status.TERMINATED
    assert row.termination_reason == "screen_deleted"


def test_create_rejects_unknown_resource_type(
    api_client,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    response = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            resource_type="topology",
            resource_id=dashboard.id,
        ),
        format="json",
    )
    assert response.status_code == 400
    assert "resource_type" in response.data


def test_create_rejects_conflicting_dashboard_and_resource_id(
    api_client,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    other = Dashboard.objects.create(
        name="另一个仪表盘",
        directory=dashboard.directory,
        groups=[1],
        created_by="owner",
    )
    response = api_client.post(
        subscription_url,
        _base_payload(
            email_channel,
            dashboard=dashboard.id,
            resource_type=RESOURCE_TYPE_DASHBOARD,
            resource_id=other.id,
        ),
        format="json",
    )
    assert response.status_code == 400
    assert "resource_id" in response.data


def test_list_filter_resource_equals_dashboard_id(
    api_client,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    created = api_client.post(
        subscription_url,
        _base_payload(email_channel, dashboard=dashboard.id),
        format="json",
    )
    assert created.status_code == 201

    by_dashboard = api_client.get(
        subscription_url,
        {"dashboard_id": dashboard.id},
    )
    by_resource = api_client.get(
        subscription_url,
        {
            "resource_type": RESOURCE_TYPE_DASHBOARD,
            "resource_id": dashboard.id,
        },
    )
    assert by_dashboard.status_code == 200
    assert by_resource.status_code == 200
    assert {item["id"] for item in by_dashboard.data} == {
        item["id"] for item in by_resource.data
    }
    assert created.data["id"] in {item["id"] for item in by_resource.data}


def test_list_rejects_conflicting_dashboard_and_resource_filters(
    api_client,
    dashboard,
    subscription_url,
):
    response = api_client.get(
        subscription_url,
        {
            "dashboard_id": dashboard.id,
            "resource_type": RESOURCE_TYPE_DASHBOARD,
            "resource_id": dashboard.id + 1,
        },
    )
    assert response.status_code == 400


def test_execution_freezes_resource_binding_and_render_schema(
    api_client,
    authenticated_user,
    dashboard,
    subscription_url,
    monkeypatch,
    email_channel,
):
    grant_dashboard_view(monkeypatch)
    monkeypatch.setattr(
        "apps.operation_analysis.services.execution_service."
        "DashboardReportExecutionService._dispatch_render",
        lambda execution_id: None,
    )
    created = api_client.post(
        subscription_url,
        _base_payload(email_channel, dashboard=dashboard.id),
        format="json",
    )
    assert created.status_code == 201
    subscription_id = created.data["id"]

    execute = api_client.post(
        f"{subscription_url}{subscription_id}/execute/",
        {"request_id": "binding-1"},
        format="json",
    )
    assert execute.status_code == 201
    execution = DashboardReportExecution.objects.get(
        pk=execute.data["execution_id"]
    )
    assert execution.resource_type == RESOURCE_TYPE_DASHBOARD
    assert execution.resource_id == dashboard.id
    assert execution.snapshot.resource_type == RESOURCE_TYPE_DASHBOARD
    assert execution.snapshot.resource_id == dashboard.id

    from apps.operation_analysis.services.render_snapshot_service import (
        DashboardReportRenderSnapshotService,
    )

    render_snapshot = DashboardReportRenderSnapshotService.create(execution)
    assert render_snapshot.resource_type == RESOURCE_TYPE_DASHBOARD
    assert render_snapshot.resource_id == dashboard.id
    assert (
        render_snapshot.render_schema_version
        == DEFAULT_RENDER_SCHEMA_VERSION
    )
    assert DashboardReportRenderSnapshot.objects.filter(
        execution=execution
    ).exists()

    detail = api_client.get(
        f"/api/v1/operation_analysis/api/dashboard_execution/"
        f"{execution.id}/"
    )
    assert detail.status_code == 200
    assert detail.data["resource_type"] == RESOURCE_TYPE_DASHBOARD
    assert detail.data["resource_id"] == dashboard.id
    assert detail.data["snapshot"]["resource_id"] == dashboard.id
