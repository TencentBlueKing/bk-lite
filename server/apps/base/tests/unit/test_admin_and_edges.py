"""base.admin 与 user_api_secret viewset/serializer 边界补缺。

- UserAPISecretAdmin.save_model：obj 无 api_secret 时生成密钥并只保存哈希；已有哈希不重复处理；
- UserAPISecretViewSet.get_queryset：未认证 / team cookie 非整数 -> 空 queryset；
- UserAPISecretSerializer.get_api_secret_preview：空 secret -> 空串，非空只返回固定掩码。
只 mock super().save_model（admin 父类落库边界）与 request；不连真实 DB 写库的部分用 monkeypatch。
"""
import pydantic.root_model  # noqa

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite

from apps.base.admin import UserAPISecretAdmin
from apps.base.models import UserAPISecret
from apps.base.user_api_secret_mgmt.serializers import UserAPISecretSerializer
from apps.base.user_api_secret_mgmt.views import UserAPISecretViewSet

pytestmark = pytest.mark.unit


class TestUserAPISecretAdminSaveModel:
    def _admin(self):
        return UserAPISecretAdmin(UserAPISecret, AdminSite())

    def test_无secret时生成并保存哈希(self):
        admin = self._admin()
        obj = UserAPISecret(username="u", domain="domain.com", api_secret="", team=0)
        raw_secret = "a" * 64
        with (
            patch("apps.base.admin.UserAPISecret.generate_api_secret", return_value=raw_secret),
            patch("apps.base.admin.admin.ModelAdmin.save_model") as super_save,
        ):
            admin.save_model(MagicMock(), obj, MagicMock(), change=False)
            super_save.assert_called_once()
        assert obj.api_secret == UserAPISecret.hash_api_secret(raw_secret)
        assert raw_secret not in obj.api_secret

    def test_已有哈希时不重复哈希(self):
        admin = self._admin()
        hashed_secret = UserAPISecret.hash_api_secret("EXISTING")
        obj = UserAPISecret(username="u", domain="domain.com", api_secret=hashed_secret, team=0)
        with patch("apps.base.admin.admin.ModelAdmin.save_model") as super_save:
            admin.save_model(MagicMock(), obj, MagicMock(), change=True)
            super_save.assert_called_once()
        assert obj.api_secret == hashed_secret


class TestViewSetGetQueryset:
    def _vs(self, request):
        vs = UserAPISecretViewSet()
        vs.request = request
        return vs

    def test_无request返回none(self):
        vs = UserAPISecretViewSet()
        # 不设置 request 属性
        assert vs.get_queryset().count() == 0 if hasattr(vs, "request") else True
        # 显式覆盖：无 request 属性
        vs2 = UserAPISecretViewSet()
        qs = vs2.get_queryset()
        assert list(qs) == []

    def test_未认证用户返回空queryset(self):
        request = MagicMock()
        request.user.is_authenticated = False
        qs = self._vs(request).get_queryset()
        assert list(qs) == []

    def test_team_cookie非整数返回空queryset(self):
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.username = "alice"
        request.user.domain = "domain.com"
        with patch("apps.base.user_api_secret_mgmt.views.get_current_team", return_value="not-int"):
            qs = self._vs(request).get_queryset()
        assert list(qs) == []


class TestApiSecretPreviewEmpty:
    def test_空secret预览为空串(self):
        instance = UserAPISecret(api_secret="")
        request = MagicMock()
        request.user.group_list = []
        ser = UserAPISecretSerializer(context={"request": request})
        assert ser.get_api_secret_preview(instance) == ""

    def test_有secret只返回固定掩码(self):
        instance = UserAPISecret(api_secret="abcd1234ef")
        request = MagicMock()
        request.user.group_list = []
        ser = UserAPISecretSerializer(context={"request": request})
        assert ser.get_api_secret_preview(instance) == "********"
