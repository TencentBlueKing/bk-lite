"""opspilot-views2 切片: utils/vendor_model_mixin 真实测试。

- protected_delete_response: count/format/loader 各分支生成 400 干净信封;
- VendorModelMixin.by_vendor(经 __wrapped__ 绕鉴权): 缺 vendor / 无 current_team /
  非超管越权 403 / 正常按 vendor + vendor.team 过滤,真实 ORM 落库。
真实 DB(LLMModel/ModelVendor),无外部 mock。
"""

import json

import pydantic.root_model  # noqa
import pytest
from types import SimpleNamespace

from apps.opspilot.utils.vendor_model_mixin import VendorModelMixin, protected_delete_response

pytestmark = pytest.mark.unit


def _body(resp):
    return json.loads(resp.content.decode("utf-8"))


# ---------------------------------------------------------------------------
# protected_delete_response
# ---------------------------------------------------------------------------
class TestProtectedDeleteResponse:
    def test_默认信息含count(self):
        err = SimpleNamespace(protected_objects=[1, 2, 3])
        resp = protected_delete_response(None, err)
        assert resp.status_code == 400
        body = _body(resp)
        assert body["result"] is False
        assert "3" in body["message"]

    def test_loader提供信息时优先(self):
        err = SimpleNamespace(protected_objects=[1])
        loader = SimpleNamespace(get=lambda key: "占用中 {count} 个" if key == "error.vendor_in_use" else None)
        resp = protected_delete_response(loader, err, message_key="error.vendor_in_use")
        assert _body(resp)["message"] == "占用中 1 个"

    def test_protected_objects缺失按0(self):
        err = SimpleNamespace()
        resp = protected_delete_response(None, err)
        assert resp.status_code == 400
        # count=0 仍可 format
        assert "0" in _body(resp)["message"]

    def test_不可len的迭代器用计数(self):
        err = SimpleNamespace(protected_objects=(x for x in range(2)))
        resp = protected_delete_response(None, err)
        assert "2" in _body(resp)["message"]

    def test_无count占位的message不报错(self):
        err = SimpleNamespace(protected_objects=[1])
        loader = SimpleNamespace(get=lambda key: "对象正在使用")
        resp = protected_delete_response(loader, err, message_key="x")
        assert _body(resp)["message"] == "对象正在使用"


# ---------------------------------------------------------------------------
# by_vendor action (真实 DB,经 DRF as_view 路由)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestByVendor:
    """用真实 LLMModelViewSet(混入 VendorModelMixin)经 DRF 路由驱动 by_vendor。"""

    def _su(self, groups=None):
        from apps.base.models import User

        u = User.objects.create_user(
            username=f"bv_su_{User.objects.count()}",
            password="x",
            domain="domain.com",
            locale="en",
            group_list=groups if groups is not None else [{"id": 1, "name": "T1"}],
        )
        u.is_superuser = True
        u.save()
        return u

    def _normal(self, groups):
        from apps.base.models import User

        u = User.objects.create_user(
            username=f"bv_usr_{User.objects.count()}",
            password="x",
            domain="domain.com",
            locale="en",
            group_list=groups,
        )
        u.permission = {"opspilot": {"provide_list-View"}}
        return u

    def _call(self, user, params, current_team=None):
        from rest_framework.test import APIRequestFactory, force_authenticate

        factory = APIRequestFactory()
        request = factory.get("/", params)
        force_authenticate(request, user=user)
        if current_team is not None:
            request.COOKIES["current_team"] = str(current_team)
        from apps.opspilot.viewsets.llm_view import LLMModelViewSet

        return LLMModelViewSet.as_view({"get": "by_vendor"})(request)

    def _data(self, resp):
        # DRF Response 优先用 .data(未渲染);Django JsonResponse 用 content
        if hasattr(resp, "data"):
            body = resp.data
        else:
            body = _body(resp)
        if isinstance(body, dict):
            if "data" in body:
                return body["data"]
            if "items" in body:
                return body["items"]
        return body

    def test_缺vendor返回false(self):
        resp = self._call(self._su(), {})
        assert _body(resp)["result"] is False

    def test_无current_team返回空(self):
        from apps.opspilot.models.model_provider_mgmt import ModelVendor
        from apps.opspilot.models import LLMModel

        v = ModelVendor.objects.create(name="v", vendor_type="openai", team=[1])
        LLMModel.objects.create(name="m", vendor=v, model="m", enabled=True, team=[1])
        # 未带 current_team cookie -> 解析 0 -> 返回 none() 空集
        resp = self._call(self._su(), {"vendor": str(v.id)})
        assert resp.status_code == 200
        assert len(self._data(resp)) == 0

    def test_非超管越权抛403(self):
        from apps.opspilot.models.model_provider_mgmt import ModelVendor

        v = ModelVendor.objects.create(name="v", vendor_type="openai", team=[1])
        user = self._normal([{"id": 5, "name": "G5"}])
        resp = self._call(user, {"vendor": str(v.id)}, current_team=9)
        assert resp.status_code == 403

    def test_正常按vendor和team过滤(self):
        from apps.opspilot.models import LLMModel
        from apps.opspilot.models.model_provider_mgmt import ModelVendor

        v1 = ModelVendor.objects.create(name="v1", vendor_type="openai", team=[1])
        v2 = ModelVendor.objects.create(name="v2", vendor_type="openai", team=[1])
        m_in = LLMModel.objects.create(name="in", vendor=v1, model="in", enabled=True, team=[1])
        LLMModel.objects.create(name="ov", vendor=v2, model="o", enabled=True, team=[1])

        resp = self._call(self._su(), {"vendor": str(v1.id)}, current_team=1)
        assert resp.status_code == 200
        ids = {item["id"] for item in self._data(resp)}
        assert m_in.id in ids
        # 不含其他 vendor 的模型
        assert len(ids) == 1

    def test_vendor_team不含current_team过滤掉(self):
        from apps.opspilot.models import LLMModel
        from apps.opspilot.models.model_provider_mgmt import ModelVendor

        # vendor.team 为 [2],但 current_team=1 -> vendor__team__contains=1 不命中
        v = ModelVendor.objects.create(name="v", vendor_type="openai", team=[2])
        LLMModel.objects.create(name="m", vendor=v, model="m", enabled=True, team=[1, 2])
        resp = self._call(self._su(), {"vendor": str(v.id)}, current_team=1)
        assert resp.status_code == 200
        assert len(self._data(resp)) == 0
