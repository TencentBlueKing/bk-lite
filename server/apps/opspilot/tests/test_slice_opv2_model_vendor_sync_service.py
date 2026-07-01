"""opspilot-views2 切片: services/model_vendor_sync_service.ModelVendorSyncService 真实测试。

只 mock 唯一外部边界 safe_get_llm_endpoint(HTTP requests),返回真实形态的
OpenAI /models 响应;upsert 走真实 ORM 落库,断言分类/创建/更新副作用。
另含 is_supported / _get_protocol_type / classify_model_type / fetch_*(协议/校验)
等纯逻辑分支。
"""

import pydantic.root_model  # noqa
import pytest
from types import SimpleNamespace

from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider
from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService as Svc

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 纯逻辑: classify_model_type
# ---------------------------------------------------------------------------
class TestClassify:
    @pytest.mark.parametrize(
        "model_id,expected",
        [
            ("bge-reranker-v2", "rerank"),
            ("rankgpt-1", "rerank"),
            ("text-embedding-3-large", "embed"),
            ("bge-m3", "embed"),
            ("voyage-2", "embed"),
            ("olmocr-7b", "ocr"),
            ("got-ocr2", "ocr"),
            ("gpt-4o", "llm"),
            ("", "llm"),
            (None, "llm"),
        ],
    )
    def test_分类(self, model_id, expected):
        assert Svc.classify_model_type(model_id) == expected


# ---------------------------------------------------------------------------
# 纯逻辑: is_supported / _get_protocol_type
# ---------------------------------------------------------------------------
class TestSupportProtocol:
    def test_anthropic不支持同步(self):
        v = SimpleNamespace(vendor_type="anthropic", protocol_type="anthropic")
        assert Svc.is_supported(v) is False
        assert Svc._get_protocol_type(v) == "anthropic"

    def test_other总是支持(self):
        v = SimpleNamespace(vendor_type="other", protocol_type="anthropic")
        assert Svc.is_supported(v) is True
        # other 跟随 protocol_type
        assert Svc._get_protocol_type(v) == "anthropic"

    def test_openai兼容类型支持(self):
        for t in ("openai", "azure", "deepseek"):
            assert Svc.is_supported(SimpleNamespace(vendor_type=t, protocol_type="openai")) is True

    def test_deepseek协议跟随(self):
        assert Svc._get_protocol_type(SimpleNamespace(vendor_type="deepseek", protocol_type="anthropic")) == "anthropic"
        # 缺省回退 openai
        assert Svc._get_protocol_type(SimpleNamespace(vendor_type="deepseek", protocol_type="")) == "openai"

    def test_未知类型不支持(self):
        assert Svc.is_supported(SimpleNamespace(vendor_type="zhipu", protocol_type="openai")) is False
        # zhipu 协议固定 openai
        assert Svc._get_protocol_type(SimpleNamespace(vendor_type="zhipu", protocol_type="x")) == "openai"


# ---------------------------------------------------------------------------
# fetch_models_with_credentials: 协议/校验分支
# ---------------------------------------------------------------------------
class TestFetch:
    def test_anthropic协议拒绝(self):
        with pytest.raises(ValueError):
            Svc.fetch_models_with_credentials("http://api", "key", protocol_type="anthropic")

    def test_缺api_base拒绝(self):
        with pytest.raises(ValueError):
            Svc.fetch_models_with_credentials("", "key", protocol_type="openai")

    def test_缺api_key拒绝(self):
        with pytest.raises(ValueError):
            Svc.fetch_models_with_credentials("http://api", "", protocol_type="openai")

    def test_正常返回data列表(self, mocker):
        resp = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "gpt-4o"}, {"id": "bge-m3"}]},
        )
        getter = mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.safe_get_llm_endpoint",
            return_value=resp,
        )
        out = Svc.fetch_models_with_credentials("http://api.x.com/v1/", "key", protocol_type="openai")
        assert out == [{"id": "gpt-4o"}, {"id": "bge-m3"}]
        # 真实拼接 /models 端点 + Bearer 头(契约断言)
        called_url = getter.call_args[0][0]
        assert called_url == "http://api.x.com/v1/models"
        assert getter.call_args.kwargs["headers"]["Authorization"] == "Bearer key"

    def test_非dict_payload返回空(self, mocker):
        resp = SimpleNamespace(raise_for_status=lambda: None, json=lambda: ["x"])
        mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.safe_get_llm_endpoint",
            return_value=resp,
        )
        assert Svc.fetch_models_with_credentials("http://api", "key") == []


# ---------------------------------------------------------------------------
# test_anthropic_connection: 错误翻译分支
# ---------------------------------------------------------------------------
class TestAnthropicConnection:
    def test_缺key抛错(self):
        with pytest.raises(ValueError):
            Svc.test_anthropic_connection("http://api", "")

    def test_invalid_key被翻译(self, mocker):
        from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import ANTHROPIC_INVALID_API_KEY_ERROR

        mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.AnthropicCompatibleAdapter.validate_minimal_connection",
            side_effect=ValueError(ANTHROPIC_INVALID_API_KEY_ERROR),
        )
        with pytest.raises(ValueError):
            Svc.test_anthropic_connection("http://api", "bad-key")

    def test_其他valueerror原样抛出(self, mocker):
        mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.AnthropicCompatibleAdapter.validate_minimal_connection",
            side_effect=ValueError("network timeout"),
        )
        with pytest.raises(ValueError, match="network timeout"):
            Svc.test_anthropic_connection("http://api", "key", model="deepseek-chat")

    def test_成功默认模型(self, mocker):
        m = mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.AnthropicCompatibleAdapter.validate_minimal_connection",
        )
        Svc.test_anthropic_connection("http://api", "key")
        # 默认 claude haiku 模型
        assert m.call_args[0][2] == "claude-3-haiku-20240307"


# ---------------------------------------------------------------------------
# sync_vendor_models: 真实 DB upsert
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSyncVendorModels:
    def _vendor(self, vendor_type="openai", protocol_type="openai", team=None):
        return ModelVendor.objects.create(
            name="v1",
            vendor_type=vendor_type,
            protocol_type=protocol_type,
            api_base="http://api.x.com/v1",
            api_key="sk-test",
            team=team if team is not None else [1],
        )

    def test_anthropic拒绝同步(self):
        v = self._vendor(vendor_type="anthropic")
        with pytest.raises(ValueError):
            Svc.sync_vendor_models(v)

    def test_不支持类型拒绝(self):
        v = self._vendor(vendor_type="zhipu")
        with pytest.raises(ValueError):
            Svc.sync_vendor_models(v)

    def test_全量分类创建落库(self, mocker):
        v = self._vendor(team=[7])
        resp = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": [
                    {"id": "gpt-4o"},
                    {"id": "text-embedding-3-small"},
                    {"id": "bge-reranker-base"},
                    {"id": "olmocr-7b"},
                    {"id": ""},  # 空 id 跳过
                ]
            },
        )
        mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.safe_get_llm_endpoint",
            return_value=resp,
        )
        result = Svc.sync_vendor_models(v)

        assert result["llm_models"]["created"] == 1
        assert result["embed_models"]["created"] == 1
        assert result["rerank_models"]["created"] == 1
        assert result["ocr_models"]["created"] == 1
        # 真实落库 + team 继承自 vendor
        llm = LLMModel.objects.get(vendor=v, model="gpt-4o")
        assert llm.enabled is True
        assert llm.team == [7]
        assert llm.is_build_in is True
        emb = EmbedProvider.objects.get(vendor=v, model="text-embedding-3-small")
        assert emb.is_build_in is False
        assert RerankProvider.objects.filter(vendor=v, model="bge-reranker-base").exists()
        assert OCRProvider.objects.filter(vendor=v, model="olmocr-7b").exists()

    def test_已存在则更新而非重复创建(self, mocker):
        v = self._vendor(team=[3])
        # 预置一个 disabled、team 不同、name 不同的旧 LLM
        LLMModel.objects.create(name="old-name", vendor=v, model="gpt-4o", enabled=False, team=[9], is_build_in=False)
        resp = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "gpt-4o"}]},
        )
        mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.safe_get_llm_endpoint",
            return_value=resp,
        )
        result = Svc.sync_vendor_models(v)

        assert result["llm_models"]["created"] == 0
        assert result["llm_models"]["updated"] == 1
        # 不重复创建
        assert LLMModel.objects.filter(vendor=v, model="gpt-4o").count() == 1
        updated = LLMModel.objects.get(vendor=v, model="gpt-4o")
        assert updated.name == "gpt-4o"  # name 同步为 model_id
        assert updated.enabled is True  # 被重新启用
        assert updated.team == [3]  # team 同步为 vendor.team
        assert updated.is_build_in is True

    def test_无变化不计入更新(self, mocker):
        v = self._vendor(team=[3])
        LLMModel.objects.create(name="gpt-4o", vendor=v, model="gpt-4o", enabled=True, team=[3], is_build_in=True)
        resp = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": [{"id": "gpt-4o"}]})
        mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.safe_get_llm_endpoint",
            return_value=resp,
        )
        result = Svc.sync_vendor_models(v)
        assert result["llm_models"]["created"] == 0
        assert result["llm_models"]["updated"] == 0

    def test_deepseek_anthropic协议转换api_base(self, mocker):
        v = self._vendor(vendor_type="deepseek", protocol_type="anthropic")
        v.api_base = "https://api.deepseek.com/anthropic"
        v.save()
        resp = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": []})
        getter = mocker.patch(
            "apps.opspilot.services.model_vendor_sync_service.safe_get_llm_endpoint",
            return_value=resp,
        )
        Svc.sync_vendor_models(v)
        # anthropic 路径被转换为 /v1/models
        assert getter.call_args[0][0] == "https://api.deepseek.com/v1/models"
