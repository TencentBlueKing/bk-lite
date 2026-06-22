import logging
from collections import defaultdict
from typing import Dict, List

from apps.rpc.cmdb import CMDB
from apps.alerts.enrichment.providers.base import EnrichmentProvider, register_provider

logger = logging.getLogger(__name__)


@register_provider
class CMDBProvider(EnrichmentProvider):
    provider_type = "cmdb"

    def fetch_batch(self, keys: List, config: Dict) -> Dict:
        # 按 model_id 分组，收集 id / inst_name
        by_model_ids = defaultdict(list)
        by_model_names = defaultdict(list)
        key_meta = {}  # key -> (model_id, lookup_value)
        for key in keys:
            params = dict(key)
            model_id = params.get("model_id")
            if not model_id:
                continue
            if params.get("_id"):
                by_model_ids[model_id].append(params["_id"])
                key_meta[key] = (model_id, str(params["_id"]))
            elif params.get("inst_name"):
                by_model_names[model_id].append(params["inst_name"])
                key_meta[key] = (model_id, str(params["inst_name"]))

        fetched = {}  # (model_id, value) -> instance
        client = CMDB()
        for model_id, ids in by_model_ids.items():
            try:
                res = client.search_instances_batch(model_id=model_id, ids=ids)
                for value, inst in res.items():
                    fetched[(model_id, str(value))] = inst
            except Exception:
                logger.error("[Enrichment] CMDB 批量查询失败 model_id=%s", model_id, exc_info=True)
        for model_id, names in by_model_names.items():
            try:
                res = client.search_instances_batch(model_id=model_id, inst_names=names)
                for value, inst in res.items():
                    fetched[(model_id, str(value))] = inst
            except Exception:
                logger.error("[Enrichment] CMDB 批量查询失败(name) model_id=%s", model_id, exc_info=True)

        result = {}
        for key in keys:
            meta = key_meta.get(key)
            inst = fetched.get(meta) if meta else None
            result[key] = [inst] if inst else []
        return result
