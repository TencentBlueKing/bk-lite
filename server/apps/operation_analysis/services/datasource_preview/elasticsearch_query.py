"""只读 Query DSL 和结果展平。时间过滤写在已保存的查询体里。"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.user_messages import oa_message

MAX_ROWS = 1000
MAX_FROM = 1000
MAX_QUERY_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

_INDEX_RE = re.compile(r"^[A-Za-z0-9.*][A-Za-z0-9_.*-]{0,255}$")

_ROOT_KEYS = frozenset(
    {
        "query",
        "aggs",
        "aggregations",
        "size",
        "sort",
        "_source",
        "from",
        "track_total_hits",
        "timeout",
        "terminate_after",
        "stored_fields",
        "docvalue_fields",
        "fields",
        "post_filter",
        "min_score",
        "collapse",
    }
)
_ALWAYS_FORBIDDEN = frozenset(
    {
        "script_fields",
        "script_score",
        "runtime_mappings",
        "painless",
        "pit",
        "scroll",
        "scroll_id",
        "search_after",
        "rescore",
        "highlight",
        "suggest",
    }
)
_SCRIPT_LANGUAGES = frozenset({"painless", "expression"})
_MAX_WRAPPER_DEPTH = 8
_BUCKET_SKIP = frozenset(
    {
        "key",
        "key_as_string",
        "doc_count",
        "doc_count_error_upper_bound",
        "sum_other_doc_count",
    }
)
_STATS_KEYS = frozenset({"count", "min", "max", "avg", "sum"})


def _fail(message_key: str, default: str, *, code: str, **params) -> ConnectorError:
    return ConnectorError(oa_message(message_key, default, **params), code=code, status_code=400)


def validate_index_name(index: str) -> str:
    text = str(index or "").strip()
    if not text or text in {"*", "_all"} or text.startswith("_") or ".." in text or not _INDEX_RE.match(text):
        raise _fail("messages.es_index_invalid", "Elasticsearch 索引名无效", code="elasticsearch_index_invalid")
    return text


def _script_forbidden() -> ConnectorError:
    return _fail("messages.es_query_readonly", "Elasticsearch 查询只允许只读 Query DSL", code="elasticsearch_query_forbidden")


def _is_script_bearing_key(lowered: str) -> bool:
    """script、script_*、*_script 和 scripted_metric 都会执行 Painless。"""
    return lowered == "script" or lowered == "scripted_metric" or lowered.startswith("script_") or lowered.endswith("_script")


def _decode_wrapper_body(encoded: str) -> Any:
    compact = "".join(str(encoded).split())
    if not compact:
        raise _script_forbidden()
    try:
        raw = base64.b64decode(compact + ("=" * ((-len(compact)) % 4)), validate=True)
    except ValueError:
        raise _script_forbidden() from None
    if len(raw) > MAX_QUERY_BYTES:
        raise _fail("messages.es_query_too_large", "Elasticsearch 查询体过大", code="elasticsearch_query_too_large")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _script_forbidden() from None
    if not isinstance(payload, (dict, list)):
        raise _script_forbidden()
    return payload


def _reject_wrapper_query(value: Any, *, wrapper_depth: int) -> None:
    """拆开 wrapper.query 的 base64，按同一套只读规则递归检查。"""
    if not isinstance(value, dict):
        _reject_scripts(value, wrapper_depth=wrapper_depth)
        return
    encoded = None
    for key, item in value.items():
        lowered = str(key).lower()
        if lowered in _ALWAYS_FORBIDDEN or _is_script_bearing_key(lowered):
            raise _script_forbidden()
        if lowered == "query" and isinstance(item, str):
            encoded = item
            continue
        _reject_scripts(item, wrapper_depth=wrapper_depth)
    if encoded is None:
        return
    if wrapper_depth >= _MAX_WRAPPER_DEPTH:
        raise _script_forbidden()
    _reject_scripts(_decode_wrapper_body(encoded), wrapper_depth=wrapper_depth + 1)


def _reject_scripts(node: Any, *, wrapper_depth: int = 0) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).lower()
            if lowered in _ALWAYS_FORBIDDEN or _is_script_bearing_key(lowered):
                raise _script_forbidden()
            if lowered == "lang" and str(value).lower() in _SCRIPT_LANGUAGES:
                raise _script_forbidden()
            if lowered == "wrapper":
                _reject_wrapper_query(value, wrapper_depth=wrapper_depth)
                continue
            _reject_scripts(value, wrapper_depth=wrapper_depth)
        return
    if isinstance(node, list):
        for item in node:
            _reject_scripts(item, wrapper_depth=wrapper_depth)


def validate_query_body(body: dict) -> dict:
    if not isinstance(body, dict):
        raise _fail("messages.es_query_object", "Elasticsearch 查询体必须是 JSON 对象", code="elasticsearch_query_invalid")
    unexpected = sorted(set(body.keys()) - _ROOT_KEYS)
    if unexpected:
        raise _fail(
            "messages.es_query_keys",
            "Elasticsearch 查询包含不允许的字段: {names}",
            code="elasticsearch_query_forbidden",
            names=", ".join(unexpected),
        )
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_QUERY_BYTES:
        raise _fail("messages.es_query_too_large", "Elasticsearch 查询体过大", code="elasticsearch_query_too_large")
    _reject_scripts(body)

    prepared = dict(body)
    for key in ("query", "aggs", "aggregations", "post_filter", "collapse"):
        if key in prepared and not isinstance(prepared[key], dict):
            raise _fail("messages.es_query_object", "Elasticsearch 查询体必须是 JSON 对象", code="elasticsearch_query_invalid")
    has_aggs = "aggs" in prepared or "aggregations" in prepared
    if has_aggs:
        prepared["size"] = 0
        prepared.pop("from", None)
    else:
        size = prepared.get("size", 100)
        if isinstance(size, bool) or not isinstance(size, int):
            raise _fail("messages.es_query_size", "Elasticsearch size 必须是整数", code="elasticsearch_query_invalid")
        prepared["size"] = min(max(size, 0), MAX_ROWS)
        if "from" in prepared:
            start = prepared["from"]
            if isinstance(start, bool) or not isinstance(start, int) or start < 0 or start > MAX_FROM:
                raise _fail("messages.es_query_from", "Elasticsearch from 超出允许范围", code="elasticsearch_query_invalid")
    if "timeout" in prepared:
        prepared["timeout"] = _bounded_timeout(prepared["timeout"])
    return prepared


def _bounded_timeout(value: Any) -> str:
    if not isinstance(value, str):
        raise _fail("messages.es_query_timeout", "Elasticsearch timeout 必须是字符串", code="elasticsearch_query_invalid")
    match = re.fullmatch(r"(\d+)(nanos|micros|ms|s|m|h|d)?", value.strip())
    if not match:
        raise _fail("messages.es_query_timeout", "Elasticsearch timeout 必须是字符串", code="elasticsearch_query_invalid")
    amount = int(match.group(1))
    unit = match.group(2) or "ms"
    seconds = {
        "nanos": amount / 1_000_000_000,
        "micros": amount / 1_000_000,
        "ms": amount / 1000,
        "s": amount,
        "m": amount * 60,
        "h": amount * 3600,
        "d": amount * 86400,
    }[unit]
    if seconds <= 0 or seconds > 60:
        raise _fail("messages.es_query_timeout", "Elasticsearch timeout 必须是字符串", code="elasticsearch_query_invalid")
    return value.strip()


def _load_query_body(query_config: dict) -> dict:
    if not isinstance(query_config, dict):
        raise _fail("messages.es_query_object", "Elasticsearch 查询体必须是 JSON 对象", code="elasticsearch_query_invalid")
    unexpected = sorted(set(query_config.keys()) - {"body"})
    if unexpected:
        raise _fail(
            "messages.es_query_config_keys",
            "Elasticsearch 取数配置包含不允许的字段: {names}",
            code="elasticsearch_query_forbidden",
            names=", ".join(unexpected),
        )
    body = query_config.get("body") if "body" in query_config else {}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError as exc:
            raise _fail("messages.es_query_object", "Elasticsearch 查询体必须是 JSON 对象", code="elasticsearch_query_invalid") from exc
    if not isinstance(body, dict):
        raise _fail("messages.es_query_object", "Elasticsearch 查询体必须是 JSON 对象", code="elasticsearch_query_invalid")
    return body


def validate_stored_query_config(query_config: dict) -> dict:
    """保存/导入时检查查询形状。查询体原样执行，不替换参数，也不注入画布时间。"""
    validate_query_body(_load_query_body(query_config or {}))
    return query_config or {}


def prepare_search_body(query_config: dict) -> dict:
    """返回已校验的查询体。不替换声明参数，也不注入画布时间。"""
    return validate_query_body(_load_query_body(query_config))


def _is_bucket_agg(value: Any) -> bool:
    return isinstance(value, dict) and "buckets" in value


def _is_metric(value: Any) -> bool:
    return isinstance(value, dict) and "value" in value and "buckets" not in value


def _is_stats(value: Any) -> bool:
    return isinstance(value, dict) and "buckets" not in value and "value" not in value and bool(_STATS_KEYS.intersection(value))


def _key_text(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _copy_metrics(target: dict, metrics: list, stats: list) -> None:
    for name, body in metrics:
        target[name] = body.get("value")
    for name, body in stats:
        for stat_key in _STATS_KEYS:
            if stat_key in body:
                target[f"{name}_{stat_key}"] = body.get(stat_key)
    if len(metrics) == 1:
        target["value"] = metrics[0][1].get("value")
        target.setdefault("name", metrics[0][0])
    elif "doc_count" in target and "value" not in target:
        target["value"] = target["doc_count"]
    elif "count" in target and "value" not in target:
        target["value"] = target["count"]
    if "doc_count" in target and "count" not in target:
        target["count"] = target["doc_count"]


def _bucket_list(body: dict) -> list[dict]:
    buckets = body.get("buckets")
    if isinstance(buckets, list):
        return [item for item in buckets if isinstance(item, dict)]
    if isinstance(buckets, dict):
        normalized = []
        for key, bucket in buckets.items():
            if isinstance(bucket, dict):
                item = dict(bucket)
                item.setdefault("key", key)
                normalized.append(item)
        return normalized
    return []


def _flatten_agg_node(node: dict, current: dict, rows: list[dict], max_rows: int) -> bool:
    """返回是否因为行数上限提前停止。"""
    if len(rows) >= max_rows:
        return True
    bucket_items = [(key, value) for key, value in node.items() if _is_bucket_agg(value)]
    metric_items = [(key, value) for key, value in node.items() if _is_metric(value)]
    stats_items = [(key, value) for key, value in node.items() if _is_stats(value)]
    if not bucket_items:
        row = dict(current)
        _copy_metrics(row, metric_items, stats_items)
        if row:
            rows.append(row)
        return len(rows) >= max_rows

    for agg_name, body in bucket_items:
        for bucket in _bucket_list(body):
            if len(rows) >= max_rows:
                return True
            key = _key_text(bucket.get("key_as_string", bucket.get("key")))
            next_row = dict(current)
            next_row[agg_name] = key
            next_row["name"] = key
            if "doc_count" in bucket:
                next_row["doc_count"] = bucket.get("doc_count")
                next_row["count"] = bucket.get("doc_count")
            sub = {sub_name: sub_body for sub_name, sub_body in bucket.items() if sub_name not in _BUCKET_SKIP and isinstance(sub_body, dict)}
            if any(_is_bucket_agg(value) for value in sub.values()):
                if _flatten_agg_node(sub, next_row, rows, max_rows):
                    return True
                continue
            metrics = [(name, value) for name, value in sub.items() if _is_metric(value)]
            stats = [(name, value) for name, value in sub.items() if _is_stats(value)]
            _copy_metrics(next_row, metrics, stats)
            rows.append(next_row)
            if len(rows) >= max_rows:
                return True
    return False


def flatten_search_response(payload: dict, *, max_rows: int) -> tuple[list[dict], bool]:
    """有聚合时把 bucket 展成行，否则使用 hits._source。返回 (rows, truncated)。"""
    limit = max(int(max_rows or 1), 1)
    aggregations = payload.get("aggregations") if isinstance(payload, dict) else None
    if aggregations is None and isinstance(payload, dict):
        aggregations = payload.get("aggs")
    if isinstance(aggregations, dict) and aggregations:
        rows: list[dict] = []
        stopped = _flatten_agg_node(aggregations, {}, rows, limit)
        return rows, stopped

    hits = payload.get("hits") if isinstance(payload, dict) else None
    hit_list = hits.get("hits") if isinstance(hits, dict) else None
    if not isinstance(hit_list, list):
        return [], False
    rows = []
    for hit in hit_list:
        if len(rows) >= limit:
            return rows, True
        source = hit.get("_source") if isinstance(hit, dict) else None
        rows.append(dict(source) if isinstance(source, dict) else {"_source": source})
    return rows, len(hit_list) > len(rows)
