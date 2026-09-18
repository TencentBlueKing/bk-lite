"""系统 Token 网关认证契约（T2）：前缀判别、五步校验、403 可穿出。"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.base.tests.factories import UserFactory
from apps.core.openapi.testing import bearer, create_api_tenant
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ME_URL = "/openapi/v1/_me"


def _create_system_token(**kwargs):
    from apps.system_mgmt.models import SystemAPIToken

    plaintext = SystemAPIToken.generate_secret()
    SystemAPIToken.objects.create(
        system_id=kwargs.get("system_id", "itsm"),
        name=kwargs.get("name", "ITSM"),
        secret_hash=SystemAPIToken.hash_secret(plaintext),
        scope=kwargs.get("scope", {"mode": "all"}),
        enabled=kwargs.get("enabled", True),
        expires_at=kwargs.get("expires_at"),
        created_by="admin",
        created_by_domain="domain.com",
    )
    return plaintext


def _create_acting_user(team_id, *, username=None, disabled=False, is_active=True):
    user = UserFactory(
        group_list=[team_id],
        is_active=is_active,
        **({"username": username} if username else {}),
    )
    SystemUser.objects.get_or_create(
        username=user.username,
        domain=user.domain,
        defaults={
            "display_name": user.username,
            "email": f"{user.username}@example.com",
            "password": "x",
            "group_list": [team_id],
            "disabled": disabled,
        },
    )
    if disabled or not is_active:
        SystemUser.objects.filter(username=user.username, domain=user.domain).update(
            disabled=disabled,
        )
        user.is_active = is_active
        user.save(update_fields=["is_active"])
    Group.objects.get_or_create(id=team_id, defaults={"name": f"team-{team_id}"})
    return user


def _acting(token, user, team_id):
    return {
        **bearer(token),
        "HTTP_X_BKLITE_ACTING_USER": f"{user.username}@{user.domain}",
        "HTTP_X_BKLITE_ACTING_TEAM": str(team_id),
    }


def test_malformed_bksys_prefix_is_not_treated_as_jwt(client):
    resp = client.get(ME_URL, HTTP_AUTHORIZATION="Bearer bksys_a.b.c")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_INVALID"
    assert "invalid system token" in body["message"]


def test_unknown_system_token_401(client):
    from apps.system_mgmt.models import SystemAPIToken

    token = SystemAPIToken.generate_secret()
    user = _create_acting_user(4)
    resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 401
    assert "invalid system token" in resp.json()["message"]


def test_disabled_system_token_401(client):
    token = _create_system_token(enabled=False)
    user = _create_acting_user(4)
    resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 401
    assert "invalid system token" in resp.json()["message"]


def test_expired_system_token_401(client):
    token = _create_system_token(expires_at=timezone.now() - timedelta(minutes=1))
    user = _create_acting_user(4)
    resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 401
    assert "invalid system token" in resp.json()["message"]


def test_missing_acting_headers_401(client):
    token = _create_system_token()
    resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 401
    assert "acting headers required" in resp.json()["message"]


def test_malformed_acting_headers_401(client):
    token = _create_system_token()
    resp = client.get(
        ME_URL,
        **bearer(token),
        HTTP_X_BKLITE_ACTING_USER="user@",
        HTTP_X_BKLITE_ACTING_TEAM="4",
    )
    assert resp.status_code == 401
    assert "acting headers required" in resp.json()["message"]


def test_acting_user_not_found_401(client):
    token = _create_system_token()
    Group.objects.get_or_create(id=4, defaults={"name": "team-4"})
    resp = client.get(
        ME_URL,
        **bearer(token),
        HTTP_X_BKLITE_ACTING_USER="ghost@domain.com",
        HTTP_X_BKLITE_ACTING_TEAM="4",
    )
    assert resp.status_code == 401
    assert "acting user not found or disabled" in resp.json()["message"]


def test_acting_user_disabled_401(client):
    token = _create_system_token()
    user = _create_acting_user(4, disabled=True)
    resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 401
    assert "acting user not found or disabled" in resp.json()["message"]


def test_acting_team_not_direct_group_403(client):
    token = _create_system_token()
    user = _create_acting_user(4)
    Group.objects.get_or_create(id=9, defaults={"name": "team-9"})
    resp = client.get(ME_URL, **_acting(token, user, 9))
    assert resp.status_code == 403
    assert resp.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_parent_group_child_team_403(client):
    parent, _ = Group.objects.get_or_create(id=20, defaults={"name": "parent-20"})
    Group.objects.get_or_create(id=21, defaults={"name": "child-21", "parent_id": parent.id})
    token = _create_system_token()
    user = _create_acting_user(20)
    resp = client.get(ME_URL, **_acting(token, user, 21))
    assert resp.status_code == 403
    assert resp.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_valid_system_token_uses_acting_subject(client):
    token = _create_system_token(system_id="itsm")
    user = _create_acting_user(4, username="zhangsan")
    resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"] == "zhangsan"
    assert data["domain"] == user.domain
    assert data["credential_type"] == "system_token"
    assert [g["id"] for g in data["groups"]] == [4]
    assert data["user"] != "itsm"
    assert data["caller_system"] == "itsm"


def test_acting_user_without_domain_defaults_to_domain_com(client):
    token = _create_system_token(system_id="itsm")
    user = _create_acting_user(4, username="zhangsan")
    resp = client.get(
        ME_URL,
        **bearer(token),
        HTTP_X_BKLITE_ACTING_USER="zhangsan",
        HTTP_X_BKLITE_ACTING_TEAM="4",
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"] == "zhangsan"
    assert data["domain"] == "domain.com"


def test_personal_token_ignores_acting_headers(client):
    user, token = create_api_tenant(3)
    other = _create_acting_user(8, username="intruder")
    resp = client.get(ME_URL, **_acting(token, other, 8))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"] == user.username
    assert data["credential_type"] == "api_token"
    assert [g["id"] for g in data["groups"]] == [3]


_AUDIT_TEMPLATE = (
    "openapi_access user=%s domain=%s credential=%s token_id=%s token_name=%s "
    "team=%s caller=%s method=%s path=%s status=%s duration_ms=%d size=%d "
    "request_sha256=%s"
)


def _access_log(caplog):
    records = [r for r in caplog.records if isinstance(r.msg, str) and r.msg.startswith("openapi_access")]
    assert records, "expected openapi_access log"
    return records[-1]


def _assert_log_has_no_secret(rec, caplog, secret=None):
    rendered = rec.getMessage()
    blob = " ".join([rendered, caplog.text, str(rec.args)])
    assert "sha256$" not in blob
    assert "bksys_" not in blob
    if secret:
        assert secret not in rendered
        assert secret not in caplog.text
        assert secret not in str(rec.args)


def test_audit_log_caller_is_system_id(client, caplog):
    from apps.system_mgmt.models import SystemAPIToken

    token = _create_system_token(system_id="itsm")
    row = SystemAPIToken.objects.get(secret_hash=SystemAPIToken.hash_secret(token))
    user = _create_acting_user(4, username="zhangsan")
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 200
    rec = _access_log(caplog)
    assert rec.msg == _AUDIT_TEMPLATE
    assert rec.args[0] == "zhangsan"
    assert rec.args[2] == "system_token"
    assert rec.args[3] == row.pk
    assert rec.args[4] == "ITSM"
    assert rec.args[5] == "4"
    assert rec.args[6] == "itsm"
    rendered = rec.getMessage()
    assert f"token_id={row.pk}" in rendered
    assert "token_name=ITSM" in rendered
    assert "caller=itsm" in rendered
    assert "path=/openapi/v1/_me" in rendered
    _assert_log_has_no_secret(rec, caplog, token)
    assert "X-Bklite-Acting" not in caplog.text
    assert "HTTP_X_BKLITE" not in caplog.text


def test_audit_log_personal_token_uses_bound_identity_and_key(client, caplog):
    from apps.base.models.user import UserAPISecret

    user, token = create_api_tenant(3)
    row = UserAPISecret.find_by_api_secret(token)
    row.name = "job-script"
    row.save(update_fields=["name"])
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 200
    rec = _access_log(caplog)
    assert rec.msg == _AUDIT_TEMPLATE
    assert rec.args[0] == user.username
    assert rec.args[2] == "api_token"
    assert rec.args[3] == row.pk
    assert rec.args[4] == "job-script"
    assert rec.args[5] == "3"
    assert rec.args[6] == "-"
    rendered = rec.getMessage()
    assert f"token_id={row.pk}" in rendered
    assert "token_name=job-script" in rendered
    assert "caller=-" in rendered
    _assert_log_has_no_secret(rec, caplog, token)


def test_audit_log_unnamed_personal_token_name_is_dash(client, caplog):
    from apps.base.models.user import UserAPISecret

    _user, token = create_api_tenant(3)
    row = UserAPISecret.find_by_api_secret(token)
    row.name = ""
    row.save(update_fields=["name"])
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 200
    rec = _access_log(caplog)
    assert rec.args[3] == row.pk
    assert rec.args[4] == "-"
    assert "token_name=-" in rec.getMessage()
    _assert_log_has_no_secret(rec, caplog, token)


def test_audit_log_unauthenticated_keeps_identity_dashes(client, caplog):
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL)
    assert resp.status_code == 401
    rec = _access_log(caplog)
    assert rec.msg == _AUDIT_TEMPLATE
    assert rec.args[0] == "-"
    assert rec.args[2] == "-"
    assert rec.args[3] == "-"
    assert rec.args[4] == "-"
    assert rec.args[5] == "-"
    assert rec.args[6] == "-"
    assert "token_id=-" in rec.getMessage()


def test_audit_log_token_name_strips_newlines_without_mutating_row(client, caplog):
    from apps.system_mgmt.models import SystemAPIToken

    token = _create_system_token(system_id="itsm", name="line1\nline2")
    row = SystemAPIToken.objects.get(secret_hash=SystemAPIToken.hash_secret(token))
    user = _create_acting_user(4, username="zhangsan")
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **_acting(token, user, 4))
    assert resp.status_code == 200
    rec = _access_log(caplog)
    assert rec.args[4] == "line1 line2"
    assert "\n" not in rec.args[4]
    assert "\n" not in rec.getMessage()
    row.refresh_from_db()
    assert row.name == "line1\nline2"
    _assert_log_has_no_secret(rec, caplog, token)


def test_audit_log_team_out_of_scope_keeps_system_token_and_acting(client, caplog):
    from apps.system_mgmt.models import SystemAPIToken

    token = _create_system_token(system_id="itsm")
    row = SystemAPIToken.objects.get(secret_hash=SystemAPIToken.hash_secret(token))
    user = _create_acting_user(4, username="zhangsan")
    Group.objects.get_or_create(id=9, defaults={"name": "team-9"})
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **_acting(token, user, 9))
    assert resp.status_code == 403
    rec = _access_log(caplog)
    assert rec.args[0] == "zhangsan"
    assert rec.args[2] == "system_token"
    assert rec.args[3] == row.pk
    assert rec.args[4] == "ITSM"
    assert rec.args[5] == "9"
    assert rec.args[6] == "itsm"
    rendered = rec.getMessage()
    assert "status=403" in rendered
    _assert_log_has_no_secret(rec, caplog, token)


def test_audit_log_missing_acting_headers_keeps_system_token(client, caplog):
    from apps.system_mgmt.models import SystemAPIToken

    token = _create_system_token(system_id="itsm")
    row = SystemAPIToken.objects.get(secret_hash=SystemAPIToken.hash_secret(token))
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 401
    rec = _access_log(caplog)
    assert rec.args[0] == "-"
    assert rec.args[2] == "system_token"
    assert rec.args[3] == row.pk
    assert rec.args[4] == "ITSM"
    assert rec.args[5] == "-"
    assert rec.args[6] == "itsm"
    _assert_log_has_no_secret(rec, caplog, token)


def test_audit_log_unknown_system_token_stays_dashes(client, caplog):
    from apps.system_mgmt.models import SystemAPIToken

    token = SystemAPIToken.generate_secret()
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 401
    rec = _access_log(caplog)
    assert rec.args[0] == "-"
    assert rec.args[2] == "-"
    assert rec.args[3] == "-"
    assert rec.args[6] == "-"
    _assert_log_has_no_secret(rec, caplog, token)
