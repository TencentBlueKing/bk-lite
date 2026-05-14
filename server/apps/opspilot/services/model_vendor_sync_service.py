import logging
from collections import defaultdict
from typing import ContextManager, cast

import requests
from django.db import transaction

from apps.core.utils.loader import LanguageLoader
from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider

logger = logging.getLogger(__name__)

OPENAI_COMPATIBLE_VENDOR_TYPES = {"openai", "azure", "deepseek", "other"}
ANTHROPIC_COMPATIBLE_VENDOR_TYPES = {"anthropic"}

# Anthropic 官方模型列表（API 不提供 /models 端点，需要硬编码）
ANTHROPIC_KNOWN_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
]


class ModelVendorSyncService:
    @staticmethod
    def _get_loader(locale=None):
        return LanguageLoader(app="opspilot", default_lang=locale or "en")

    @staticmethod
    def is_supported(vendor):
        """检查供应商是否支持模型同步"""
        # anthropic 类型始终支持
        if vendor.vendor_type in ANTHROPIC_COMPATIBLE_VENDOR_TYPES:
            return True
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
        """根据协议类型获取模型列表"""
        if protocol_type == "anthropic":
            return cls._fetch_anthropic_models(api_base, api_key, locale)
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
        response = requests.get(
            f"{normalized_api_base}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", []) if isinstance(payload, dict) else []

    @classmethod
    def _fetch_anthropic_models(cls, api_base, api_key, locale=None):
        """获取 Anthropic 模型列表

        Anthropic API 不提供 /models 端点，返回预定义的模型列表。
        如果提供了 API 凭证，会尝试验证连接。
        """
        loader = cls._get_loader(locale)
        if not api_key:
            raise ValueError(loader.get("error.vendor_api_key_required", "供应商 API Key 不能为空"))

        # 使用官方地址或用户指定的地址
        normalized_api_base = (api_base or "https://api.anthropic.com").rstrip("/")

        # 尝试验证 API 连接（使用一个简单的请求）
        try:
            # Anthropic 没有 /models 端点，我们用一个最小的 messages 请求来验证凭证
            response = requests.post(
                f"{normalized_api_base}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                timeout=15,
            )
            # 如果是认证错误，抛出异常
            if response.status_code == 401:
                raise ValueError(loader.get("error.vendor_api_key_invalid", "API Key 无效"))
            # 其他错误（如 rate limit）不影响模型列表返回
        except requests.exceptions.RequestException as e:
            # 网络错误时记录日志但仍返回模型列表
            logger.warning(f"Anthropic API 连接验证失败: {e}")

        # 返回预定义的模型列表（格式与 OpenAI 兼容）
        return [{"id": model_id} for model_id in ANTHROPIC_KNOWN_MODELS]

    @classmethod
    def sync_vendor_models(cls, vendor, locale=None):
        if not cls.is_supported(vendor):
            loader = cls._get_loader(locale)
            raise ValueError(loader.get("error.vendor_sync_not_supported", "当前仅支持 OpenAI-compatible 供应商同步"))

        protocol_type = cls._get_protocol_type(vendor)
        remote_models = cls.fetch_models_with_credentials(vendor.api_base, vendor.decrypted_api_key, protocol_type=protocol_type, locale=locale)
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
