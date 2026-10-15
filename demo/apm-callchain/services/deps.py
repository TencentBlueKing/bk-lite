"""只读 PG 查询和短 TTL Redis，用来在 APM 里打出数据库语句 / 出站调用 Span。"""

from __future__ import annotations

import os
from typing import Any

import psycopg2
import redis

CACHE_PREFIX = "apm-demo:"
CACHE_TTL_SECONDS = 30


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
