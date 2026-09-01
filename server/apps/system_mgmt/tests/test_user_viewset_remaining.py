"""UserViewSet 剩余：列表分页、创建校验、重置密码与状态变更鉴权。"""
import json

import pytest
from django.contrib.auth.hashers import check_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.viewset.user_viewset import UserViewSet

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _body(resp):
    return json.loads(resp.content)


def _actor(**kwargs):
    user = UserFactory(domain="domain.com", is_superuser=True)
    user.group_list = kwargs.get("group_list", [{"id": 1}])
    user.locale = "zh-Hans"
    return user


def _req(action, method, actor, data=None, query=""):
    path = f"/x/?{query}" if query else "/x/"
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=actor)
    return UserViewSet.as_view({method: action})(request)


def test_search_user_list_paginates_and_filters():
    group = Group.objects.create(name="uv-search")
    actor = _actor(group_list=[{"id": group.id}])
    User.objects.create(
        username="uv-alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[group.id],
        domain="domain.com",
    )
    User.objects.create(
        username="uv-bob",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[group.id],
        domain="domain.com",
    )
    User.objects.create(
        username="uv-other",
        display_name="Other",
        email="other@example.com",
        password="x",
        group_list=[999],
        domain="domain.com",
    )
    resp = _req("search_user_list", "get", actor, query="search=uv-&page=1&page_size=1")
    body = _body(resp)
    assert body["result"] is True
    assert body["data"]["count"] >= 2
    assert len(body["data"]["users"]) == 1


def test_user_all_and_user_id_all_scope_to_accessible_groups():
    group = Group.objects.create(name="uv-all")
    actor = _actor(group_list=[{"id": group.id}])
    actor.is_superuser = False
    actor.permission = {"user_group-View"}
    visible = User.objects.create(
        username="uv-visible",
        display_name="可见",
        email="v@example.com",
        password="x",
        group_list=[group.id],
        domain="domain.com",
    )
    User.objects.create(
        username="uv-hidden",
        display_name="隐藏",
        email="h@example.com",
        password="x",
        group_list=[888],
        domain="domain.com",
    )
    all_resp = _req("user_all", "get", actor)
    names = {item["username"] for item in _body(all_resp)["data"]}
    assert "uv-visible" in names
    assert "uv-hidden" not in names

    ids_resp = _req("user_id_all", "get", actor)
    ids = {item["id"] for item in _body(ids_resp)["data"]}
    assert visible.id in ids


def test_create_user_rejects_empty_groups_invalid_role_and_phone():
    actor = _actor()
    empty = _req("create_user", "post", actor, data={"username": "n", "groups": []})
    assert _body(empty)["result"] is False
    assert _body(empty)["message"] == "至少选择一个组织"

    group = Group.objects.create(name="uv-create")
    bad_role = _req(
        "create_user",
        "post",
        actor,
        data={
            "username": "uv-new",
            "lastName": "新用户",
            "email": "n@example.com",
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [987654],
        },
    )
    assert _body(bad_role)["result"] is False
    assert "987654" in _body(bad_role)["message"]

    bad_phone = _req(
        "create_user",
        "post",
        actor,
        data={
            "username": "uv-phone",
            "lastName": "电话",
            "email": "p@example.com",
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [],
            "phone": "abc",
        },
    )
    assert _body(bad_phone) == {"result": False, "message": "手机号格式不正确"}


def test_create_user_forbids_unauthorized_group(monkeypatch):
    group = Group.objects.create(name="uv-scope")
    actor = _actor()
    actor.is_superuser = False
    actor.group_list = [{"id": 1}]
    actor.permission = {"user_group-Add User"}
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.get_unauthorized_group_ids",
        lambda user, group_ids: [group.id],
    )
    resp = _req(
        "create_user",
        "post",
        actor,
        data={
            "username": "uv-scope-u",
            "lastName": "越权",
            "email": "s@example.com",
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [],
        },
    )
    assert resp.status_code == 403
    assert _body(resp)["result"] is False


def test_create_user_success(monkeypatch):
    group = Group.objects.create(name="uv-ok")
    actor = _actor()
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.log_operation", lambda *a, **k: None)
    resp = _req(
        "create_user",
        "post",
        actor,
        data={
            "username": "uv-created",
            "lastName": "创建成功",
            "email": "c@example.com",
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [],
        },
    )
    assert _body(resp) == {"result": True}
    user = User.objects.get(username="uv-created")
    assert user.display_name == "创建成功"
    assert user.group_list == [group.id]


def test_reset_password_empty_invalid_and_forbidden(monkeypatch):
    group = Group.objects.create(name="uv-pwd")
    actor = _actor()
    target = User.objects.create(
        username="uv-pwd-t",
        display_name="t",
        email="t@example.com",
        password="old",
        group_list=[999],
        domain="domain.com",
    )
    empty = _req("reset_password", "post", actor, data={"id": target.id, "password": ""})
    assert empty.status_code == 400
    assert _body(empty) == {"result": False, "message": "密码不能为空"}

    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.PasswordValidator.validate_password",
        lambda pwd, locale=None: (False, "密码太弱"),
    )
    weak = _req("reset_password", "post", actor, data={"id": target.id, "password": "123"})
    assert weak.status_code == 400
    assert _body(weak) == {"result": False, "message": "密码太弱"}

    actor.is_superuser = False
    actor.group_list = [{"id": group.id}]
    actor.permission = {"user_group-Edit User"}
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.PasswordValidator.validate_password",
        lambda pwd, locale=None: (True, ""),
    )
    resp = _req("reset_password", "post", actor, data={"id": target.id, "password": "GoodPass1!"})
    assert resp.status_code == 403
    assert _body(resp)["result"] is False


def test_reset_password_success(monkeypatch):
    group = Group.objects.create(name="uv-pwd-ok")
    actor = _actor(group_list=[{"id": group.id}])
    target = User.objects.create(
        username="uv-pwd-ok-t",
        display_name="t",
        email="ok@example.com",
        password="old",
        group_list=[group.id],
        domain="domain.com",
    )
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.PasswordValidator.validate_password",
        lambda pwd, locale=None: (True, ""),
    )
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.log_operation", lambda *a, **k: None)
    resp = _req("reset_password", "post", actor, data={"id": target.id, "password": "GoodPass1!", "temporary": True})
    assert _body(resp) == {"result": True}
    target.refresh_from_db()
    assert target.temporary_pwd is True
    assert check_password("GoodPass1!", target.password)


def test_change_status_validates_and_skips():
    actor = _actor()
    empty = _req("change_status", "post", actor, data={"user_ids": [], "action": "enable"})
    assert empty.status_code == 400
    assert _body(empty)["message"] == "user_ids 必须是非空列表"

    bad_action = _req("change_status", "post", actor, data={"user_ids": [1], "action": "freeze"})
    assert bad_action.status_code == 400
    assert _body(bad_action)["message"] == "action 必须是 enable、disable 或 unlock"

    bad_id = _req("change_status", "post", actor, data={"user_ids": ["x"], "action": "enable"})
    assert bad_id.status_code == 400
    assert _body(bad_id)["message"] == "非法的用户 ID: ['x']"

    missing = _req("change_status", "post", actor, data={"user_ids": [999999], "action": "enable"})
    assert _body(missing)["data"]["skipped"] == [{"id": 999999, "reason": "user_not_found"}]


def test_change_status_disable_and_skip_already_disabled(monkeypatch):
    group = Group.objects.create(name="uv-status")
    actor = _actor(group_list=[{"id": group.id}])
    enabled = User.objects.create(
        username="uv-en",
        display_name="en",
        email="en@example.com",
        password="x",
        group_list=[group.id],
        domain="domain.com",
        disabled=False,
    )
    disabled = User.objects.create(
        username="uv-dis",
        display_name="dis",
        email="dis@example.com",
        password="x",
        group_list=[group.id],
        domain="domain.com",
        disabled=True,
    )
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.log_operation", lambda *a, **k: None)
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.clear_user_permission_cache", lambda *a, **k: None)
    resp = _req("change_status", "post", actor, data={"user_ids": [enabled.id, disabled.id], "action": "disable"})
    body = _body(resp)
    assert body["result"] is True
    assert body["data"]["success_ids"] == [enabled.id]
    assert body["data"]["skipped"] == [{"id": disabled.id, "reason": "user_not_enabled"}]
    enabled.refresh_from_db()
    assert enabled.disabled is True
