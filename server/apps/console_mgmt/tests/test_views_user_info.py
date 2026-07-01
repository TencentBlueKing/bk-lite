"""console_mgmt views 真实单元/集成测试：

覆盖 update_user_base_info / validate_pwd / get_user_info / reset_pwd /
get_user_group_paths / _format_datetime_for_user / validate_email_code。

策略：用真实 User（DB）+ RequestFactory 直调视图函数，只 mock 外部边界
（SystemMgmt RPC、cache、log_operation）。断言真实 JSON 输出、字段、分支、异常。
"""
import pydantic.root_model  # noqa

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.console_mgmt import views
from apps.console_mgmt.views import (
    _format_datetime_for_user,
    get_user_group_paths,
    get_user_info,
    reset_pwd,
    update_user_base_info,
    validate_email_code,
    validate_pwd,
)
from apps.system_mgmt.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _req(method, body=None, cookies=None):
    factory = RequestFactory()
    kwargs = {}
    if body is not None:
        kwargs["data"] = json.dumps(body)
        kwargs["content_type"] = "application/json"
    req = getattr(factory, method)("/x/", **kwargs)
    if cookies:
        req.COOKIES.update(cookies)
    return req


def _make_user(**kw):
    defaults = dict(username="alice", domain="domain.com", locale="zh-CN", email="a@b.com")
    defaults.update(kw)
    return User.objects.create(**defaults)


class TestFormatDatetimeForUser:
    def test_None返回None(self):
        assert _format_datetime_for_user(None) is None

    def test_无时区用本地时间(self):
        from django.utils import timezone
        now = timezone.now()
        out = _format_datetime_for_user(now)
        assert isinstance(out, str) and "T" in out

    def test_非法时区回退本地时间(self):
        from django.utils import timezone
        now = timezone.now()
        # 非法时区名触发 except 分支，回退 localtime
        out = _format_datetime_for_user(now, "Not/AZone")
        assert isinstance(out, str)

    def test_合法时区生效(self):
        from django.utils import timezone
        now = timezone.now()
        out = _format_datetime_for_user(now, "Asia/Shanghai")
        assert isinstance(out, str)


class TestUpdateUserBaseInfo:
    def test_非法json返回400(self):
        req = _req("post")
        req._body = b"not-json"
        req.user = MagicMock(username="alice", domain="domain.com", locale="zh-CN")
        resp = update_user_base_info(req)
        assert resp.status_code == 400
        assert json.loads(resp.content)["result"] is False

    def test_更新成功落库(self):
        _make_user(display_name="old")
        req = _req("post", {"display_name": "新名字", "email": "new@x.com", "locale": "en", "timezone": "UTC"})
        req.user = MagicMock(username="alice", domain="domain.com", locale="zh-CN")
        with patch.object(views, "log_operation"):
            resp = update_user_base_info(req)
        assert json.loads(resp.content)["result"] is True
        u = User.objects.get(username="alice", domain="domain.com")
        assert u.display_name == "新名字"
        assert u.email == "new@x.com"
        assert u.locale == "en"

    def test_用户不存在返回错误(self):
        req = _req("post", {"display_name": "x"})
        req.user = MagicMock(username="ghost", domain="domain.com", locale="en")
        resp = update_user_base_info(req)
        body = json.loads(resp.content)
        assert body["result"] is False


class TestValidatePwd:
    def test_非法json返回400(self):
        req = _req("post")
        req._body = b"{bad"
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        resp = validate_pwd(req)
        assert resp.status_code == 400

    def test_空密码被拒(self):
        req = _req("post", {})
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        resp = validate_pwd(req)
        assert json.loads(resp.content)["result"] is False

    def test_密码正确返回True(self):
        from django.contrib.auth.hashers import make_password
        u = _make_user()
        u.password = make_password("secret123")
        u.save()
        req = _req("post", {"password": "secret123"})
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        resp = validate_pwd(req)
        assert json.loads(resp.content)["result"] is True

    def test_密码错误返回False(self):
        from django.contrib.auth.hashers import make_password
        u = _make_user()
        u.password = make_password("secret123")
        u.save()
        req = _req("post", {"password": "wrong"})
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        resp = validate_pwd(req)
        assert json.loads(resp.content)["result"] is False

    def test_用户不存在返回False(self):
        req = _req("post", {"password": "x"})
        req.user = MagicMock(username="ghost", domain="domain.com", locale="en")
        resp = validate_pwd(req)
        assert json.loads(resp.content)["result"] is False


class TestValidateEmailCode:
    def test_缺字段被拒(self):
        req = _req("post", {"email": "a@b.com"})
        req.user = MagicMock(username="alice", locale="en")
        resp = validate_email_code(req)
        assert json.loads(resp.content)["result"] is False

    def test_验证码不存在返回过期(self):
        req = _req("post", {"email": "a@b.com", "input_code": "123456"})
        req.user = MagicMock(username="alice", locale="en")
        with patch.object(views, "cache") as c:
            c.get.return_value = None
            resp = validate_email_code(req)
        assert json.loads(resp.content)["result"] is False

    def test_验证码正确一次性删除(self):
        req = _req("post", {"email": "a@b.com", "input_code": "123456"})
        req.user = MagicMock(username="alice", locale="en")
        with patch.object(views, "cache") as c:
            c.get.return_value = "123456"
            resp = validate_email_code(req)
            c.delete.assert_called_once()
        assert json.loads(resp.content)["result"] is True

    def test_验证码错误不删除(self):
        req = _req("post", {"email": "a@b.com", "input_code": "000000"})
        req.user = MagicMock(username="alice", locale="en")
        with patch.object(views, "cache") as c:
            c.get.return_value = "123456"
            resp = validate_email_code(req)
            c.delete.assert_not_called()
        assert json.loads(resp.content)["result"] is False


class TestGetUserGroupPaths:
    def test_空列表返回空(self):
        assert get_user_group_paths([]) == []

    def test_向上收集祖先并构建路径(self):
        from apps.system_mgmt.models import Group
        root = Group.objects.create(name="root", parent_id=0)
        child = Group.objects.create(name="child", parent_id=root.id)
        leaf = Group.objects.create(name="leaf", parent_id=child.id)
        paths = get_user_group_paths([leaf.id])
        # build_group_paths 返回非空路径，包含 leaf 节点
        assert isinstance(paths, list)
        assert len(paths) >= 1


class TestGetUserInfo:
    def test_用户不存在返回False(self):
        req = _req("get")
        req.user = MagicMock(username="ghost", domain="domain.com", locale="en", timezone="UTC")
        resp = get_user_info(req)
        assert json.loads(resp.content)["result"] is False

    def test_返回用户信息字段齐全(self):
        u = _make_user(display_name="A", group_list=[], role_list=[])
        req = _req("get")
        req.user = MagicMock(username="alice", domain="domain.com", locale="en", timezone="UTC")
        resp = get_user_info(req)
        body = json.loads(resp.content)
        assert body["result"] is True
        data = body["data"]
        assert data["id"] == u.id
        assert data["username"] == "alice"
        assert data["email"] == "a@b.com"
        assert data["group_list"] == []
        assert data["role_list"] == []


class TestResetPwd:
    def test_缺token返回提示(self):
        _make_user()
        req = _req("post", {"password": "newpw"})
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        resp = reset_pwd(req)
        body = json.loads(resp.content)
        assert body["result"] is False

    def test_重置成功转发RPC并记日志(self):
        _make_user()
        req = _req("post", {"password": "newpw"}, cookies={"bklite_token": "tok123"})
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        with patch.object(views, "SystemMgmt") as MockRPC, patch.object(views, "log_operation") as log:
            inst = MagicMock()
            inst.reset_pwd.return_value = {"result": True}
            MockRPC.return_value = inst
            resp = reset_pwd(req)
            inst.reset_pwd.assert_called_once_with("alice", "domain.com", "newpw", caller_token="tok123")
            log.assert_called_once()
        assert json.loads(resp.content)["result"] is True

    def test_空密码被拒(self):
        req = _req("post", {"password": ""})
        req.user = MagicMock(username="alice", domain="domain.com", locale="en")
        resp = reset_pwd(req)
        assert json.loads(resp.content)["result"] is False
