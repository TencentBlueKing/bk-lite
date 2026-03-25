import logging
from collections import defaultdict

import requests
from django.db import transaction

from apps.opspilot.models import EmbedProvider, LLMModel, OCRProvider, RerankProvider

logger = logging.getLogger(__name__)

OPENAI_COMPATIBLE_VENDOR_TYPES = {"openai", "azure", "deepseek", "other"}


class ModelVendorSyncService:
    @staticmethod
    def is_supported(vendor):
        return vendor.vendor_type in OPENAI_COMPATIBLE_VENDOR_TYPES

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

    @staticmethod
    def fetch_vendor_models(vendor):
        api_base = (vendor.api_base or "").rstrip("/")
        if not api_base:
            raise ValueError("供应商 API 地址不能为空")
        response = requests.get(
            f"{api_base}/models",
            headers={"Authorization": f"Bearer {vendor.decrypted_api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", []) if isinstance(payload, dict) else []

    @classmethod
    def sync_vendor_models(cls, vendor):
        if not cls.is_supported(vendor):
            raise ValueError("当前仅支持 OpenAI-compatible 供应商同步")

        remote_models = cls.fetch_vendor_models(vendor)
        grouped = defaultdict(list)
        for item in remote_models:
            model_id = item.get("id", "")
            if not model_id:
                continue
            grouped[cls.classify_model_type(model_id)].append(model_id)

        result = {}
        with transaction.atomic():
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
