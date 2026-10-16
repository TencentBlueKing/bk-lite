"""只读 PG 查询、短 TTL Redis，以及给 HTTP Client Span 补路由模板。"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import psycopg2
import redis

CACHE_PREFIX = "apm-demo:"
CACHE_TTL_SECONDS = 30


def resolve_demo_sku(raw: object) -> str | None:
    """出站 URL 只用 demo 常量 sku，避免把请求原文拼进地址。"""

    if raw == "book":
        return "book"
    if raw == "slow":
        return "slow"
    if raw == "fail":
        return "fail"
    if raw == "stockout":
        return "stockout"
    if raw == "crash":
        return "crash"
    return None


def _pg_connect():
    host = os.environ.get("PGHOST") or os.environ.get("DB_HOST")
    if not host:
        return None
    return psycopg2.connect(
        host=host,
        port=os.environ.get("PGPORT") or os.environ.get("DB_PORT") or "5432",
        user=os.environ.get("PGUSER") or os.environ.get("DB_USER"),
        password=os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
        dbname=os.environ.get("PGDATABASE") or os.environ.get("DB_NAME"),
        connect_timeout=3,
        options="-c default_transaction_read_only=on",
    )


def pg_fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    conn = _pg_connect()
    if conn is None:
        return []
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            return list(cur.fetchall())
    finally:
        conn.close()


def _redis():
    url = os.environ.get("REDIS_URL") or os.environ.get("REDIS_CACHE_URL")
    if not url:
        return None
    return redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)


def cache_get(key: str) -> str | None:
    client = _redis()
    if client is None:
        return None
    value = client.get(CACHE_PREFIX + key)
    return str(value) if value is not None else None


def cache_set(key: str, value: str, ttl: int = CACHE_TTL_SECONDS) -> None:
    client = _redis()
    if client is None:
        return
    client.setex(CACHE_PREFIX + key, ttl, value)


_HTTP_ROUTE_TEMPLATES = (
    (re.compile(r"^/products/[^/]+$"), "/products/{sku}"),
    (re.compile(r"^/stock/[^/]+$"), "/stock/{sku}"),
    (re.compile(r"^/reserve/[^/]+$"), "/reserve/{sku}"),
    (re.compile(r"^/orders/?$"), "/orders"),
    (re.compile(r"^/charges/?$"), "/charges"),
)


def http_route_template(path: str) -> str:
    """把带 sku 的路径收成模板，避免 HTTP 出站按字面量膨胀。"""

    for pattern, template in _HTTP_ROUTE_TEMPLATES:
        if pattern.match(path):
            return template
    return path or "/"


def _http_request_hook(span, request_obj) -> None:
    if span is None or not span.is_recording():
        return
    parsed = urlparse(getattr(request_obj, "url", "") or "")
    method = str(getattr(request_obj, "method", "") or "GET").upper()
    route = http_route_template(parsed.path or "/")
    span.set_attribute("http.method", method)
    span.set_attribute("http.request.method", method)
    span.set_attribute("http.route", route)
    span.update_name(f"{method} {route}")


def _instrument_http_client() -> None:
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
    except Exception:
        return
    instrumentor = RequestsInstrumentor()
    try:
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        instrumentor.instrument(request_hook=_http_request_hook)
    except Exception:
        return


_instrument_http_client()
