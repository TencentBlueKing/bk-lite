from copy import deepcopy
from typing import Any, Dict, Iterable, Tuple

META_KEY = "_meta"
MAX_CONFLICT_VALUES = 20


def _append_unique(values: list, value: Any) -> None:
    if value not in values and len(values) < MAX_CONFLICT_VALUES:
        values.append(deepcopy(value))


def _merge_dicts(primary: Dict[str, Any], candidate: Dict[str, Any], rule_ids: Iterable[int] = ()) -> Tuple[Dict[str, Any], bool]:
    result = deepcopy(primary)
    primary_meta = result.pop(META_KEY, {}) if isinstance(result.get(META_KEY), dict) else {}
    candidate_meta = candidate.get(META_KEY, {}) if isinstance(candidate.get(META_KEY), dict) else {}
    conflicts = deepcopy(primary_meta.get("conflicts") or {})
    had_conflict = primary_meta.get("status") == "conflict" or candidate_meta.get("status") == "conflict"

    for field, value in candidate.items():
        if field == META_KEY:
            continue
        if field not in result:
            result[field] = deepcopy(value)
        elif result[field] != value:
            had_conflict = True
            field_conflicts = conflicts.setdefault(field, [])
            _append_unique(field_conflicts, value)

    if had_conflict:
        merged_rule_ids = []
        for rule_id in [*(primary_meta.get("rule_ids") or []), *(candidate_meta.get("rule_ids") or []), *rule_ids]:
            if rule_id is not None and rule_id not in merged_rule_ids:
                merged_rule_ids.append(rule_id)
        meta = {
            "schema_version": 1,
            "status": "conflict",
        }
        if merged_rule_ids:
            meta["rule_ids"] = merged_rule_ids
        if conflicts:
            meta["conflicts"] = conflicts
        result[META_KEY] = meta
    return result, had_conflict


def normalize_namespace_payload(payload: Any) -> Dict[str, Any]:
    """兼容旧数组结构，并归一化为稳定对象。"""
    if isinstance(payload, dict):
        return deepcopy(payload)
    if not isinstance(payload, list):
        return {}
    merged: Dict[str, Any] = {}
    for item in payload:
        if isinstance(item, dict):
            merged, _ = _merge_dicts(merged, item)
    return merged


def merge_namespace_payload(existing: Any, candidate: Any, *, rule_ids: Iterable[int] = ()) -> Tuple[Dict[str, Any], bool]:
    return _merge_dicts(normalize_namespace_payload(existing), normalize_namespace_payload(candidate), rule_ids)


def normalize_enrichment_document(enrichment: Any) -> Tuple[Dict[str, Any], bool]:
    """把历史 namespace 数组幂等转换为稳定对象。"""
    if not isinstance(enrichment, dict):
        return {}, bool(enrichment)
    normalized = {}
    changed = False
    for namespace, payload in enrichment.items():
        if isinstance(payload, list):
            normalized[namespace] = normalize_namespace_payload(payload)
            changed = True
        else:
            normalized[namespace] = deepcopy(payload)
    return normalized, changed
