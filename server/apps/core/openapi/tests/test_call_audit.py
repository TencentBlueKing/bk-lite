"""OpenAPI 网关调用日志写侧：invoke / ForwardAuth 终态落库。"""

import logging
import traceback
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.base.models.user import UserAPISecret
from apps.core.logger import SafeLogException
from apps.core.openapi import renderer
from apps.core.openapi.testing import acting_headers, bearer, create_api_tenant, create_system_tenant
from apps.system_mgmt.models import OpenAPICallLog

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PATCH_URL = "/openapi/v1/patch-mgmt/module-data"
ME_URL = "/openapi/v1/_me"
DOCS_URL = "/openapi/v1/_docs"
PROVIDER_URL = "/openapi/v1/_provider/traefik"
AUTH_URL = "/openapi/v1/_auth"
TEST_SECRET = "openapi-test-secret-key"
SAMPLE_ENTRY = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "auth_mode": "trusted-header",
    "shared_secret_ref": "env:TEST_ITSM_SECRET",
    "required_roles": [],
    "enabled": True,
}


@pytest.fixture
def registered_itsm(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_ITSM_SECRET", "s3cret")
    monkeypatch.setattr(
        "apps.core.openapi.renderer.fetch_entries", lambda: {"itsm": dict(SAMPLE_ENTRY)}
    )
    renderer.refresh_snapshot()


@pytest.fixture
def jwt_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")


def _row_values(row):
    return [
        row.username,
        row.credential_type,
        row.token_name,
        row.system_id,
        row.api_kind,
        row.method,
        row.path,
        row.error_code,
        row.source_ip,
    ]


def _assert_no_sentinels_or_secrets(row, *secrets):
    for value in _row_values(row):
        assert value != "-"
        for secret in secrets:
            if secret:
                assert secret not in str(value)


def test_invoke_api_token_success_writes_call_log(client):
    user, token = create_api_tenant(1)
    secret = UserAPISecret.find_by_api_secret(token)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 1},
        REMOTE_ADDR="203.0.113.9",
        **bearer(token),
    )
    assert resp.status_code == 200
    row = OpenAPICallLog.objects.get()
    assert row.api_kind == OpenAPICallLog.API_KIND_INTERNAL
    assert row.method == "GET"
    assert row.path == PATCH_URL
    assert row.credential_type == "api_token"
    assert row.username == user.username
    assert row.token_id == secret.pk
    assert row.token_name == secret.name
    assert row.system_id == ""
    assert row.team_id == 1
    assert row.http_status == 200
    assert row.error_code == ""
    assert row.source_ip == "203.0.113.9"
    _assert_no_sentinels_or_secrets(row, token)
    assert "?" not in row.path


def test_invoke_system_token_and_jwt_success_write_identity(client, jwt_env):
    from apps.core.openapi.tests.test_gateway import make_jwt, make_jwt_tenant

    sys_user, sys_token = create_system_tenant(8, system_id="itsm")
    sys_resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 8},
        **acting_headers(sys_token, sys_user, 8),
    )
    assert sys_resp.status_code == 200
    sys_row = OpenAPICallLog.objects.latest("id")
    assert sys_row.credential_type == "system_token"
    assert sys_row.username == sys_user.username
    assert sys_row.system_id == "itsm"
    assert sys_row.api_kind == OpenAPICallLog.API_KIND_INTERNAL
    assert sys_row.team_id == 8
    assert sys_row.token_id is not None
    _assert_no_sentinels_or_secrets(sys_row, sys_token)

    jwt_user = make_jwt_tenant(5)
    jwt_token = make_jwt(jwt_user)
    jwt_resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 5},
        HTTP_AUTHORIZATION=f"Bearer {jwt_token}",
    )
    assert jwt_resp.status_code == 200
    jwt_row = OpenAPICallLog.objects.exclude(id=sys_row.id).get()
    assert jwt_row.credential_type == ""
    assert jwt_row.username == ""
    assert jwt_row.token_id is None
    assert jwt_row.token_name == ""
    assert jwt_row.system_id == ""
    assert jwt_row.team_id is None
    assert jwt_row.api_kind == OpenAPICallLog.API_KIND_INTERNAL
    _assert_no_sentinels_or_secrets(jwt_row, jwt_token)


def test_me_docs_and_provider_do_not_write_call_log(client, monkeypatch):
    monkeypatch.setenv("OPENAPI_PROVIDER_TOKEN", "provider-token")
    _, token = create_api_tenant(1)
    assert client.get(ME_URL, **bearer(token)).status_code == 200
    assert client.get(DOCS_URL, **bearer(token)).status_code == 200
    resp = client.get(PROVIDER_URL, HTTP_X_PROVIDER_TOKEN="provider-token")
    assert resp.status_code == 200
    assert OpenAPICallLog.objects.count() == 0


PERSIST_FAIL_TEMPLATE = (
    "event=openapi_call_log_persist_failed failed_stage=persist error_type=%s token_id=%s path=%s"
)
ACCESS_FAIL_TEMPLATE = (
    "event=openapi_access_log_failed failed_stage=access_log error_type=%s token_id=%s path=%s"
)
_LOG_SECRET_SENTINEL = "openapi-audit-secret-sentinel"


@contextmanager
def _capture_openapi_formatted_logs():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log = logging.getLogger("openapi")
    log.addHandler(handler)
    try:
        yield stream
    finally:
        log.removeHandler(handler)


def _owned_traceback_errors(records, template):
    return [
        rec
        for rec in records
        if rec.name == "openapi" and rec.levelno >= logging.ERROR and rec.exc_info and rec.msg == template
    ]


def test_persist_failure_does_not_change_invoke_response(client, caplog):
    _, token = create_api_tenant(1)
    secret = UserAPISecret.find_by_api_secret(token)
    original = RuntimeError(f"db down {_LOG_SECRET_SENTINEL}")

    def boom(*args, **kwargs):
        raise original

    caplog.set_level(logging.DEBUG, logger="openapi")
    with _capture_openapi_formatted_logs() as rendered, patch(
        "apps.system_mgmt.models.OpenAPICallLog.objects.create",
        side_effect=boom,
    ):
        resp = client.get(
            PATCH_URL,
            {"module": "patch_target", "group_id": 1},
            **bearer(token),
        )
    output = rendered.getvalue()
    assert resp.status_code == 200
    assert resp.json()["result"] is True
    assert OpenAPICallLog.objects.count() == 0
    assert str(original) == f"db down {_LOG_SECRET_SENTINEL}"
    owned = _owned_traceback_errors(caplog.records, PERSIST_FAIL_TEMPLATE)
    assert len(owned) == 1
    rec = owned[0]
    assert rec.args == ("RuntimeError", secret.pk, PATCH_URL)
    message = rec.getMessage()
    assert "failed_stage=persist" in message
    assert "error_type=RuntimeError" in message
    assert f"token_id={secret.pk}" in message
    assert f"path={PATCH_URL}" in message
    assert rec.exc_info[0] is SafeLogException
    assert rec.exc_info[1] is not original
    assert rec.exc_info[2] is original.__traceback__
    assert str(rec.exc_info[1]) == "RuntimeError"
    assert "boom" in [frame.name for frame in traceback.extract_tb(rec.exc_info[2])]
    assert _LOG_SECRET_SENTINEL not in message
    assert token not in message
    assert "Traceback" in output
    assert "boom" in output
    assert _LOG_SECRET_SENTINEL not in output
    assert token not in output
    traceback_errors = [r for r in caplog.records if r.name == "openapi" and r.levelno >= logging.ERROR and r.exc_info]
    assert traceback_errors == owned


def test_access_log_failure_still_persists_call_and_response(client, caplog):
    user, token = create_api_tenant(1)
    secret = UserAPISecret.find_by_api_secret(token)
    original = RuntimeError(f"info down {_LOG_SECRET_SENTINEL}")

    def boom(*args, **kwargs):
        raise original

    caplog.set_level(logging.DEBUG, logger="openapi")
    with _capture_openapi_formatted_logs() as rendered, patch(
        "apps.core.openapi.views.logger.info",
        side_effect=boom,
    ):
        resp = client.get(
            PATCH_URL,
            {"module": "patch_target", "group_id": 1},
            **bearer(token),
        )
    output = rendered.getvalue()
    assert resp.status_code == 200
    assert resp.json()["result"] is True
    row = OpenAPICallLog.objects.get()
    assert row.username == user.username
    assert row.token_id == secret.pk
    assert str(original) == f"info down {_LOG_SECRET_SENTINEL}"
    owned = _owned_traceback_errors(caplog.records, ACCESS_FAIL_TEMPLATE)
    assert len(owned) == 1
    rec = owned[0]
    assert rec.args == ("RuntimeError", secret.pk, PATCH_URL)
    message = rec.getMessage()
    assert "failed_stage=access_log" in message
    assert "error_type=RuntimeError" in message
    assert rec.exc_info[0] is SafeLogException
    assert rec.exc_info[2] is original.__traceback__
    assert str(rec.exc_info[1]) == "RuntimeError"
    assert _LOG_SECRET_SENTINEL not in message
    assert token not in message
    assert "Traceback" in output
    assert _LOG_SECRET_SENTINEL not in output
    assert token not in output
    traceback_errors = [r for r in caplog.records if r.name == "openapi" and r.levelno >= logging.ERROR and r.exc_info]
    assert traceback_errors == owned


def test_unfinished_response_still_writes_internal_error(client):
    _, token = create_api_tenant(1)
    with patch("apps.core.openapi.views._invoke", side_effect=RuntimeError("boom")):
        resp = client.get(
            PATCH_URL,
            {"module": "patch_target", "group_id": 1},
            **bearer(token),
        )
    assert resp.status_code == 500
    row = OpenAPICallLog.objects.get()
    assert row.http_status == 500
    assert row.error_code == "INTERNAL_ERROR"
    assert row.username != ""
    assert row.api_kind == OpenAPICallLog.API_KIND_INTERNAL


def test_expired_personal_token_writes_bound_identity_and_stays_401(client):
    user, token = create_api_tenant(1)
    secret = UserAPISecret.find_by_api_secret(token)
    UserAPISecret.objects.filter(pk=secret.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    resp = client.get(PATCH_URL, {"module": "patch_target", "group_id": 1}, **bearer(token))
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.credential_type == "api_token"
    assert row.token_id == secret.pk
    assert row.token_name == secret.name
    assert row.username == user.username
    assert row.team_id == 1
    assert row.http_status == 401
    assert row.error_code == "AUTH_INVALID"
    assert client.get(ME_URL, **bearer(token)).status_code == 401


def test_disabled_personal_token_owner_still_writes_bound_user(client):
    user, token = create_api_tenant(1)
    secret = UserAPISecret.find_by_api_secret(token)
    user.is_active = False
    user.save(update_fields=["is_active"])
    resp = client.get(PATCH_URL, {"module": "patch_target", "group_id": 1}, **bearer(token))
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.credential_type == "api_token"
    assert row.token_id == secret.pk
    assert row.username == user.username
    assert row.team_id == 1


def test_expired_and_disabled_system_token_write_key_without_unvalidated_user(client):
    from apps.core.openapi.tests.test_system_token_auth import _acting, _create_acting_user, _create_system_token

    expired = _create_system_token(expires_at=timezone.now() - timedelta(minutes=1), name="expired-itsm")
    acting = _create_acting_user(4)
    resp = client.get(PATCH_URL, **_acting(expired, acting, 4))
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.credential_type == "system_token"
    assert row.token_name == "expired-itsm"
    assert row.system_id == "itsm"
    assert row.token_id is not None
    assert row.username == acting.username

    OpenAPICallLog.objects.all().delete()
    disabled = _create_system_token(enabled=False, name="disabled-itsm", system_id="cmdb")
    resp = client.get(PATCH_URL, **bearer(disabled))
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.credential_type == "system_token"
    assert row.token_name == "disabled-itsm"
    assert row.system_id == "cmdb"
    assert row.username == ""
    assert row.team_id is None


def test_system_token_acting_failures_do_not_write_header_username(client):
    from apps.core.openapi.tests.test_system_token_auth import _create_system_token

    token = _create_system_token(name="live-itsm")
    resp = client.get(PATCH_URL, **bearer(token))
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.username == ""
    assert row.token_name == "live-itsm"
    assert row.credential_type == "system_token"

    OpenAPICallLog.objects.all().delete()
    resp = client.get(
        PATCH_URL,
        **bearer(token),
        HTTP_X_BKLITE_ACTING_USER="ghost@domain.com",
        HTTP_X_BKLITE_ACTING_TEAM="4",
    )
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.username == ""
    assert "ghost" not in row.username


def test_system_token_team_out_of_scope_keeps_validated_user(client):
    user, token = create_system_tenant(8)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 9},
        **acting_headers(token, user, 9),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "TEAM_OUT_OF_SCOPE"
    row = OpenAPICallLog.objects.get()
    assert row.username == user.username
    assert row.team_id == 9
    assert row.error_code == "TEAM_OUT_OF_SCOPE"


def test_unknown_credential_writes_empty_identity(client):
    resp = client.get(PATCH_URL)
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.username == ""
    assert row.credential_type == ""
    assert row.token_id is None
    assert row.token_name == ""
    assert row.system_id == ""
    assert row.team_id is None


def test_invoke_does_not_store_request_body(client):
    _, token = create_api_tenant(1)
    payload = {"module": "patch_target", "secret": "super-secret-body"}
    client.get(PATCH_URL, payload, **bearer(token))
    row = OpenAPICallLog.objects.get()
    dumped = " ".join(str(v) for v in _row_values(row))
    assert "super-secret-body" not in dumped
    assert token not in dumped


def test_forward_auth_writes_forwarded_target_not_callback(client, registered_itsm):
    _, token = create_api_tenant(9)
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create?x=1",
        HTTP_X_FORWARDED_METHOD="POST",
        HTTP_X_FORWARDED_FOR="198.51.100.10",
        REMOTE_ADDR="10.0.0.8",
        **bearer(token),
    )
    assert resp.status_code == 200
    row = OpenAPICallLog.objects.get()
    assert row.api_kind == OpenAPICallLog.API_KIND_EXTERNAL
    assert row.method == "POST"
    assert row.path == "/openapi/v1/itsm/tickets/create"
    assert "?" not in row.path
    assert row.path != AUTH_URL
    assert row.http_status == 200
    assert row.error_code == ""
    assert row.source_ip == "198.51.100.10"


def test_forward_auth_missing_method_is_empty_and_failures_write(client, registered_itsm):
    _, token = create_api_tenant(9)
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create",
        **bearer(token),
    )
    assert resp.status_code == 200
    row = OpenAPICallLog.objects.get()
    assert row.method == ""

    OpenAPICallLog.objects.all().delete()
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/nonexistent/x",
        **bearer(token),
    )
    assert resp.status_code == 404
    row = OpenAPICallLog.objects.get()
    assert row.api_kind == ""
    assert row.error_code == "NOT_FOUND"
    assert row.http_status == 404

    OpenAPICallLog.objects.all().delete()
    with patch(
        "apps.system_mgmt.models.OpenAPICallLog.objects.create",
        side_effect=RuntimeError("db down"),
    ):
        resp = client.get(
            AUTH_URL,
            HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create",
            HTTP_X_FORWARDED_METHOD="GET",
            **bearer(token),
        )
    assert resp.status_code == 200


def test_forward_auth_unauthenticated_writes_empty_identity(client, registered_itsm):
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create?x=1",
        HTTP_X_FORWARDED_METHOD="GET",
    )
    assert resp.status_code == 401
    row = OpenAPICallLog.objects.get()
    assert row.api_kind == OpenAPICallLog.API_KIND_EXTERNAL
    assert row.method == "GET"
    assert row.path == "/openapi/v1/itsm/tickets/create"
    assert row.http_status == 401
    assert row.error_code == "AUTH_INVALID"
    assert row.username == ""
    assert row.credential_type == ""
    assert row.token_id is None


def test_forward_auth_scope_denied_writes_row(client, registered_itsm):
    user, token = create_api_tenant(9)
    UserAPISecret.objects.filter(
        username=user.username, domain=user.domain, team=9
    ).update(scope={"mode": "allowlist", "endpoints": ["GET cmdb/classifications"]})
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create",
        HTTP_X_FORWARDED_METHOD="POST",
        **bearer(token),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "SCOPE_DENIED"
    row = OpenAPICallLog.objects.get()
    assert row.api_kind == OpenAPICallLog.API_KIND_EXTERNAL
    assert row.method == "POST"
    assert row.http_status == 403
    assert row.error_code == "SCOPE_DENIED"
    assert row.username == user.username
    assert row.credential_type == "api_token"
