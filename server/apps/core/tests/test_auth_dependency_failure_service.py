"""鉴权依赖失败不能冒充凭据失效，也不能在错误处理时再次查库。"""

import logging
import os
import sys
import time
from types import SimpleNamespace

import pytest
from django.db import InterfaceError, OperationalError
from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import path
from django.utils.functional import SimpleLazyObject

from apps.core.backends import AuthBackend
from apps.core.middlewares.auth_middleware import AuthMiddleware
from apps.core.utils.custom_error import DoesNotExist


def protected_view(request):
    return JsonResponse({"result": True})


urlpatterns = [path("protected/", protected_view)]


@pytest.mark.parametrize("error_type,status", [(OperationalError, 503), (InterfaceError, 503), (RuntimeError, 500)])
def test_dependency_failure_http_status_and_safe_single_log(settings, monkeypatch, caplog, error_type, status):
    from apps.core.middlewares import auth_middleware as module

    sentinel = "secret-must-not-appear-6443"
    error = error_type(sentinel)

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(module.auth, "authenticate", fail)
    with override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=["apps.core.middlewares.auth_middleware.AuthMiddleware"]):
        response = Client().get("/protected/", **{settings.AUTH_TOKEN_HEADER_NAME: "test-token"})
    assert response.status_code == status
    assert response.json()["result"] is False
    assert sentinel not in response.content.decode()
    records = [record for record in caplog.records if record.name == "app" and record.levelno >= logging.ERROR]
    assert len(records) == 1
    record = records[0]
    assert record.exc_info[2] is error.__traceback__
    assert record.args
    assert "failed_stage=" in record.getMessage() and "error_type=" in record.getMessage()
    assert sentinel not in logging.Formatter().format(record)


@pytest.mark.parametrize("outcome,status", [(None, 401), (DoesNotExist("missing"), 460), (OperationalError("busy"), 503)])
def test_error_response_never_evaluates_lazy_session_user(settings, monkeypatch, outcome, status):
    from apps.core.middlewares import auth_middleware as module

    attempts = []

    def load_session_user():
        attempts.append(True)
        raise OperationalError("session database unavailable")

    def authenticate(**kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(module.auth, "authenticate", authenticate)
    request = SimpleNamespace(path="/protected/", META={settings.AUTH_TOKEN_HEADER_NAME: "test-token"}, user=SimpleLazyObject(load_session_user))
    response = AuthMiddleware(lambda request: None).process_view(request, protected_view, [], {})
    assert response.status_code == status
    assert attempts == []


@pytest.mark.parametrize("stage", ["verify", "rules", "user"])
@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_backend_preserves_database_failure_identity(monkeypatch, stage, error_type):
    from apps.core import backends

    error = error_type("database unavailable")
    backend = AuthBackend()

    def fail(*args, **kwargs):
        raise error

    client = SimpleNamespace(verify_token=lambda token: {"result": True, "data": {"username": "test"}}, get_user_rules=lambda *args: {})
    monkeypatch.setattr(backends, "SystemMgmt", lambda: client)
    if stage == "verify":
        client.verify_token = fail
    elif stage == "rules":
        client.get_user_rules = fail
    else:
        monkeypatch.setattr(backends.User._default_manager, "get_or_create", fail)
    with pytest.raises(error_type) as caught:
        backend.authenticate(request=SimpleNamespace(COOKIES={"current_team": "1"}), token="test-token")
    assert caught.value is error


@pytest.mark.parametrize("failure,status", [("scope", 401), ("database", 503), (None, 200)])
def test_render_scope_keeps_credential_failure_separate_from_database_failure(settings, monkeypatch, failure, status):
    """共享中间件仍保留 Render JWT 原有的拒绝与成功契约。"""

    class RenderScopeError(RuntimeError):
        pass

    def authorize(request, token):
        if failure == "scope":
            raise RenderScopeError("scope denied")
        if failure == "database":
            raise OperationalError("database unavailable")
        return {"execution_id": 1}

    service = SimpleNamespace(authorize_request=authorize, resolve_request_user=lambda *args: SimpleNamespace(locale="en"))
    monkeypatch.setitem(
        sys.modules,
        "apps.operation_analysis.services.render_scope_service",
        SimpleNamespace(
            DashboardReportRenderScopeError=RenderScopeError,
            DashboardReportRenderScopeService=service,
        ),
    )
    monkeypatch.setattr(AuthMiddleware, "_is_render_token_candidate", lambda self, token: True)
    with override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=["apps.core.middlewares.auth_middleware.AuthMiddleware"]):
        response = Client().get("/protected/", **{settings.AUTH_TOKEN_HEADER_NAME: "render-test-token"})
    assert response.status_code == status


def test_missing_token_does_not_load_session_user(settings):
    def fail():
        raise AssertionError("错误响应不得读取 session 用户")

    request = SimpleNamespace(path="/protected/", META={}, user=SimpleLazyObject(fail))
    assert AuthMiddleware(lambda request: None).process_view(request, protected_view, [], {}).status_code == 401


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(os.getenv("RUN_ISOLATED_PG_EXHAUSTION") != "1", reason="仅允许在独占的一次性 PostgreSQL 容器中运行")
def test_real_pg_exhaustion_returns_503_and_recovers_without_relogin(settings, monkeypatch):
    """显式启用、最多 32 个连接，禁止在共享或生产数据库上运行。"""
    import jwt
    from django.db import connection, models

    from apps.system_mgmt.models import User

    class PgSetting(models.Model):
        name = models.TextField(primary_key=True)
        setting = models.TextField()

        class Meta:
            app_label = "base"
            managed = False
            db_table = "pg_settings"

    assert connection.vendor == "postgresql"
    limit = int(PgSetting.objects.get(name="max_connections").setting)
    assert limit <= 32, "必须使用低连接上限的一次性数据库"
    user = User.objects.create(username="connection-test", domain="test.local")
    monkeypatch.setenv("SECRET_KEY", settings.SECRET_KEY)
    token = jwt.encode({"user_id": user.pk, "jti": "isolated-test", "exp": int(time.time()) + 600}, settings.SECRET_KEY, algorithm="HS256")
    holders = []
    middleware = [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "apps.core.middlewares.auth_middleware.AuthMiddleware",
    ]
    with override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=middleware, AUTHENTICATION_BACKENDS=["apps.core.backends.AuthBackend"]):
        client = Client()
        headers = {settings.AUTH_TOKEN_HEADER_NAME: token}
        assert client.get("/protected/", **headers).status_code == 200
        connection.close()
        try:
            for _ in range(limit):
                holder = connection.copy()
                holders.append(holder)
                holder.ensure_connection()
            response = client.get("/protected/", **headers)
            assert response.status_code == 503
            assert response.json()["result"] is False
        finally:
            for holder in holders:
                holder.close()
        # 原 Cookie、原 Token，无需重新登录即可恢复。
        assert client.get("/protected/", **headers).status_code == 200
