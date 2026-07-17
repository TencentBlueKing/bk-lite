"""AppViewSet 与 AppSerializer 的真实行为测试。

覆盖：
- AppSerializer.to_representation 在 GET 请求下用翻译后的 description_cn 替换 description，
  并移除辅助字段 description_cn。
- AppSerializer.create 强制 is_build_in=False 并联动创建 user 角色。
- AppSerializer.update 丢弃 is_build_in。
- AppViewSet.destroy 对内置应用拒绝删除；对自定义应用删除并联动清理角色。
"""

import types
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import App, Group, Role, User
from apps.system_mgmt.serializers.app_serializer import AppSerializer
from apps.system_mgmt.viewset.app_viewset import AppViewSet

pytestmark = pytest.mark.django_db


def _request(method="get"):
    factory = APIRequestFactory()
    req = getattr(factory, method)("/system_mgmt/api/application/")
    req.user = types.SimpleNamespace(
        username="app-admin",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        is_authenticated=True,
        permission={},
    )
    return req


def test_app_serializer_get_replaces_description_and_drops_helper():
    app = App.objects.create(
        name="custom_app",
        display_name="自定义应用",
        description="custom desc",
        url="/custom",
        is_build_in=False,
    )
    # 用 DRF Request 包装以满足 self.context["request"].method == "GET"
    from rest_framework.request import Request

    drf_req = Request(_request("get"))
    serializer = AppSerializer(app, context={"request": drf_req})
    data = serializer.data
    # 非内置：description_cn 即原 description，替换后仍是原值
    assert data["description"] == "custom desc"
    # 辅助字段被删除
    assert "description_cn" not in data


def test_app_serializer_create_forces_non_builtin_and_creates_role():
    from rest_framework.request import Request

    drf_req = Request(_request("post"))
    serializer = AppSerializer(
        data={
            "name": "brand_new_app",
            "display_name": "新应用",
            "description": "d",
            "url": "/new",
            "is_build_in": True,  # 应被强制为 False
            "tags": [],
        },
        context={"request": drf_req},
    )
    assert serializer.is_valid(), serializer.errors
    instance = serializer.save()
    assert instance.is_build_in is False
    assert Role.objects.filter(name="user", app="brand_new_app").exists()


def test_app_serializer_update_drops_is_build_in():
    app = App.objects.create(
        name="upd_app", display_name="d", description="x", url="/u", is_build_in=False
    )
    from rest_framework.request import Request

    drf_req = Request(_request("put"))
    serializer = AppSerializer(
        app,
        data={
            "name": "upd_app",
            "display_name": "d2",
            "description": "y",
            "url": "/u",
            "is_build_in": True,  # 应被忽略
            "tags": [],
        },
        context={"request": drf_req},
    )
    assert serializer.is_valid(), serializer.errors
    instance = serializer.save()
    instance.refresh_from_db()
    assert instance.is_build_in is False
    assert instance.display_name == "d2"


def test_app_viewset_destroy_rejects_builtin_app():
    app = App.objects.create(
        name="builtin_app", display_name="内置", description="x", url="/b", is_build_in=True
    )
    view = AppViewSet.as_view({"delete": "destroy"})
    request = _request("delete")
    force_authenticate(request, user=request.user)
    response = view(request, pk=app.id)
    import json

    payload = json.loads(response.content)
    assert payload["result"] is False
    # 应用未被删除
    assert App.objects.filter(id=app.id).exists()


def test_app_viewset_destroy_removes_custom_app_and_roles():
    app = App.objects.create(
        name="deletable_app", display_name="可删", description="x", url="/d", is_build_in=False
    )
    role = Role.objects.create(name="user", app="deletable_app")
    parent = Group.objects.create(name="AppParent", parent_id=0, allow_inherit_roles=True)
    child = Group.objects.create(name="AppChild", parent_id=parent.id)
    parent.roles.add(role)
    User.objects.create(
        username="app-descendant",
        password="x",
        display_name="App Descendant",
        email="app-descendant@example.com",
        group_list=[child.id],
    )
    view = AppViewSet.as_view({"delete": "destroy"})
    request = _request("delete")
    force_authenticate(request, user=request.user)
    with patch("apps.system_mgmt.viewset.app_viewset.clear_users_permission_cache") as clear_cache:
        response = view(request, pk=app.id)
    assert response.status_code == 204
    assert not App.objects.filter(id=app.id).exists()
    assert not Role.objects.filter(app="deletable_app").exists()
    assert {user["username"] for user in clear_cache.call_args.args[0]} == {"app-descendant"}


def test_app_viewset_rename_invalidates_role_users():
    app = App.objects.create(name="old_app", display_name="Old", description="x", url="/old", is_build_in=False)
    role = Role.objects.create(name="user", app="old_app")
    User.objects.create(
        username="app-direct",
        password="x",
        display_name="App Direct",
        email="app-direct@example.com",
        role_list=[role.id],
    )
    view = AppViewSet.as_view({"put": "update"})
    request = APIRequestFactory().put(
        "/system_mgmt/api/application/",
        {"name": "new_app", "display_name": "New", "description": "x", "url": "/new", "tags": []},
        format="json",
    )
    force_authenticate(request, user=_request().user)

    with patch("apps.system_mgmt.viewset.app_viewset.clear_users_permission_cache") as clear_cache:
        response = view(request, pk=app.id)

    assert response.status_code == 200
    role.refresh_from_db()
    assert role.app == "new_app"
    assert {user["username"] for user in clear_cache.call_args.args[0]} == {"app-direct"}
