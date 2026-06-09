import logging
from collections import defaultdict
from typing import ContextManager, cast

from django.db import transaction

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.safe_requests import safe_get_llm_endpoint
from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import ANTHROPIC_INVALID_API_KEY_ERROR, AnthropicCompatibleAdapter
from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider

logger = logging.getLogger(__name__)

OPENAI_COMPATIBLE_VENDOR_TYPES = {"openai", "azure", "deepseek", "other"}


class ModelVendorSyncService:
    @staticmethod
    def _get_loader(locale=None):
        return LanguageLoader(app="opspilot", default_lang=locale or "en")

    @staticmethod
    def is_supported(vendor):
        """检查供应商是否支持模型同步"""
        # anthropic 类型不支持模型同步（Anthropic API 不提供 /models 端点）
        if vendor.vendor_type == "anthropic":
            return False
        # other 类型根据 protocol_type 判断
        if vendor.vendor_type == "other":
            return True  # 无论 openai 还是 anthropic 协议都支持
        # 其他 OpenAI 兼容类型
        return vendor.vendor_type in OPENAI_COMPATIBLE_VENDOR_TYPES

    @staticmethod
    def _get_protocol_type(vendor):
        """获取供应商的协议类型"""
        if vendor.vendor_type == "anthropic":
            return "anthropic"
        # deepseek 和 other 类型支持协议选择
        if vendor.vendor_type in ("deepseek", "other"):
            return getattr(vendor, "protocol_type", "openai") or "openai"
        return "openai"

    @staticmethod
    def classify_model_type(model_id):
        model_name = (model_id or "").lower()
        if any(keyword in model_name for keyword in ["rerank", "reranker", "rankgpt"]):
            return "rerank"
        if any(keyword in model_name for keyword in ["embed", "embedding", "bge-m3", "voyage"]):
            return "embed"
        if any(keyword in model_name for keyword in ["ocr", "olmocr"]):
            return "ocr"
        return "llm"

    @classmethod
    def fetch_models_with_credentials(cls, api_base, api_key, protocol_type="openai", locale=None):
        """根据协议类型获取模型列表

        注意：Anthropic API 不提供 /models 端点，此方法仅支持 OpenAI 兼容协议。
        对于 Anthropic 协议，请使用 test_anthropic_connection 验证连接。
        """
        loader = cls._get_loader(locale)
        if protocol_type == "anthropic":
            raise ValueError(loader.get("error.anthropic_no_models_endpoint", "Anthropic API 不支持模型列表查询，请手动添加模型"))
        return cls._fetch_openai_models(api_base, api_key, locale)

    @classmethod
    def _fetch_openai_models(cls, api_base, api_key, locale=None):
        """获取 OpenAI 兼容 API 的模型列表"""
        loader = cls._get_loader(locale)
        normalized_api_base = (api_base or "").rstrip("/")
        if not normalized_api_base:
            raise ValueError(loader.get("error.vendor_api_base_required", "供应商 API 地址不能为空"))
        if not api_key:
            raise ValueError(loader.get("error.vendor_api_key_required", "供应商 API Key 不能为空"))
        response = safe_get_llm_endpoint(
            f"{normalized_api_base}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", []) if isinstance(payload, dict) else []

    @classmethod
    def test_anthropic_connection(cls, api_base, api_key, model=None, locale=None):
        """测试 Anthropic 协议连接

        用于验证 Anthropic 协议端点是否可用，支持自定义模型（如 DeepSeek）。

        Args:
            api_base: API 基础地址
            api_key: API 密钥
            model: 用于测试的模型名称，默认使用 claude-3-haiku-20240307
            locale: 语言环境
        """
        loader = cls._get_loader(locale)
        if not api_key:
            raise ValueError(loader.get("error.vendor_api_key_required", "供应商 API Key 不能为空"))

        test_model = model or "claude-3-haiku-20240307"
        try:
            AnthropicCompatibleAdapter.validate_minimal_connection(api_base, api_key, test_model)
        except ValueError as exc:
            if str(exc) == ANTHROPIC_INVALID_API_KEY_ERROR:
                raise ValueError(loader.get("error.vendor_api_key_invalid", "API Key 无效")) from exc
            raise

    @classmethod
    def sync_vendor_models(cls, vendor, locale=None):
        loader = cls._get_loader(locale)
        if not cls.is_supported(vendor):
            if vendor.vendor_type == "anthropic":
                raise ValueError(loader.get("error.anthropic_sync_not_supported", "Anthropic API 不支持模型同步，请手动添加模型"))
            raise ValueError(loader.get("error.vendor_sync_not_supported", "当前仅支持 OpenAI-compatible 供应商同步"))

        # 所有支持同步的供应商都使用 OpenAI /models 端点
        # 对于 deepseek 使用 anthropic 协议的情况，需要转换 API base
        api_base = vendor.api_base
        if vendor.vendor_type == "deepseek" and vendor.protocol_type == "anthropic":
            # DeepSeek Anthropic 协议的 api_base 可能是 https://api.deepseek.com/anthropic
            # 模型同步需要用 https://api.deepseek.com/v1
            api_base = (api_base or "").replace("/anthropic", "/v1").rstrip("/")
            if not api_base.endswith("/v1"):
                api_base = "https://api.deepseek.com/v1"
        remote_models = cls._fetch_openai_models(api_base, vendor.decrypted_api_key, locale=locale)
        grouped = defaultdict(list)
        for item in remote_models:
            model_id = item.get("id", "")
            if not model_id:
                continue
            grouped[cls.classify_model_type(model_id)].append(model_id)

        result = {}
        atomic_context = cast(ContextManager[None], transaction.atomic())
        with atomic_context:
            result["llm_models"] = cls._upsert_models(LLMModel, vendor, grouped.get("llm", []), is_build_in=True)
            result["embed_models"] = cls._upsert_models(EmbedProvider, vendor, grouped.get("embed", []), is_build_in=False)
            result["rerank_models"] = cls._upsert_models(RerankProvider, vendor, grouped.get("rerank", []), is_build_in=False)
            result["ocr_models"] = cls._upsert_models(OCRProvider, vendor, grouped.get("ocr", []), is_build_in=True)
        return result

    @staticmethod
    def _upsert_models(model_class, vendor, model_ids, is_build_in):
        existing_map = {obj.model: obj for obj in model_class.objects.filter(vendor=vendor, model__in=model_ids)}
        create_list = []
        update_list = []
        for model_id in model_ids:
            existing = existing_map.get(model_id)
            if existing:
                changed = False
                if existing.name != model_id:
                    existing.name = model_id
                    changed = True
                if existing.team != vendor.team:
                    existing.team = vendor.team
                    changed = True
                if not existing.enabled:
                    existing.enabled = True
                    changed = True
                if getattr(existing, "is_build_in", None) != is_build_in:
                    existing.is_build_in = is_build_in
                    changed = True
                if changed:
                    update_list.append(existing)
                continue
            create_list.append(
                model_class(
                    name=model_id,
                    vendor=vendor,
                    model=model_id,
                    enabled=True,
                    team=vendor.team,
                    is_build_in=is_build_in,
                )
            )
        if create_list:
            model_class.objects.bulk_create(create_list, batch_size=100)
        if update_list:
            model_class.objects.bulk_update(update_list, ["name", "team", "enabled", "is_build_in"], batch_size=100)
        return {
            "created": len(create_list),
            "updated": len(update_list),
            "models": model_ids,
        }
