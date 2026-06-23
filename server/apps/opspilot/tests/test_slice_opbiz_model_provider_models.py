"""opspilot-biz 切片: models/model_provider_mgmt 真实 DB 行为测试。

覆盖 ModelVendor 加密 save / decrypted_api_key、LLMModel/EmbedProvider/
RerankProvider/OCRProvider 的派生属性（api_key/base_url/model_name/protocol_type/
runtime_ocr_config）。只 mock 外部边界（无），其余真实落库后断言。
"""

import pytest

from apps.opspilot.models.model_provider_mgmt import (
    EmbedProvider,
    LLMModel,
    ModelVendor,
    OCRProvider,
    RerankProvider,
)

pytestmark = pytest.mark.django_db


def _make_vendor(**kwargs):
    defaults = dict(
        name="vendor-a",
        vendor_type="openai",
        protocol_type="openai",
        api_base="https://api.example.com/v1",
        api_key="sk-plain-secret",
        enabled=True,
        team=[1],
    )
    defaults.update(kwargs)
    return ModelVendor.objects.create(**defaults)


class TestModelVendorEncryption:
    def test_save_加密api_key不落明文(self):
        v = _make_vendor(api_key="sk-plain-secret")
        v.refresh_from_db()
        # 落库值已加密，不等于明文
        assert v.api_key != "sk-plain-secret"
        assert ModelVendor._is_encrypted(v.api_key)

    def test_decrypted_api_key_还原明文(self):
        v = _make_vendor(api_key="sk-plain-secret")
        v.refresh_from_db()
        assert v.decrypted_api_key == "sk-plain-secret"

    def test_save_不重复加密(self):
        v = _make_vendor(api_key="sk-once")
        first_cipher = v.api_key
        # 再次 save 不应二次加密
        v.save()
        v.refresh_from_db()
        assert v.decrypted_api_key == "sk-once"
        # 密文保持稳定（未被重新加密成另一段）
        assert v.api_key == first_cipher

    def test_空api_key不加密(self):
        v = _make_vendor(api_key="")
        v.refresh_from_db()
        assert v.api_key == ""
        assert v.decrypted_api_key == ""


class TestLLMModelProperties:
    def test_无vendor时派生字段为默认(self):
        m = LLMModel.objects.create(name="m1", model="gpt-4")
        assert m.openai_api_key == ""
        assert m.openai_api_base == ""
        assert m.protocol_type == "openai"

    def test_有vendor复用解密key与base(self):
        v = _make_vendor(api_key="sk-llm", api_base="https://llm.base/v1")
        m = LLMModel.objects.create(name="m2", vendor=v, model="gpt-4o")
        assert m.openai_api_key == "sk-llm"
        assert m.openai_api_base == "https://llm.base/v1"

    def test_model_name_回退到name(self):
        m_with = LLMModel.objects.create(name="display", model="real-model")
        m_without = LLMModel.objects.create(name="only-name", model=None)
        assert m_with.model_name == "real-model"
        assert m_without.model_name == "only-name"

    def test_protocol_type_anthropic(self):
        v = _make_vendor(vendor_type="anthropic")
        m = LLMModel.objects.create(name="claude", vendor=v)
        assert m.protocol_type == "anthropic"

    def test_protocol_type_deepseek_使用vendor协议(self):
        v = _make_vendor(vendor_type="deepseek", protocol_type="anthropic")
        m = LLMModel.objects.create(name="ds", vendor=v)
        assert m.protocol_type == "anthropic"

    def test_protocol_type_other_空协议回退openai(self):
        v = _make_vendor(vendor_type="other", protocol_type="")
        m = LLMModel.objects.create(name="o", vendor=v)
        assert m.protocol_type == "openai"

    def test_protocol_type_未知类型回退openai(self):
        v = _make_vendor(vendor_type="openai")
        m = LLMModel.objects.create(name="x", vendor=v)
        assert m.protocol_type == "openai"


class TestEmbedRerankProviderProperties:
    def test_embed_无vendor默认值(self):
        e = EmbedProvider.objects.create(name="e1", model="text-embed")
        assert e.api_key == ""
        assert e.base_url == ""
        assert e.model_name == "text-embed"

    def test_embed_有vendor派生(self):
        v = _make_vendor(api_key="sk-embed", api_base="https://embed/v1")
        e = EmbedProvider.objects.create(name="e2", vendor=v, model=None)
        assert e.api_key == "sk-embed"
        assert e.base_url == "https://embed/v1"
        assert e.model_name == "e2"  # model 为空回退 name

    def test_rerank_有vendor派生(self):
        v = _make_vendor(api_key="sk-rerank", api_base="https://rr/v1")
        r = RerankProvider.objects.create(name="r1", vendor=v, model="bge-rerank")
        assert r.api_key == "sk-rerank"
        assert r.base_url == "https://rr/v1"
        assert r.model_name == "bge-rerank"
        assert str(r) == "r1"


class TestOCRProviderRuntimeConfig:
    def test_azure_供应商配置(self):
        v = _make_vendor(vendor_type="azure", api_key="sk-azure", api_base="https://azure.ocr")
        o = OCRProvider.objects.create(name="ocr-azure", vendor=v, model="prebuilt-read")
        cfg = o.runtime_ocr_config
        assert cfg == {
            "ocr_type": "azure_ocr",
            "endpoint": "https://azure.ocr",
            "api_key": "sk-azure",
            "model": "prebuilt-read",
        }

    def test_非azure供应商走olm默认(self):
        v = _make_vendor(vendor_type="openai", api_key="sk-olm", api_base="https://olm.ocr")
        o = OCRProvider.objects.create(name="ocr-olm", vendor=v, model=None)
        cfg = o.runtime_ocr_config
        assert cfg["ocr_type"] == "olm_ocr"
        assert cfg["base_url"] == "https://olm.ocr"
        assert cfg["endpoint"] == "https://olm.ocr"
        assert cfg["api_key"] == "sk-olm"
        # model 为空时使用默认模型名
        assert cfg["model"] == "olmOCR-7B-0225-preview"

    def test_无vendor走olm空配置(self):
        o = OCRProvider.objects.create(name="ocr-none", model="custom-ocr")
        cfg = o.runtime_ocr_config
        assert cfg["ocr_type"] == "olm_ocr"
        assert cfg["base_url"] == ""
        assert cfg["api_key"] == ""
        assert cfg["model"] == "custom-ocr"
