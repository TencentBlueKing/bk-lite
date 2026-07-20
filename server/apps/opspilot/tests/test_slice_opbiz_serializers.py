"""opspilot-biz 切片: serializers 真实逻辑测试。

聚焦序列化器中无网络/可独立验证的真实逻辑：
- ModelVendorSerializer.update：未传 api_key 时保留原值（跳过更新）
- ModelVendorTestConnectionSerializer.validate：密码变更/未变更两条分支（含 DB 取回）
- LLMSerializer.get_rag_score_threshold / get_skill_params(掩码) / get_llm_model_name
- CustomProviderSerializer.get_vendor_name / get_vendor_type（基于 vendor_map）

涉及 ModelVendor 查询/解密的用例用真实 DB；纯方法用最小替身对象。
"""

from types import SimpleNamespace

import pytest

from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.serializers.llm_serializer import LLMSerializer
from apps.opspilot.serializers.model_vendor_serializer import (
    CustomProviderSerializer,
    ModelVendorSerializer,
    ModelVendorTestConnectionSerializer,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# ModelVendorSerializer.update
# ---------------------------------------------------------------------------


class TestModelVendorSerializerUpdate:
    def test_未传api_key保留原值(self, mocker):
        ser = ModelVendorSerializer()
        instance = SimpleNamespace()
        captured = {}

        def fake_super_update(inst, data):
            captured["data"] = data
            return inst

        mocker.patch(
            "apps.opspilot.serializers.model_vendor_serializer.serializers.ModelSerializer.update",
            side_effect=fake_super_update,
        )
        ser.update(instance, {"name": "n", "api_key": ""})
        # 空 api_key 被弹出，不会落库覆盖
        assert "api_key" not in captured["data"]
        assert captured["data"]["name"] == "n"

    def test_传非空api_key保留(self, mocker):
        ser = ModelVendorSerializer()
        captured = {}
        mocker.patch(
            "apps.opspilot.serializers.model_vendor_serializer.serializers.ModelSerializer.update",
            side_effect=lambda inst, data: captured.update(data) or inst,
        )
        ser.update(SimpleNamespace(), {"name": "n", "api_key": "sk-new"})
        assert captured["api_key"] == "sk-new"

    def test_get_api_key_display_脱敏(self):
        ser = ModelVendorSerializer()
        assert ser.get_api_key_display(SimpleNamespace(api_key="cipher")) == "******"
        assert ser.get_api_key_display(SimpleNamespace(api_key="")) == ""


# ---------------------------------------------------------------------------
# ModelVendorTestConnectionSerializer.validate
# ---------------------------------------------------------------------------


class TestTestConnectionSerializer:
    def test_密码变更需api_key(self):
        ser = ModelVendorTestConnectionSerializer(
            data={"api_base": "https://x", "password_changed": True, "api_key": ""}
        )
        assert not ser.is_valid()
        assert "api_key" in ser.errors

    def test_密码变更解析为输入key(self):
        ser = ModelVendorTestConnectionSerializer(
            data={"api_base": "https://x", "password_changed": True, "api_key": "sk-in"}
        )
        assert ser.is_valid(), ser.errors
        assert ser.validated_data["resolved_api_key"] == "sk-in"

    def test_未变更密码需original_id(self):
        ser = ModelVendorTestConnectionSerializer(
            data={"api_base": "https://x", "password_changed": False}
        )
        assert not ser.is_valid()
        assert "original_id" in ser.errors

    def test_未变更密码original_id不存在(self):
        ser = ModelVendorTestConnectionSerializer(
            data={"api_base": "https://x", "password_changed": False, "original_id": 999999}
        )
        assert not ser.is_valid()
        assert "original_id" in ser.errors

    def test_未变更密码从db取回解密key(self):
        vendor = ModelVendor.objects.create(
            name="v-conn", api_base="https://b", api_key="sk-stored", team=[1]
        )
        ser = ModelVendorTestConnectionSerializer(
            data={"api_base": "https://x", "password_changed": False, "original_id": vendor.id}
        )
        assert ser.is_valid(), ser.errors
        # resolved_api_key 为 DB 中密文解密后的明文
        assert ser.validated_data["resolved_api_key"] == "sk-stored"


# ---------------------------------------------------------------------------
# LLMSerializer SerializerMethodFields
# ---------------------------------------------------------------------------


class TestLLMSerializerMethods:
    @pytest.mark.skip(reason="LLMSerializer.get_rag_score_threshold 已随 RAG 功能一起删除,后续单独 PR 重启用")
    def test_rag_score_threshold_转列表(self):
        inst = SimpleNamespace(rag_score_threshold_map={"kb1": 0.5, "kb2": 0.8})
        out = LLMSerializer.get_rag_score_threshold(inst)
        assert {"knowledge_base": "kb1", "score": 0.5} in out
        assert {"knowledge_base": "kb2", "score": 0.8} in out
        assert len(out) == 2

    def test_llm_model_name_有模型(self):
        ser = LLMSerializer.__new__(LLMSerializer)
        inst = SimpleNamespace(llm_model=SimpleNamespace(name="gpt-4o"))
        assert ser.get_llm_model_name(inst) == "gpt-4o"

    def test_llm_model_name_无模型返回空(self):
        ser = LLMSerializer.__new__(LLMSerializer)
        inst = SimpleNamespace(llm_model=None)
        assert ser.get_llm_model_name(inst) == ""

    def test_skill_params_掩码password(self):
        inst = SimpleNamespace(
            skill_params=[
                {"key": "pwd", "value": "real-secret", "type": "password"},
                {"key": "host", "value": "1.1.1.1", "type": "string"},
            ]
        )
        out = LLMSerializer.get_skill_params(inst)
        pwd = next(p for p in out if p["key"] == "pwd")
        host = next(p for p in out if p["key"] == "host")
        assert pwd["value"] == "******"
        assert host["value"] == "1.1.1.1"
        # 不修改原对象
        assert inst.skill_params[0]["value"] == "real-secret"

    def test_skill_params_空返回空列表(self):
        assert LLMSerializer.get_skill_params(SimpleNamespace(skill_params=None)) == []


# ---------------------------------------------------------------------------
# CustomProviderSerializer.get_vendor_name / get_vendor_type
# ---------------------------------------------------------------------------


class TestCustomProviderSerializer:
    @staticmethod
    def _ctx():
        # TeamSerializer.__init__ 需要 request.user.group_list
        request = SimpleNamespace(user=SimpleNamespace(group_list=[{"id": 1, "name": "Default"}]))
        return {"request": request}

    def test_vendor_name_type_来自map(self):
        ModelVendor.objects.create(
            id=7001, name="厂商A", vendor_type="anthropic", api_base="b", team=[1]
        )
        ser = CustomProviderSerializer(context=self._ctx())
        inst = SimpleNamespace(vendor_id=7001)
        assert ser.get_vendor_name(inst) == "厂商A"
        assert ser.get_vendor_type(inst) == "anthropic"

    def test_无vendor_id返回空(self):
        ser = CustomProviderSerializer(context=self._ctx())
        inst = SimpleNamespace(vendor_id=None)
        assert ser.get_vendor_name(inst) == ""
        assert ser.get_vendor_type(inst) == ""

    def test_vendor_id不在map返回空(self):
        ser = CustomProviderSerializer(context=self._ctx())
        inst = SimpleNamespace(vendor_id=8888888)
        assert ser.get_vendor_name(inst) == ""
        assert ser.get_vendor_type(inst) == ""
