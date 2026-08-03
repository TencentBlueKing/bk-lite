from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace

from apps.apm.services.contracts import SpanDetail, TraceDetail

MAX_TRACE_SPANS = 1000
MAX_SPAN_ATTRIBUTES = 100
MAX_ATTRIBUTE_VALUE_LENGTH = 2048
MAX_TRACE_ATTRIBUTE_BYTES = 256 * 1024

_SENSITIVE_PARTS = {
    "authorization",
    "cookie",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "privatekey",
    "private_key",
}
_BODY_KEYS = {
    "body",
    "http.request.body",
    "http.response.body",
    "request.body",
    "response.body",
}
_RAW_URL_KEYS = {
    "url.full",
    "url.path",
    "url.query",
    "url.fragment",
    "http.url",
    "http.target",
}
_INTERNAL_KEYS = {
    "bk.apm.original_span_name",
    "bk.ingest_source.id",
}


def _is_hidden_key(key: str) -> bool:
    normalized = key.casefold().strip()
    if normalized in _BODY_KEYS or normalized in _RAW_URL_KEYS or normalized in _INTERNAL_KEYS:
        return True
    compact = normalized.replace("-", "_")
    parts = set(re.split(r"[._:/]", compact))
    return bool(parts & _SENSITIVE_PARTS) or compact in _SENSITIVE_PARTS


def _sanitize_nested(value: object, *, depth: int = 0) -> tuple[object, bool]:
    if depth >= 5:
        return str(value), True
    if isinstance(value, Mapping):
        items = [(str(key), item) for key, item in value.items() if not _is_hidden_key(str(key))]
        truncated = len(items) > MAX_SPAN_ATTRIBUTES
        result: dict[str, object] = {}
        for key, item in items[:MAX_SPAN_ATTRIBUTES]:
            result[key], item_truncated = _sanitize_nested(item, depth=depth + 1)
            truncated = truncated or item_truncated
        return result, truncated
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        truncated = len(items) > MAX_SPAN_ATTRIBUTES
        result: list[object] = []
        for item in items[:MAX_SPAN_ATTRIBUTES]:
            bounded, item_truncated = _sanitize_nested(item, depth=depth + 1)
            result.append(bounded)
            truncated = truncated or item_truncated
        return result, truncated
    return value, False


def _bounded_value(value: object) -> tuple[object, bool, int]:
    value, nested_truncated = _sanitize_nested(value)
    if isinstance(value, str):
        truncated = len(value) > MAX_ATTRIBUTE_VALUE_LENGTH
        bounded = value[:MAX_ATTRIBUTE_VALUE_LENGTH]
        return bounded, truncated or nested_truncated, len(bounded.encode("utf-8"))
    if value is None or isinstance(value, (bool, int, float)):
        encoded = json.dumps(value, ensure_ascii=False)
        return value, nested_truncated, len(encoded.encode("utf-8"))

    encoded = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    truncated = len(encoded) > MAX_ATTRIBUTE_VALUE_LENGTH
    bounded = encoded[:MAX_ATTRIBUTE_VALUE_LENGTH] if truncated else value
    size = len((bounded if isinstance(bounded, str) else encoded).encode("utf-8"))
    return bounded, truncated or nested_truncated, size


def sanitize_trace_detail(trace: TraceDetail) -> TraceDetail:
    remaining_bytes = MAX_TRACE_ATTRIBUTE_BYTES
    trace_truncated = trace.truncated or len(trace.spans) > MAX_TRACE_SPANS
    spans: list[SpanDetail] = []

    for span in trace.spans[:MAX_TRACE_SPANS]:
        attributes: dict[str, object] = {}
        visible_items = [(str(key), value) for key, value in span.attributes.items() if not _is_hidden_key(str(key))]
        if len(visible_items) > MAX_SPAN_ATTRIBUTES:
            trace_truncated = True
        for key, value in visible_items[:MAX_SPAN_ATTRIBUTES]:
            bounded, value_truncated, value_size = _bounded_value(value)
            entry_size = len(key.encode("utf-8")) + value_size
            if entry_size > remaining_bytes:
                trace_truncated = True
                break
            attributes[key] = bounded
            remaining_bytes -= entry_size
            trace_truncated = trace_truncated or value_truncated
        spans.append(replace(span, attributes=attributes))

    return replace(trace, spans=tuple(spans), truncated=trace_truncated)
