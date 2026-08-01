import hashlib
from datetime import timedelta

import jwt
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory

from apps.operation_analysis.models.datasource_models import (
    DataSourceAPIModel,
    NameSpace,
)
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
from apps.operation_analysis.services.render_scope_service import (
    DashboardReportRenderScopeError,
    DashboardReportRenderScopeService,
)
from apps.system_mgmt.models import User as SystemUser


pytestmark = pytest.mark.django_db


def _stub_render_auth_context(
    monkeypatch,
    *,
    username: str,
    domain: str,
    permission: dict | None = None,
    group_list: list | None = None,
):
    """Render 路径不再走 verify_token，改为 stub 实时授权上下文。"""

    def fake_context(user):
        return {
            "username": username,
            "display_name": username,
            "domain": domain,
            "email": "render-token@example.com",
            "is_superuser": False,
            "group_list": group_list
            if group_list is not None
            else [{"id": 1, "name": "Default Team"}],
            "group_tree": [],
            "roles": [],
            "role_ids": [],
            "locale": "en",
            "timezone": "Asia/Shanghai",
            "permission": permission
            if permission is not None
            else {
                "ops-analysis": [
                    "view-View",
                    "data_source-View",
                    "namespace-View",
                ]
            },
        }

    monkeypatch.setattr(
        "apps.operation_analysis.services.render_scope_service.build_user_authorization_context",
        fake_context,
    )


def _stub_datasource_instance_rules(monkeypatch, *, team_ids=None, instance=None):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {
            "team": team_ids if team_ids is not None else [1],
            "instance": instance if instance is not None else [],
        },
    )


@pytest.fixture
def running_execution(authenticated_user):
    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        domain=authenticated_user.domain,
        defaults={
            "display_name": authenticated_user.username,
            "email": "render-token@example.com",
            "password": "unused",
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
        creator_domain=authenticated_user.domain,
        team_id=1,
        name="Token 测试订阅",
        recipient_email="ops@example.com",
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=timezone.now(),
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        execution_team_id=1,
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
        widget_manifest=[
            {"widget_id": "chart-1", "widget_type": "line", "datasource_id": 17}
        ],
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
        creator_domain=authenticated_user.domain,
        team_id=1,
        name="另一 Token 订阅",
        recipient_email="ops@example.com",
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=timezone.now(),
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        execution_team_id=1,
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
    assert claims["token_type"] == "dashboard_report_render"
    assert claims["render_execution_id"] == running_execution.id
    assert claims["render_snapshot_id"] == running_execution.render_snapshot.id
    assert claims["creator_username"] == running_execution.creator
    assert claims["creator_domain"] == running_execution.creator_domain

    with pytest.raises(DashboardReportRenderTokenError):
        DashboardReportRenderTokenService.consume(
            execution_id=running_execution.id,
            plaintext=issued.plaintext,
        )


def test_render_token_resolves_creator_by_username_and_domain(
    running_execution, monkeypatch
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    SystemUser.objects.create(
        username=running_execution.creator,
        domain="other.example",
        display_name="同名其他域用户",
        email="other-domain@example.com",
        password="unused",
        group_list=[{"id": 1, "name": "Default Team"}],
    )

    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )

    assert session["domain"] == running_execution.creator_domain


def test_new_attempt_invalidates_existing_render_session(
    running_execution, monkeypatch
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    first = DashboardReportRenderTokenService.issue(
        running_execution, attempt_no=1
    )
    old_session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=first.plaintext,
    )
    DashboardReportRenderTokenService.issue(running_execution, attempt_no=2)

    request = APIRequestFactory().get(
        f"/api/v1/operation_analysis/api/dashboard_execution/{running_execution.id}/render-input/"
    )
    with pytest.raises(DashboardReportRenderScopeError, match="已失效"):
        DashboardReportRenderScopeService.authorize_request(
            request, old_session["token"]
        )


def test_disabled_creator_invalidates_existing_render_session(
    running_execution, monkeypatch
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    SystemUser.objects.filter(
        username=running_execution.creator,
        domain=running_execution.creator_domain,
    ).update(disabled=True)

    request = APIRequestFactory().get(
        f"/api/v1/operation_analysis/api/dashboard_execution/{running_execution.id}/render-input/"
    )
    with pytest.raises(DashboardReportRenderScopeError, match="已失效"):
        DashboardReportRenderScopeService.authorize_request(
            request, session["token"]
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


def test_render_session_rejects_ordinary_api_and_cross_execution(
    running_execution,
    monkeypatch,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    factory = APIRequestFactory()

    with pytest.raises(DashboardReportRenderScopeError):
        DashboardReportRenderScopeService.authorize_request(
            factory.get("/api/v1/operation_analysis/api/dashboard_subscription/"),
            session["token"],
        )
    with pytest.raises(DashboardReportRenderScopeError):
        DashboardReportRenderScopeService.authorize_request(
            factory.get(
                "/api/v1/operation_analysis/api/dashboard_execution/999/render-input/"
            ),
            session["token"],
        )


def test_auth_middleware_rejects_render_session_on_ordinary_api(
    running_execution,
    monkeypatch,
    settings,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    settings.MIDDLEWARE = (
        *settings.MIDDLEWARE,
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    )
    _stub_render_auth_context(
        monkeypatch,
        username=running_execution.creator,
        domain=running_execution.creator_domain,
    )

    response = APIClient().get(
        "/api/v1/operation_analysis/api/dashboard_subscription/",
        HTTP_AUTHORIZATION=f"Bearer {session['token']}",
    )

    assert response.status_code in {401, 403}


def test_verify_token_rejects_render_jwt_as_login_credential(
    running_execution,
    monkeypatch,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    from apps.system_mgmt.nats.common import _verify_token

    with pytest.raises(Exception, match="Render token"):
        _verify_token(session["token"])


def test_render_session_does_not_create_ordinary_login_session(
    running_execution,
    monkeypatch,
    settings,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    settings.MIDDLEWARE = (
        *settings.MIDDLEWARE,
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    )
    _stub_render_auth_context(
        monkeypatch,
        username=running_execution.creator,
        domain=running_execution.creator_domain,
    )
    client = APIClient()

    response = client.get(
        f"/api/v1/operation_analysis/api/dashboard_execution/{running_execution.id}/render-input/",
        HTTP_AUTHORIZATION=f"Bearer {session['token']}",
    )

    assert response.status_code == 200, response.data
    assert "sessionid" not in response.cookies
    assert "sessionid" not in client.cookies


def test_render_session_rechecks_creator_permission_on_widget_query(
    running_execution,
    monkeypatch,
    settings,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    DataSourceAPIModel.objects.create(
        id=17,
        name="Render Permission DataSource",
        rest_api="render/query",
        groups=[1],
    )
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    settings.MIDDLEWARE = (
        *settings.MIDDLEWARE,
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    )
    _stub_render_auth_context(
        monkeypatch,
        username=running_execution.creator,
        domain=running_execution.creator_domain,
        permission={"ops-analysis": []},
    )
    _stub_datasource_instance_rules(monkeypatch, team_ids=[1])

    response = APIClient().post(
        "/api/v1/operation_analysis/api/data_source/get_source_data/17/",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {session['token']}",
    )

    assert response.status_code == 403


def test_render_session_rejects_widget_query_after_creator_leaves_team(
    running_execution,
    monkeypatch,
    settings,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    DataSourceAPIModel.objects.create(
        id=17,
        name="Render Team DataSource",
        rest_api="render/query",
        groups=[1],
    )
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    SystemUser.objects.filter(
        username=running_execution.creator,
        domain=running_execution.creator_domain,
    ).update(group_list=[])
    settings.MIDDLEWARE = (
        *settings.MIDDLEWARE,
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    )
    _stub_render_auth_context(
        monkeypatch,
        username=running_execution.creator,
        domain=running_execution.creator_domain,
        group_list=[],
    )
    _stub_datasource_instance_rules(monkeypatch, team_ids=[1])

    response = APIClient().post(
        "/api/v1/operation_analysis/api/data_source/get_source_data/17/",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {session['token']}",
    )

    assert response.status_code in {401, 403}


def test_render_session_rejects_widget_query_without_instance_permission(
    running_execution,
    monkeypatch,
    settings,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    DataSourceAPIModel.objects.create(
        id=17,
        name="Render Instance DataSource",
        rest_api="render/query",
        groups=[1],
    )
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    settings.MIDDLEWARE = (
        *settings.MIDDLEWARE,
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    )
    _stub_render_auth_context(
        monkeypatch,
        username=running_execution.creator,
        domain=running_execution.creator_domain,
    )
    _stub_datasource_instance_rules(monkeypatch, team_ids=[], instance=[])

    response = APIClient().post(
        "/api/v1/operation_analysis/api/data_source/get_source_data/17/",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {session['token']}",
    )

    assert response.status_code == 403


def test_legacy_render_claims_are_detected_and_fail_closed():
    token = jwt.encode(
        {
            "user_id": 1,
            "render_execution_id": 42,
            "render_attempt_no": 1,
        },
        "legacy-secret",
        algorithm="HS256",
    )

    from apps.core.middlewares.auth_middleware import AuthMiddleware

    assert AuthMiddleware._is_render_token_candidate(token)


def test_render_session_allows_only_manifest_datasource(
    running_execution,
    monkeypatch,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    factory = APIRequestFactory()

    DashboardReportRenderScopeService.authorize_request(
        factory.get(
            f"/api/v1/operation_analysis/api/dashboard_execution/{running_execution.id}/render-input/"
        ),
        session["token"],
    )
    datasource_query_request = factory.post(
        "/api/v1/operation_analysis/api/data_source/get_source_data/17/",
        {},
        format="json",
    )
    DashboardReportRenderScopeService.authorize_request(
        datasource_query_request,
        session["token"],
    )
    assert datasource_query_request._api_current_team == 1
    with pytest.raises(DashboardReportRenderScopeError):
        DashboardReportRenderScopeService.authorize_request(
            factory.post(
                "/api/v1/operation_analysis/api/data_source/get_source_data/18/",
                {},
                format="json",
            ),
            session["token"],
        )


def test_render_session_allows_only_namespaces_of_manifest_datasources(
    running_execution,
    monkeypatch,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    allowed_namespace = NameSpace.objects.create(
        name="Render Allowed Namespace",
        account="render",
        password="secret",
        domain="nats.example.com",
    )
    unrelated_namespace = NameSpace.objects.create(
        name="Render Unrelated Namespace",
        account="other",
        password="secret",
        domain="other.example.com",
    )
    datasource = DataSourceAPIModel.objects.create(
        id=17,
        name="Render DataSource",
        rest_api="render/query",
    )
    datasource.namespaces.add(allowed_namespace)
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    factory = APIRequestFactory()

    DashboardReportRenderScopeService.authorize_request(
        factory.get(
            "/api/v1/operation_analysis/api/namespace/",
            {"ids": str(allowed_namespace.id)},
        ),
        session["token"],
    )
    with pytest.raises(DashboardReportRenderScopeError):
        DashboardReportRenderScopeService.authorize_request(
            factory.get(
                "/api/v1/operation_analysis/api/namespace/",
                {"ids": str(unrelated_namespace.id)},
            ),
            session["token"],
        )


def test_render_session_can_load_manifest_namespace_through_http(
    running_execution,
    monkeypatch,
    settings,
):
    monkeypatch.setenv("SECRET_KEY", "render-token-test-secret")
    namespace = NameSpace.objects.create(
        name="Render HTTP Namespace",
        account="render",
        password="secret",
        domain="nats.example.com",
    )
    datasource = DataSourceAPIModel.objects.create(
        id=17,
        name="Render HTTP DataSource",
        rest_api="render/http-query",
    )
    datasource.namespaces.add(namespace)
    issued = DashboardReportRenderTokenService.issue(running_execution)
    session = DashboardReportRenderTokenService.consume(
        execution_id=running_execution.id,
        plaintext=issued.plaintext,
    )
    settings.MIDDLEWARE = (
        *settings.MIDDLEWARE,
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    )
    _stub_render_auth_context(
        monkeypatch,
        username=running_execution.creator,
        domain=running_execution.creator_domain,
    )

    response = APIClient().get(
        "/api/v1/operation_analysis/api/namespace/",
        {"ids": str(namespace.id)},
        HTTP_AUTHORIZATION=f"Bearer {session['token']}",
    )

    assert response.status_code == 200, response.data
    assert [item["id"] for item in response.data] == [namespace.id]


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
