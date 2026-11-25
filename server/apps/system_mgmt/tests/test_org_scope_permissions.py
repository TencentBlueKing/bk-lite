import json
import types

import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Group, OperationLog, Role, User
from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet
from apps.system_mgmt.viewset.role_viewset import RoleViewSet
from apps.system_mgmt.viewset.user_viewset import UserViewSet


def _request_user(group_ids, permission, *, is_superuser=False, is_auditor=False):
    return types.SimpleNamespace(
        username="org-scope-operator",
        domain="domain.com",
        locale="en",
        is_authenticated=True,
        is_superuser=is_superuser,
        is_auditor=is_auditor,
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


@pytest.mark.parametrize("language,expected_message", [("zh-Hans", "current_team 参数非法"), ("en", "current_team parameter is invalid")])
def test_group_data_rule_cmdb_get_app_data_rejects_invalid_current_team(monkeypatch, language, expected_message):
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
    user = _request_user([7], {"data_permission-View"})
    user.locale = language
    force_authenticate(request, user=user)

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 400
    assert payload == {"result": False, "message": expected_message}


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


def test_group_data_rule_patch_get_app_data_injects_authorized_team(monkeypatch):
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
            "app": "patch",
            "module": "patch_target",
            "child_module": "",
            "page": "1",
            "page_size": "10",
            "group_id": "7",
        },
    )
    force_authenticate(request, user=_request_user([7], {"data_permission-View"}))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)

    assert response.status_code == 200
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
    assert payload == {
        "result": False,
        "message": "You do not have permission to access this group.",
    }


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
def test_search_user_list_auditor_sees_users_outside_own_groups():
    other = Group.objects.create(name="scope-search-auditor-other", parent_id=0, is_virtual=False)
    foreign_user = User.objects.create(
        username="scope_search_auditor_foreign",
        display_name="Foreign User",
        email="auditor-foreign@example.com",
        password=make_password("password"),
        group_list=[other.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"get": "search_user_list"})
    request = factory.get("/system_mgmt/api/user/search_user_list/", {"search": "scope_search_auditor"})
    force_authenticate(request, user=_request_user([], {"user_group-View"}, is_auditor=True))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert foreign_user.username in [user["username"] for user in payload["data"]["users"]]


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
def test_create_user_allows_empty_personal_roles():
    group = Group.objects.create(name="scope-create-role-optional-group", parent_id=0, is_virtual=False)
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "pending_authorization_user",
            "lastName": "Pending Authorization User",
            "email": "pending_authorization@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([group.id], {"user_group-Add User"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload == {"result": True}
    user = User.objects.get(username="pending_authorization_user")
    assert user.group_list == [group.id]
    assert user.role_list == []


@pytest.mark.django_db
def test_create_user_auditor_binds_auditor_role_not_admin():
    from apps.system_mgmt.services.platform_roles import ensure_platform_auditor_role

    auditor_role = ensure_platform_auditor_role()
    Role.objects.get_or_create(name="admin", app="")
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "platform_auditor",
            "lastName": "Auditor",
            "email": "auditor@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [],
            "roles": [],
            "rules": [],
            "is_auditor": True,
            "is_superuser": False,
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([], {"user_group-Add User"}))
    response = view(request)
    assert response.status_code == 200
    created = User.objects.get(username="platform_auditor")
    assert auditor_role.id in created.role_list
    assert Role.objects.get(name="admin", app="").id not in created.role_list
    assert created.group_list == []


@pytest.mark.django_db
def test_create_user_superuser_wins_over_auditor_flag():
    from apps.system_mgmt.services.platform_roles import ensure_platform_auditor_role

    auditor_role = ensure_platform_auditor_role()
    admin_role, _ = Role.objects.get_or_create(name="admin", app="")
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "platform_admin_wins",
            "lastName": "Admin Wins",
            "email": "admin-wins@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [],
            "roles": [],
            "rules": [],
            "is_auditor": True,
            "is_superuser": True,
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([], {"user_group-Add User"}))
    response = view(request)
    assert response.status_code == 200
    created = User.objects.get(username="platform_admin_wins")
    assert admin_role.id in created.role_list
    assert auditor_role.id not in created.role_list


@pytest.mark.django_db
def test_get_user_detail_returns_is_auditor():
    from apps.system_mgmt.services.platform_roles import ensure_platform_auditor_role

    auditor_role = ensure_platform_auditor_role()
    Role.objects.get_or_create(name="admin", app="")
    target = User.objects.create(
        username="detail_auditor",
        display_name="Detail Auditor",
        email="detail-auditor@example.com",
        password=make_password("password"),
        group_list=[],
        role_list=[auditor_role.id],
    )
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "get_user_detail"})
    request = factory.post("/system_mgmt/api/user/get_user_detail/", {"user_id": target.id}, format="json")
    force_authenticate(request, user=_request_user([], {"user_group-View"}, is_superuser=True))
    response = view(request)
    payload = _json_payload(response)
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["is_auditor"] is True
    assert payload["data"]["is_superuser"] is False


@pytest.mark.django_db
def test_import_users_creates_valid_rows_and_reports_conflicts():
    group = Group.objects.create(name="xlsx-import-group", parent_id=0, is_virtual=False)
    User.objects.create(
        username="existing-import-user",
        password="p",
        display_name="Existing",
        email="existing@example.com",
        group_list=[group.id],
        role_list=[],
    )
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "import_users"})
    request = factory.post(
        "/system_mgmt/api/user/import_users/",
        {
            "group_id": group.id,
            "file_name": "users.xlsx",
            "users": [
                {
                    "row_number": 2,
                    "username": "new-import-user",
                    "lastName": "New User",
                    "email": "new@example.com",
                    "phone": "",
                    "timezone": "",
                    "locale": "",
                },
                {
                    "row_number": 3,
                    "username": "existing-import-user",
                    "lastName": "Existing User",
                    "email": "existing@example.com",
                    "phone": "",
                    "timezone": "Asia/Shanghai",
                    "locale": "zh-Hans",
                },
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([group.id], {"user_group-Add User"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload["data"] == {
        "total_count": 2,
        "success_count": 1,
        "failed_count": 1,
        "failures": [{"row_number": 3, "username": "existing-import-user", "message": "Username already exists"}],
    }
    user = User.objects.get(username="new-import-user")
    assert user.group_list == [group.id]
    assert user.role_list == []
    assert user.timezone == "Asia/Shanghai"
    assert user.locale == "zh-Hans"
    log = OperationLog.objects.get(action_type="create", target_type="organization", target_id=str(group.id))
    assert log.outcome == "success"
    assert log.failure_reason == ""
    assert log.target_name == group.name


@pytest.mark.django_db
def test_import_users_rejects_archived_group():
    group = Group.objects.create(name="xlsx-archived-group", parent_id=0, is_virtual=False, is_delete=True)
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "import_users"})
    request = factory.post(
        "/system_mgmt/api/user/import_users/",
        {
            "group_id": group.id,
            "file_name": "users.xlsx",
            "users": [
                {
                    "row_number": 2,
                    "username": "archived-import-user",
                    "lastName": "Archived User",
                    "email": "archived@example.com",
                    "phone": "",
                    "timezone": "",
                    "locale": "",
                },
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([group.id], {"user_group-Add User"}, is_superuser=True))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 400
    assert payload["result"] is False
    assert not User.objects.filter(username="archived-import-user").exists()
    assert OperationLog.objects.filter(action_type="create", target_type="organization").count() == 0


@pytest.mark.django_db
def test_import_users_rejects_unauthorized_groups():
    allowed = Group.objects.create(name="xlsx-import-allowed", parent_id=0, is_virtual=False)
    other = Group.objects.create(name="xlsx-import-other", parent_id=0, is_virtual=False)
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "import_users"})
    request = factory.post(
        "/system_mgmt/api/user/import_users/",
        {
            "group_id": other.id,
            "file_name": "users.xlsx",
            "users": [
                {
                    "row_number": 2,
                    "username": "scope-import-user",
                    "lastName": "Scope User",
                    "email": "scope-import@example.com",
                    "phone": "",
                    "timezone": "",
                    "locale": "",
                },
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([allowed.id], {"user_group-Add User"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 403
    assert payload["result"] is False
    assert not User.objects.filter(username="scope-import-user").exists()
    assert OperationLog.objects.filter(action_type="create", target_type="organization").count() == 0


@pytest.mark.django_db
def test_import_users_all_rows_failed_logs_failure():
    group = Group.objects.create(name="xlsx-import-all-fail", parent_id=0, is_virtual=False)
    User.objects.create(
        username="dup-import-user",
        password="p",
        display_name="Existing",
        email="dup@example.com",
        group_list=[group.id],
        role_list=[],
    )
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "import_users"})
    request = factory.post(
        "/system_mgmt/api/user/import_users/",
        {
            "group_id": group.id,
            "file_name": "users.xlsx",
            "users": [
                {
                    "row_number": 2,
                    "username": "dup-import-user",
                    "lastName": "Dup User",
                    "email": "dup@example.com",
                    "phone": "",
                    "timezone": "",
                    "locale": "",
                },
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([group.id], {"user_group-Add User"}))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload["data"]["success_count"] == 0
    assert payload["data"]["failed_count"] == 1
    log = OperationLog.objects.get(action_type="create", target_type="organization", target_id=str(group.id))
    assert log.outcome == "failure"
    assert log.failure_reason == "共 1 条，成功 0 条，失败 1 条"
    assert "dup-import-user" not in log.failure_reason
    assert log.target_name == group.name


@pytest.mark.django_db
def test_create_user_still_rejects_empty_groups():
    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "create_user"})
    request = factory.post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "scope_create_required_group_user",
            "lastName": "Scope Create Required Group User",
            "email": "scope_create_required_group@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [],
            "roles": [],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([], {"user_group-Add User"}, is_superuser=True))

    response = view(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload["result"] is False
    assert not User.objects.filter(username="scope_create_required_group_user").exists()


@pytest.mark.django_db
def test_update_user_still_rejects_empty_groups():
    group = Group.objects.create(name="scope-update-required-group", parent_id=0, is_virtual=False)
    Role.objects.create(name="admin", app="")
    role = Role.objects.create(name="scope-update-required-role", app="")
    target = User.objects.create(
        username="scope_update_required_user",
        display_name="Scope Update Required User",
        email="scope_update_required@example.com",
        password=make_password("password"),
        group_list=[group.id],
        role_list=[role.id],
    )

    factory = APIRequestFactory()
    view = UserViewSet.as_view({"post": "update_user"})
    request = factory.post(
        "/system_mgmt/api/user/update_user/",
        {
            "user_id": target.id,
            "username": target.username,
            "lastName": target.display_name,
            "email": target.email,
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [],
            "roles": [role.id],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([group.id], {"user_group-Edit User"}))

    response = view(request)
    payload = _json_payload(response)
    target.refresh_from_db()

    assert response.status_code == 200
    assert payload["result"] is False
    assert target.group_list == [group.id]


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
