import json
import types

import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Group, Role, User
from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet
from apps.system_mgmt.viewset.role_viewset import RoleViewSet
from apps.system_mgmt.viewset.user_viewset import UserViewSet


def _request_user(group_ids, permission, *, is_superuser=False):
    return types.SimpleNamespace(
        username="org-scope-operator",
        domain="domain.com",
        locale="en",
        is_authenticated=True,
        is_superuser=is_superuser,
        permission={"system-manager": set(permission)},
        group_list=[{"id": group_id} for group_id in group_ids],
    )


def _json_payload(response):
    return json.loads(response.content)


def test_group_data_rule_permission_accepts_integer_group_list():
    request = types.SimpleNamespace(
        user=types.SimpleNamespace(is_superuser=False, group_list=[7]),
    )

    is_valid, error_response = GroupDataRuleViewSet()._validate_group_permission(request, 7)

    assert is_valid is True
    assert error_response is None


def test_group_data_rule_cmdb_get_app_data_injects_user_info(monkeypatch):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "cmdb",
            "module": "instances",
            "child_module": "host",
            "page": "1",
            "page_size": "10",
            "group_id": "7",
        },
    )
    request.COOKIES["current_team"] = "7"
    request.COOKIES["include_children"] = "1"
    force_authenticate(request, user=_request_user([7], {"data_permission-View"}))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured["user_info"] == {
        "user": "org-scope-operator",
        "domain": "domain.com",
        "team": 7,
        "include_children": True,
    }


def test_group_data_rule_cmdb_get_app_data_rejects_invalid_current_team(monkeypatch):
    class FakeClient:
        def get_module_data(self, **kwargs):
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "cmdb",
            "module": "instances",
            "child_module": "host",
            "page": "1",
            "page_size": "10",
            "group_id": "7",
        },
    )
    request.COOKIES["current_team"] = "bad"
    force_authenticate(request, user=_request_user([7], {"data_permission-View"}))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 400
    assert payload == {"result": False, "message": "current_team 参数非法"}


def test_group_data_rule_job_get_app_data_injects_authorized_team(monkeypatch):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "job",
            "module": "script",
            "child_module": "",
            "page": "1",
            "page_size": "10",
            "group_id": "7",
        },
    )
    force_authenticate(request, user=_request_user([7], {"data_permission-View"}))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured["team"] == [7]


def test_group_data_rule_job_get_app_data_rejects_unauthorized_group(monkeypatch):
    class FakeClient:
        def get_module_data(self, **kwargs):
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "job",
            "module": "script",
            "child_module": "",
            "page": "1",
            "page_size": "10",
            "group_id": "8",
        },
    )
    force_authenticate(request, user=_request_user([7], {"data_permission-View"}))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 403
    assert payload == {"result": False, "message": "无权访问该组织"}


@pytest.mark.django_db
def test_search_user_list_filters_to_accessible_groups():
    allowed = Group.objects.create(name="scope-search-allowed", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="scope-search-other", parent_id=0, is_virtual=False)
    allowed_user = User.objects.create(
        username="scope_search_allowed",
        display_name="Allowed User",
        email="allowed@example.com",
        password=make_password("password"),
        group_list=[allowed.id],
    )
    User.objects.create(
        username="scope_search_other",
        display_name="Other User",
        email="other@example.com",
        password=make_password("password"),
        group_list=[other.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"get": "search_user_list"})
    request = factory.get("/system_mgmt/api/user/search_user_list/", {"search": "scope_search"})
    force_authenticate(request, user=_request_user([allowed.id], {"user_group-View"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload["data"]["count"] == 1
    assert [user["username"] for user in payload["data"]["users"]] == [allowed_user.username]


@pytest.mark.django_db
def test_create_user_rejects_unauthorized_groups():
    allowed = Group.objects.create(name="scope-create-allowed", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="scope-create-other", parent_id=0, is_virtual=False)
    role = Role.objects.create(name="scope-create-role", app="")

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "scope_create_user",
            "lastName": "Scope Create User",
            "email": "scope_create@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [other.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([allowed.id], {"user_group-Add User"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 403
    assert payload["result"] is False
    assert not User.objects.filter(username="scope_create_user").exists()


@pytest.mark.django_db
def test_create_user_allows_accessible_groups():
    allowed = Group.objects.create(name="scope-create-allowed-ok", parent_id=0, is_virtual=False)
    role = Role.objects.create(name="scope-create-role-ok", app="")

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "scope_create_user_ok",
            "lastName": "Scope Create User OK",
            "email": "scope_create_ok@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [allowed.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([allowed.id], {"user_group-Add User"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload == {"result": True}
    assert User.objects.get(username="scope_create_user_ok").group_list == [allowed.id]


@pytest.mark.django_db
def test_update_user_rejects_unauthorized_groups():
    allowed = Group.objects.create(name="scope-update-allowed", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="scope-update-other", parent_id=0, is_virtual=False)
    Role.objects.create(name="admin", app="")
    role = Role.objects.create(name="scope-update-role", app="")
    target = User.objects.create(
        username="scope_update_user",
        display_name="Scope Update User",
        email="scope_update@example.com",
        password=make_password("password"),
        group_list=[allowed.id],
        role_list=[role.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "update_user"})
    request = factory.post(
        "/system_mgmt/api/user/update_user/",
        {
            "user_id": target.id,
            "username": target.username,
            "lastName": "Scope Update User",
            "email": target.email,
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [other.id],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([allowed.id], {"user_group-Edit User"}))

    response = view(request)
    payload = _json_payload(response)
    target.refresh_from_db()

    assert response.status_code == 403
    assert payload["result"] is False
    assert target.group_list == [allowed.id]


@pytest.mark.django_db
def test_batch_assign_group_roles_rejects_unauthorized_groups():
    allowed = Group.objects.create(name="scope-role-assign-allowed", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="scope-role-assign-other", parent_id=0, is_virtual=False)
    role = Role.objects.create(name="scope-role-assign", app="system_mgmt")

    request = types.SimpleNamespace(
        user=_request_user([allowed.id], {"application_role-Edit"}),
        data={"group_ids": [other.id], "role_id": role.id},
        META={},
    )

    response = RoleViewSet().batch_assign_group_roles(request)
    payload = _json_payload(response)

    assert response.status_code == 403
    assert payload["result"] is False
    assert not role.group_set.filter(id=other.id).exists()


@pytest.mark.django_db
def test_batch_assign_group_roles_allows_accessible_groups():
    allowed = Group.objects.create(name="scope-role-assign-allowed-ok", parent_id=0, is_virtual=False)
    role = Role.objects.create(name="scope-role-assign-ok", app="system_mgmt")

    request = types.SimpleNamespace(
        user=_request_user([allowed.id], {"application_role-Edit"}),
        data={"group_ids": [allowed.id], "role_id": role.id},
        META={},
    )

    response = RoleViewSet().batch_assign_group_roles(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload == {"result": True}
    assert role.group_set.filter(id=allowed.id).exists()


@pytest.mark.django_db
def test_revoke_group_roles_rejects_unauthorized_groups():
    allowed = Group.objects.create(name="scope-role-revoke-allowed", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="scope-role-revoke-other", parent_id=0, is_virtual=False)
    role = Role.objects.create(name="scope-role-revoke", app="system_mgmt")
    role.group_set.add(other)

    request = types.SimpleNamespace(
        user=_request_user([allowed.id], {"application_role-Edit"}),
        data={"group_ids": [other.id], "role_id": role.id},
        META={},
    )

    response = RoleViewSet().revoke_group_roles(request)
    payload = _json_payload(response)

    assert response.status_code == 403
    assert payload["result"] is False
    assert role.group_set.filter(id=other.id).exists()
