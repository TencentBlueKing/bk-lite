"""Full Flow conversation list: keyword on src/dst, then paginate.

The professional dashboard used to query a TopN capability. This service unwraps
topk/bottomk/limitk, keeps the full 5-tuple aggregation, filters by source or
destination address, and returns one page. Top protocol ranking stays unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, AuthorizedMetricQueryService
from apps.monitor.services.metric_series import fold_instant_rows, unwrap_limiting_query
from apps.monitor.services.metrics import Metrics
from apps.monitor.utils.pagination import parse_page_params

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
MAX_KEYWORD_LENGTH = 256
CONVERSATION_DIMENSIONS = ["src", "src_port", "dst", "dst_port", "protocol"]


def normalize_conversation_keyword(value) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_KEYWORD_LENGTH:
        raise AuthorizedMetricQueryError("keyword 过长", code="keyword_invalid")
    return text


def parse_conversation_page(payload: dict[str, Any]) -> tuple[int, int]:
    page, page_size = parse_page_params(payload, default_page=1, default_page_size=DEFAULT_PAGE_SIZE)
    return page, min(page_size, MAX_PAGE_SIZE)


def is_conversation_query(query: str) -> bool:
    text = str(query or "")
    has_src = "src_ip" in text or re.search(r"\bsrc\b", text) is not None
    has_dst = "dst_ip" in text or re.search(r"\bdst\b", text) is not None
    has_ports = "src_port" in text and "dst_port" in text
    has_protocol = "protocol" in text
    return has_src and has_dst and has_ports and has_protocol


def conversation_matches_keyword(row: dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    needle = keyword.casefold()
    src = str(row.get("src") or "").casefold()
    dst = str(row.get("dst") or "").casefold()
    return needle in src or needle in dst


def parse_conversation_rows(vm_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    series = ((vm_result or {}).get("data") or {}).get("result") or []
    if not isinstance(series, list):
        return []
    rows = fold_instant_rows(series, CONVERSATION_DIMENSIONS, limit=max(len(series), 1))
    return [row for row in rows if row.get("src") or row.get("dst")]


def serialize_conversation_page(
    rows: list[dict[str, Any]],
    *,
    keyword: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    filtered = [row for row in rows if conversation_matches_keyword(row, keyword)]
    count = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]
    items = []
    for offset, row in enumerate(page_rows):
        items.append(
            {
                "src_ip": row.get("src") or "--",
                "dst_ip": row.get("dst") or "--",
                "src_port": row.get("src_port") or "--",
                "dst_port": row.get("dst_port") or "--",
                "protocol": row.get("protocol") or "--",
                "bytes_rate": float(row.get("value") or 0),
                "rank": start + offset + 1,
            }
        )
    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def query_flow_conversation_page(
    *,
    authorized_service: AuthorizedMetricQueryService,
    payload: dict[str, Any],
) -> dict[str, Any]:
    keyword = normalize_conversation_keyword(payload.get("keyword") or payload.get("ip"))
    page, page_size = parse_conversation_page(payload)
    prepared = authorized_service.prepare(payload)
    query = unwrap_limiting_query(prepared.query)
    if not is_conversation_query(query):
        raise AuthorizedMetricQueryError("查询能力不支持会话列表", code="capability_not_conversation")

    vm_result = Metrics.get_metrics(query, time=prepared.end / 1000.0)
    if not isinstance(vm_result, dict) or vm_result.get("status") != "success":
        raise AuthorizedMetricQueryError("指标查询失败", code="metric_query_failed")
    return serialize_conversation_page(
        parse_conversation_rows(vm_result),
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
