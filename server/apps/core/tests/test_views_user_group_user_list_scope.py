"""core user_list 必须按调用方授权组织收口，且不得回传敏感用户字段。"""

import json
import types

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.views.user_group import UserGroupViewSet
from apps.system_mgmt.models import Group, User

pytestmark = pytest.mark.django_db

SENSITIVE_SENTINELS = (
    "email",
    "phone",
    "role_list",
    "last_login",
    "password_last_modified",
    "password_error_count",
    "account_locked_until",
    "password",
    "otp_secret",
    "group_list",
)


def _request(*, path="/core/api/user_group/user_list/", user=None, cookies=None):
    factory = APIRequestFactory()
    wsgi = factory.get(path)
    for key, value in (cookies or {}).items():
        wsgi.COOKIES[key] = str(value)
    request = Request(wsgi)
    request.user = user
    return request


def _body(response):
    return json.loads(response.content)


def _directory_fixture():
    home = Group.objects.create(name="core-home", parent_id=0)
    other = Group.objects.create(name="core-other", parent_id=0)
    actor = User.objects.create(
        username="core-actor",
        password="x",
        display_name="Core Actor",
        email="core-actor@example.com",
        phone="13800001111",
        domain="domain.com",
        group_list=[home.id],
        role_list=[1],
    )
    insider = User.objects.create(
        username="core-insider",
        password="secret-hash",
        display_name="Core Insider",
        email="insider@example.com",
        phone="13800002222",
        domain="domain.com",
        group_list=[home.id],
        role_list=[2],
    )
    User.objects.create(
        username="core-outsider",
        password="secret-hash",
        display_name="Core Outsider",
        email="outsider@example.com",
        phone="13800003333",
        domain="domain.com",
        group_list=[other.id],
        role_list=[3],
    )
    request_user = types.SimpleNamespace(
        username=actor.username,
        domain=actor.domain,
        is_superuser=True,
        group_list=[other.id],
    )
    return home, other, actor, insider, request_user


def test_user_list_returns_only_authorized_group_users_without_sensitive_fields():
    home, _other, _actor, insider, request_user = _directory_fixture()
    vs = UserGroupViewSet()
    response = vs.user_list(
        _request(
            user=request_user,
            cookies={"current_team": home.id, "include_children": "0"},
        )
    )
    payload = _body(response)

    assert response.status_code == 200
    assert payload["result"] is True
    users = payload["data"]["users"]
    usernames = {row["username"] for row in users}
    assert insider.username in usernames
    assert "core-outsider" not in usernames
    for row in users:
        assert set(row) <= {"id", "user_id", "username", "display_name"}
        for field in SENSITIVE_SENTINELS:
            assert field not in row


def test_user_list_caps_page_size_and_keeps_scope():
    home, _other, _actor, insider, request_user = _directory_fixture()
    vs = UserGroupViewSet()
    response = vs.user_list(
        _request(
            path="/core/api/user_group/user_list/?page=1&page_size=99999999",
            user=request_user,
            cookies={"current_team": home.id},
        )
    )
    payload = _body(response)

    assert payload["result"] is True
    usernames = {row["username"] for row in payload["data"]["users"]}
    assert insider.username in usernames
    assert "core-outsider" not in usernames
    assert payload["data"]["count"] == len(payload["data"]["users"])
