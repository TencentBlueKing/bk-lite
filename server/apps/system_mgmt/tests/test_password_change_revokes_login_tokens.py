"""改密后作废改密前签发的登录 JWT，并只在自助改密时换发当前会话。"""

import json
import time
import types
from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.constants import PASSWORD_CHANGED_ERROR_CODE, PASSWORD_CHANGED_TOKEN_MESSAGE
from apps.system_mgmt.models import User
from apps.system_mgmt.nats.auth import verify_token
from apps.system_mgmt.nats.common import _verify_token
from apps.system_mgmt.nats.login import reset_pwd
from apps.system_mgmt.viewset.user_viewset import UserViewSet

pytestmark = pytest.mark.django_db


def _user(username="pwd-rotate-user"):
    return User.objects.create(
        username=username,
        display_name="Pwd Rotate",
        email=f"{username}@example.com",
        password=make_password("OldP@ssw0rd!"),
        domain="domain.com",
        disabled=False,
        group_list=[],
        role_list=[],
    )


def _token(user, login_time, *, include_login_time=True):
    now = int(time.time())
    payload = {
        "user_id": user.id,
        "jti": uuid4().hex,
        "exp": now + 3600,
    }
    if include_login_time:
        payload["login_time"] = login_time
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def _post_admin_reset(user_id, password):
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "reset_password"})
    request = factory.post(
        "/system_mgmt/api/user/reset_password/",
        {"id": user_id, "password": password, "temporary": False},
        format="json",
    )
    force_authenticate(
        request,
        user=types.SimpleNamespace(
            username="admin-reset",
            domain="domain.com",
            locale="en",
            is_superuser=True,
            is_authenticated=True,
        ),
    )
    response = view(request)
    return response, json.loads(response.content.decode("utf-8"))


def test_token_issued_before_password_change_is_rejected(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user()
    issued_at = int(time.time()) - 30
    old_token = _token(user, issued_at)
    changed_at = timezone.now()
    user.password_last_modified = changed_at
    user.save()

    with pytest.raises(Exception, match="revoked due to password change"):
        _verify_token(old_token)

    rejected = verify_token(old_token)
    assert rejected["result"] is False
    assert rejected["error_code"] == PASSWORD_CHANGED_ERROR_CODE
    assert rejected["message"] == PASSWORD_CHANGED_TOKEN_MESSAGE


def test_token_issued_in_the_same_second_as_password_change_stays_valid(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user("same-second-user")
    changed_at = timezone.now().replace(microsecond=0)
    user.password_last_modified = changed_at
    user.save()
    same_second = int(changed_at.timestamp())

    assert _verify_token(_token(user, same_second)).id == user.id
    with pytest.raises(Exception, match="revoked due to password change"):
        _verify_token(_token(user, same_second - 1))


def test_token_without_login_time_is_not_revoked_by_password_time(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user("missing-login-time")
    user.password_last_modified = timezone.now()
    user.save()

    assert _verify_token(_token(user, 0, include_login_time=False)).id == user.id


def _backdate_password(user, seconds=60):
    user.password_last_modified = timezone.now() - timedelta(seconds=seconds)
    user.save()


def test_self_service_reset_replaces_the_current_session_token(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user("self-reset-user")
    _backdate_password(user)
    old_token = _token(user, int(time.time()) - 5)
    assert _verify_token(old_token).id == user.id

    result = reset_pwd(user.username, user.domain, "NewP@ssw0rd!", caller_token=old_token)

    assert result["result"] is True
    rotated = result["data"]["token"]
    assert rotated != old_token
    assert _verify_token(rotated).id == user.id
    with pytest.raises(Exception, match="revoked due to password change"):
        _verify_token(old_token)


def test_admin_reset_does_not_issue_a_token_and_revokes_existing_sessions(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    user = _user("admin-reset-user")
    _backdate_password(user)
    old_token = _token(user, int(time.time()) - 5)
    assert _verify_token(old_token).id == user.id

    response, payload = _post_admin_reset(user.id, "NewP@ssw0rd!")

    assert response.status_code == 200
    assert payload == {"result": True}
    assert "token" not in payload
    with pytest.raises(Exception, match="revoked due to password change"):
        _verify_token(old_token)
