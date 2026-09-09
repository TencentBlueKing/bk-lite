from collections import defaultdict
from time import monotonic
from typing import Dict, List

from apps.alerts.enrichment.providers.base import EnrichmentProvider, FetchBatchResult, register_provider
from apps.core.logger import alert_logger as logger
from apps.rpc.cmdb import CMDB


@register_provider
class CMDBProvider(EnrichmentProvider):
    provider_type = "cmdb"

    def fetch_batch(self, keys: List, config: Dict) -> Dict | FetchBatchResult:
        authorized_team_ids = list(config.get("_authorized_team_ids") or [])
        if not authorized_team_ids:
            logger.warning("[Enrichment] CMDB 查询缺少组织上下文，拒绝查询")
            return {key: [] for key in keys}
        # 按 model_id 分组，收集 UUID / inst_name
        by_model_uuids = defaultdict(list)
        by_model_names = defaultdict(list)
        key_meta = {}  # key -> (model_id, lookup_value)
        for key in keys:
            params = dict(key)
            model_id = params.get("model_id")
            if not model_id:
                continue
            if params.get("inst_uuid"):
                by_model_uuids[model_id].append(params["inst_uuid"])
                key_meta[key] = (model_id, str(params["inst_uuid"]))
            elif params.get("inst_name"):
                by_model_names[model_id].append(params["inst_name"])
                key_meta[key] = (model_id, str(params["inst_name"]))

        fetched = {}  # (model_id, value) -> instance
        failed_keys = set()
        budget_exhausted_keys = set()
        query_timeout = config.get("query_timeout_seconds", 3)
        try:
            query_timeout = max(1, min(int(query_timeout), 10))
        except (TypeError, ValueError):
            query_timeout = 3
        deadline_at = config.get("_deadline_at")

        def remaining_timeout(group_keys):
            if deadline_at is None:
                return query_timeout
            try:
                remaining = float(deadline_at) - monotonic()
            except (TypeError, ValueError):
                return query_timeout
            if remaining <= 0:
                failed_keys.update(group_keys)
                budget_exhausted_keys.update(group_keys)
                return None
            return max(0.05, min(query_timeout, remaining))

        client = CMDB()
        for model_id, inst_uuids in by_model_uuids.items():
            group_keys = {key for key, meta in key_meta.items() if meta[0] == model_id and meta[1] in {str(value) for value in inst_uuids}}
            group_timeout = remaining_timeout(group_keys)
            if group_timeout is None:
                continue
            try:
                res = client.search_instances_batch(
                    params={
                        "protocol_version": "2",
                        "model_id": model_id,
                        "inst_uuids": inst_uuids,
                        "organization_ids": authorized_team_ids,
                    },
                    _timeout=group_timeout,
                )
                for value, inst in res.items():
                    fetched[(model_id, str(value))] = inst
            except Exception:
                logger.error("[Enrichment] CMDB 批量查询失败 model_id=%s", model_id, exc_info=True)
                failed_keys.update(group_keys)
        for model_id, names in by_model_names.items():
            group_keys = {key for key, meta in key_meta.items() if meta[0] == model_id and meta[1] in {str(value) for value in names}}
            group_timeout = remaining_timeout(group_keys)
            if group_timeout is None:
                continue
            try:
                res = client.search_instances_batch(
                    params={
                        "protocol_version": "2",
                        "model_id": model_id,
                        "inst_names": names,
                        "organization_ids": authorized_team_ids,
                    },
                    _timeout=group_timeout,
                )
                for value, inst in res.items():
                    fetched[(model_id, str(value))] = inst
            except Exception:
                logger.error("[Enrichment] CMDB 批量查询失败(name) model_id=%s", model_id, exc_info=True)
                failed_keys.update(group_keys)

        result = {}
        for key in keys:
            meta = key_meta.get(key)
            inst = fetched.get(meta) if meta else None
            result[key] = [inst] if inst else []
        if failed_keys:
            return FetchBatchResult(
                records=result,
                failed_keys=failed_keys,
                budget_exhausted_keys=budget_exhausted_keys,
            )
        return result
