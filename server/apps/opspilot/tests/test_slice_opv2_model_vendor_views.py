"""opspilot-views2 切片: viewsets/model_vendor_view.ModelVendorViewSet 真实 DRF + DB 测试。

- list: 真实 ORM 统计每个 vendor 的启用模型数(model_count),超管走全量;
- test_connection action(经 __wrapped__ 绕鉴权): openai/anthropic 各路由到对应
  ModelVendorSyncService 方法,异常被包装为 {"result": False};serializer 校验失败抛 400;
- sync_models action: 委托 sync_vendor_models,ValueError/Exception 转 {"result": False};
- destroy: 被 LLMModel(on_delete=PROTECT)引用时 ProtectedError 转 400 干净信封。
仅 mock ModelVendorSyncService(LLM/HTTP 边界),DB/序列化器走真实。
"""

import json

import pydantic.root_model  # noqa
import pytest
from types import SimpleNamespace
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import LLMModel, EmbedProvider
from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.viewsets.model_vendor_view import ModelVendorViewSet

pytestmark = pytest.mark.django_db


def _body(resp):
    if hasattr(resp, "data") and not hasattr(resp, "content"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _su():
    from apps.base.models import User

    u = User.objects.create_user(
        username=f"mv_su_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
    )
    u.is_superuser = True
    u.save()
    return u


def _vendor(name="v", team=None):
    return ModelVendor.objects.create(name=name, vendor_type="openai", api_base="http://api", api_key="sk", team=team or [1])


class TestList:
    def test_统计启用模型数(self):
        user = _su()
        v1 = _vendor("v1")
        v2 = _vendor("v2")
        # v1: 2 个启用 LLM + 1 个禁用(不计) + 1 个启用 Embed = 3
        LLMModel.objects.create(name="a", vendor=v1, model="a", enabled=True)
        LLMModel.objects.create(name="b", vendor=v1, model="b", enabled=True)
        LLMModel.objects.create(name="c", vendor=v1, model="c", enabled=False)
        EmbedProvider.objects.create(name="e", vendor=v1, model="e", enabled=True)
        # v2: 无模型 -> 0
        factory = APIRequestFactory()
        request = factory.get("/")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = ModelVendorViewSet.as_view({"get": "list"})(request)

        assert resp.status_code == 200
        body = _body(resp)
        assert body["result"] is True
        counts = {item["id"]: item["model_count"] for item in body["data"]}
        assert counts[v1.id] == 3
        assert counts[v2.id] == 0


class TestTestConnection:
    def _call(self, data):
        viewset = ModelVendorViewSet()
        viewset.loader = None
        request = SimpleNamespace(data=data, user=SimpleNamespace(locale="en"))
        return ModelVendorViewSet.test_connection.__wrapped__(viewset, request)

    def test_openai路由到fetch_models(self, mocker):
        m = mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.fetch_models_with_credentials"
        )
        resp = self._call({"api_base": "http://api.x", "api_key": "sk-1", "protocol_type": "openai"})
        assert _body(resp) == {"result": True}
        m.assert_called_once()
        assert m.call_args.kwargs["protocol_type"] == "openai"

    def test_anthropic真供应商路由到test_anthropic(self, mocker):
        m = mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.test_anthropic_connection"
        )
        resp = self._call(
            {"api_base": "http://api.x", "api_key": "sk-1", "protocol_type": "anthropic", "vendor_type": "anthropic"}
        )
        assert _body(resp)["result"] is True
        # 真 anthropic 不传 model 参数(用默认 claude)
        assert "model" not in m.call_args.kwargs

    def test_deepseek_anthropic协议用deepseek模型(self, mocker):
        m = mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.test_anthropic_connection"
        )
        resp = self._call(
            {"api_base": "http://api.x", "api_key": "sk-1", "protocol_type": "anthropic", "vendor_type": "deepseek"}
        )
        assert _body(resp)["result"] is True
        assert m.call_args.kwargs["model"] == "deepseek-chat"

    def test_异常被包装为result_false(self, mocker):
        mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.fetch_models_with_credentials",
            side_effect=Exception("connect refused"),
        )
        resp = self._call({"api_base": "http://api.x", "api_key": "sk-1", "protocol_type": "openai"})
        body = _body(resp)
        assert body["result"] is False
        assert "connect refused" in body["message"]

    def test_缺api_key校验失败抛400(self):
        # password_changed 默认 True 时 api_key 必填,serializer.is_valid(raise_exception)
        viewset = ModelVendorViewSet()
        viewset.loader = None
        request = SimpleNamespace(data={"api_base": "http://api.x"}, user=SimpleNamespace(locale="en"))
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            ModelVendorViewSet.test_connection.__wrapped__(viewset, request)


class TestSyncModels:
    def _call(self, vendor):
        viewset = ModelVendorViewSet()
        viewset.loader = None
        viewset.get_object = lambda: vendor
        request = SimpleNamespace(user=SimpleNamespace(locale="en"))
        return ModelVendorViewSet.sync_models.__wrapped__(viewset, request, pk=vendor.id)

    def test_成功委托服务(self, mocker):
        v = _vendor()
        m = mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.sync_vendor_models"
        )
        resp = self._call(v)
        assert _body(resp) == {"result": True}
        m.assert_called_once()
        assert m.call_args[0][0] is v

    def test_valueerror转result_false(self, mocker):
        v = _vendor()
        mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.sync_vendor_models",
            side_effect=ValueError("not supported"),
        )
        body = _body(self._call(v))
        assert body["result"] is False
        assert "not supported" in body["message"]

    def test_泛异常转result_false(self, mocker):
        v = _vendor()
        mocker.patch(
            "apps.opspilot.viewsets.model_vendor_view.ModelVendorSyncService.sync_vendor_models",
            side_effect=RuntimeError("boom"),
        )
        body = _body(self._call(v))
        assert body["result"] is False
        assert "boom" in body["message"]


class TestDestroyProtected:
    def test_被引用返回400干净信封(self):
        user = _su()
        v = _vendor()
        # LLMModel 以 PROTECT 引用 vendor
        LLMModel.objects.create(name="ref", vendor=v, model="ref", enabled=True)
        factory = APIRequestFactory()
        request = factory.delete("/")
        force_authenticate(request, user=user)
        resp = ModelVendorViewSet.as_view({"delete": "destroy"})(request, pk=v.id)

        assert resp.status_code == 400
        body = _body(resp)
        assert body["result"] is False
        assert body["message"]
        # vendor 未被删除
        assert ModelVendor.objects.filter(id=v.id).exists()

    def test_无引用正常删除(self):
        user = _su()
        v = _vendor()
        factory = APIRequestFactory()
        request = factory.delete("/")
        force_authenticate(request, user=user)
        resp = ModelVendorViewSet.as_view({"delete": "destroy"})(request, pk=v.id)
        assert resp.status_code == 204
        assert not ModelVendor.objects.filter(id=v.id).exists()
