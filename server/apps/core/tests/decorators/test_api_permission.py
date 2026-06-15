"""core.decorators.api_permission 纯单元测试。

规格：HasRole / HasPermission 是接口鉴权装饰器，决定请求放行或 403。
鉴权契约必须可靠，这里覆盖角色/权限解析与放行决策的关键分支。
"""

import os
from types import SimpleNamespace
from unittest import mock

import pytest
from rest_framework import status

from apps.core.decorators.api_permission import HasPermission, HasRole

pytestmark = pytest.mark.unit


def _request(user):
    return SimpleNamespace(user=user)


def _user(**kw):
    kw.setdefault("is_superuser", False)
    kw.setdefault("roles", [])
    kw.setdefault("locale", "en")
    return SimpleNamespace(**kw)


class TestHasRoleNormalize:
    def test_none_返回空列表(self):
        assert HasRole(None).roles == []

    def test_普通字符串包装为单元素列表(self):
        assert HasRole("guest").roles == ["guest"]

    def test_列表原样返回(self):
        assert HasRole(["a", "b"]).roles == ["a", "b"]

    def test_非法类型返回空列表(self):
        assert HasRole(123).roles == []

    def test_admin_无_client_id_时仅_admin(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLIENT_ID", None)
            assert HasRole("admin").roles == ["admin"]

    def test_admin_有_client_id_时附加租户管理员(self):
        with mock.patch.dict(os.environ, {"CLIENT_ID": "bklite"}):
            assert HasRole("admin").roles == ["admin", "bklite_admin"]


class TestHasRoleCall:
    def test_无角色要求直接放行(self):
        called = HasRole(None)(lambda req: "ok")
        assert called(_request(_user())) == "ok"

    def test_超级用户放行(self):
        called = HasRole(["admin"])(lambda req: "ok")
        assert called(_request(_user(is_superuser=True))) == "ok"

    def test_命中角色放行(self):
        called = HasRole(["admin"])(lambda req: "ok")
        assert called(_request(_user(roles=["admin"]))) == "ok"

    def test_未命中角色返回_403(self):
        called = HasRole(["admin"])(lambda req: "ok")
        resp = called(_request(_user(roles=["guest"])))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_无请求对象返回_403(self):
        called = HasRole(["admin"])(lambda: "ok")
        # 无法从参数解析出 request -> 取 args[0]=None 路径会抛错；
        # 以位置参数 None 模拟「拿不到 request」
        resp = called(None)
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestHasPermissionParse:
    def test_空字符串得到空集合(self):
        assert HasPermission("")._parse_permissions("") == set()

    def test_逗号分隔去空白(self):
        assert HasPermission("a, b ,c")._parse_permissions("a, b ,c") == {"a", "b", "c"}


class TestHasPermissionUserPerms:
    def test_新格式按_app_取权限(self):
        hp = HasPermission("View", app_name="myapp")
        req = _request(_user(permission={"myapp": {"View"}}))
        assert hp._get_user_permissions(req, "myapp") == {"View"}

    def test_旧格式_set_直接返回(self):
        hp = HasPermission("View", app_name="myapp")
        req = _request(_user(permission={"Operate"}))
        assert hp._get_user_permissions(req, "myapp") == {"Operate"}

    def test_无权限属性返回空集合(self):
        hp = HasPermission("View", app_name="myapp")
        req = _request(_user())
        assert hp._get_user_permissions(req, "myapp") == set()
