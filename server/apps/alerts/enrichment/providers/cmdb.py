from collections import defaultdict
from time import monotonic
from typing import Dict, List
from uuid import UUID

from apps.alerts.enrichment.providers.base import EnrichmentProvider, FetchBatchResult, register_provider
from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT
from apps.core.logger import alert_logger as logger
from apps.rpc.cmdb import CMDB

# 事件 resource_type 是监控对象名（Host、Postgres），查询要用 CMDB 模型 ID（host、postgresql）。
_MONITOR_OBJECT_TO_CMDB_MODEL = {name: model_id for model_id, name in CMDB_MODEL_TO_MONITOR_OBJECT.items()}


def _resolve_cmdb_model_id(value) -> str:
    text = str(value or "").strip()
    return _MONITOR_OBJECT_TO_CMDB_MODEL.get(text, text)


def _index_lookup_keys(keys):
    """按模型或身份键分组。身份键不带 model_id。非 UUIDv4 不进入查询。"""
    by_model_uuids = defaultdict(list)
    by_model_names = defaultdict(list)
    uuid_keys = []
    monitor_keys = []
    key_meta = {}
    skipped_invalid_uuids = 0
    for key in keys:
        params = dict(key)
        raw_model_id = params.get("model_id")
        model_id = _resolve_cmdb_model_id(raw_model_id) if raw_model_id else raw_model_id
        if not model_id:
            skipped_invalid_uuids += _remember_identity_key(key, params, uuid_keys, monitor_keys, key_meta)
            continue
        raw_uuid = params.get("inst_uuid")
        if raw_uuid:
            inst_uuid = _canonical_inst_uuid(raw_uuid)
            if not inst_uuid:
                skipped_invalid_uuids += 1
                continue
            by_model_uuids[model_id].append(inst_uuid)
            key_meta[key] = (model_id, inst_uuid)
        elif params.get("inst_name"):
            by_model_names[model_id].append(params["inst_name"])
            key_meta[key] = (model_id, str(params["inst_name"]))
    return by_model_uuids, by_model_names, uuid_keys, monitor_keys, key_meta, skipped_invalid_uuids


def _remember_identity_key(key, params, uuid_keys, monitor_keys, key_meta) -> int:
    raw_uuid = params.get("inst_uuid")
    if raw_uuid:
        inst_uuid = _canonical_inst_uuid(raw_uuid)
        if inst_uuid:
            uuid_keys.append(key)
            key_meta[key] = ("__uuid__", inst_uuid)
            return 0
        if params.get("monitor_id"):
            monitor_keys.append(key)
            key_meta[key] = ("__monitor__", str(params["monitor_id"]))
        return 1
    if params.get("monitor_id"):
        monitor_keys.append(key)
        key_meta[key] = ("__monitor__", str(params["monitor_id"]))
    return 0


def _fetch_model_groups(client, groups, param_name, log_suffix, authorized_team_ids, key_meta, fetched, failed_keys, remaining_timeout):
    for model_id, values in groups.items():
        value_set = {str(value) for value in values}
        group_keys = {key for key, meta in key_meta.items() if meta[0] == model_id and meta[1] in value_set}
        group_timeout = remaining_timeout(group_keys)
        if group_timeout is None:
            continue
        try:
            res = client.search_instances_batch(
                params={
                    "protocol_version": "2",
                    "model_id": model_id,
                    param_name: values,
                    "organization_ids": authorized_team_ids,
                },
                _timeout=group_timeout,
            )
            for value, inst in res.items():
                fetched[(model_id, str(value))] = inst
        except Exception:
            logger.error("[Enrichment] CMDB 批量查询失败%s model_id=%s", log_suffix, model_id, exc_info=True)
            failed_keys.update(group_keys)


def _fetch_unscoped_uuids(client, uuid_keys, monitor_keys, key_meta, authorized_team_ids, fetched, failed_keys, remaining_timeout):
    unique_uuids = []
    for key in uuid_keys:
        value = key_meta.get(key, (None, None))[1]
        if value and value not in unique_uuids:
            unique_uuids.append(value)
    group_timeout = remaining_timeout(set(uuid_keys))
    uuid_failed = group_timeout is None
    uuid_result = None
    if group_timeout is not None:
        try:
            uuid_result = client.search_instances_batch(
                params={
                    "protocol_version": "2",
                    "inst_uuids": unique_uuids,
                    "organization_ids": authorized_team_ids,
                },
                _timeout=group_timeout,
            )
        except Exception:
            logger.error("[Enrichment] CMDB 批量查询失败 locator=%s", "inst_uuid", exc_info=True)
            failed_keys.update(uuid_keys)
            uuid_failed = True
    if uuid_result is not None:
        _store_uuid_hits(uuid_result, uuid_keys, monitor_keys, key_meta, fetched, failed_keys)
    elif uuid_failed:
        failed_keys.update(uuid_keys)


def _store_uuid_hits(uuid_result, uuid_keys, monitor_keys, key_meta, fetched, failed_keys):
    for value, inst in uuid_result.items():
        fetched[("__uuid__", str(value))] = inst
    for key in uuid_keys:
        if key in failed_keys or fetched.get(key_meta.get(key)):
            continue
        monitor_id = str(dict(key).get("monitor_id") or "").strip()
        if not monitor_id:
            continue
        key_meta[key] = ("__monitor__", monitor_id)
        monitor_keys.append(key)


def _fetch_monitor_ids(client, monitor_keys, key_meta, authorized_team_ids, fetched, failed_keys, remaining_timeout):
    unique_monitor_ids = []
    for key in monitor_keys:
        value = key_meta.get(key, (None, None))[1]
        if value and value not in unique_monitor_ids:
            unique_monitor_ids.append(value)
    group_keys = set(monitor_keys)
    group_timeout = remaining_timeout(group_keys)
    if group_timeout is None:
        return
    try:
        res = client.search_instances_batch(
            params={
                "protocol_version": "2",
                "monitor_ids": unique_monitor_ids,
                "organization_ids": authorized_team_ids,
            },
            _timeout=group_timeout,
        )
        for value, inst in res.items():
            fetched[("__monitor__", str(value))] = inst
    except Exception:
        logger.error("[Enrichment] CMDB 批量查询失败 locator=%s", "monitor_id", exc_info=True)
        failed_keys.update(group_keys)


def _canonical_inst_uuid(value) -> str | None:
    """合法 UUIDv4 返回小写规范串。非法值直接跳过，不抛出会打 ERROR 的应用异常。"""
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    if parsed.version != 4:
        return None
    return str(parsed)


@register_provider
class CMDBProvider(EnrichmentProvider):
    provider_type = "cmdb"

    def fetch_batch(self, keys: List, config: Dict) -> Dict | FetchBatchResult:
        authorized_team_ids = list(config.get("_authorized_team_ids") or [])
        if not authorized_team_ids:
            logger.warning("[Enrichment] CMDB 查询缺少组织上下文，拒绝查询")
            return {key: [] for key in keys}
        grouped = _index_lookup_keys(keys)
        by_model_uuids, by_model_names, uuid_keys, monitor_keys, key_meta, skipped_invalid_uuids = grouped
        if skipped_invalid_uuids:
            logger.warning("[Enrichment] CMDB 跳过非 UUIDv4 定位 skipped=%s", skipped_invalid_uuids)

        fetched = {}
        failed_keys = set()
        budget_exhausted_keys = set()
        query_timeout = _bounded_query_timeout(config.get("query_timeout_seconds", 3))
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
        _fetch_model_groups(client, by_model_uuids, "inst_uuids", "", authorized_team_ids, key_meta, fetched, failed_keys, remaining_timeout)
        _fetch_model_groups(client, by_model_names, "inst_names", "(name)", authorized_team_ids, key_meta, fetched, failed_keys, remaining_timeout)
        if uuid_keys:
            _fetch_unscoped_uuids(client, uuid_keys, monitor_keys, key_meta, authorized_team_ids, fetched, failed_keys, remaining_timeout)
        if monitor_keys:
            _fetch_monitor_ids(client, monitor_keys, key_meta, authorized_team_ids, fetched, failed_keys, remaining_timeout)

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


def _bounded_query_timeout(query_timeout) -> int:
    try:
        return max(1, min(int(query_timeout), 10))
    except (TypeError, ValueError):
        return 3
