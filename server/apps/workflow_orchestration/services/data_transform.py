"""在临时 SQLite 文件里对一份 JSON 执行只读查询，结束即删除文件。"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

MAX_PAYLOAD_BYTES = 5 * 1024 * 1024
MAX_QUERIES = 20
MAX_SQL_CHARS = 50_000
MAX_NAME_CHARS = 64
DEFAULT_TIMEOUT_SECONDS = 30
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 120
_NAME_LEADING = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
_NAME_BODY = _NAME_LEADING | set("0123456789")
_DENIED_FUNCTIONS = {"load_extension", "writefile", "readfile", "edit"}


class DataTransformError(ValueError):
    pass


def _denied_actions() -> frozenset[int]:
    names = (
        "SQLITE_CREATE_INDEX",
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE",
        "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_CREATE_VIEW",
        "SQLITE_DELETE",
        "SQLITE_DROP_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE",
        "SQLITE_DROP_TEMP_TRIGGER",
        "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER",
        "SQLITE_DROP_VIEW",
        "SQLITE_INSERT",
        "SQLITE_PRAGMA",
        "SQLITE_TRANSACTION",
        "SQLITE_UPDATE",
        "SQLITE_ATTACH",
        "SQLITE_DETACH",
        "SQLITE_ALTER_TABLE",
        "SQLITE_REINDEX",
        "SQLITE_ANALYZE",
        "SQLITE_CREATE_VTABLE",
        "SQLITE_DROP_VTABLE",
        "SQLITE_SAVEPOINT",
    )
    return frozenset(getattr(sqlite3, name) for name in names if hasattr(sqlite3, name))


_DENIED_ACTIONS = _denied_actions()


def _valid_name(value: str) -> bool:
    if not value or len(value) > MAX_NAME_CHARS or value[0] not in _NAME_LEADING:
        return False
    return all(char in _NAME_BODY for char in value)


def _statement_kind(sql: str) -> str:
    stripped = sql.lstrip()
    head = stripped[:6].upper()
    if head == "SELECT" or head.startswith("WITH"):
        return head
    raise DataTransformError("查询只能是一条 SELECT")


def _authorizer(action: int, arg1: str | None, arg2: str | None, db_name: str | None, source: str | None) -> int:
    del arg2, source
    if action in _DENIED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == getattr(sqlite3, "SQLITE_FUNCTION", -1) and str(arg1 or "").lower() in _DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    if db_name not in {None, "", "main"}:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _json_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _shape_rows(rows: list[dict[str, Any]]) -> Any:
    if not rows:
        return []
    if len(rows) == 1:
        columns = list(rows[0])
        if len(columns) == 1:
            parsed = _json_cell(rows[0][columns[0]])
            if parsed is not None:
                return parsed
        return dict(rows[0])
    return rows


def _normalize_queries(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > MAX_QUERIES:
        raise DataTransformError("查询需要 1 到 20 条")
    queries: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise DataTransformError("每条查询都要有结果名和 SELECT")
        name = item.get("name")
        sql = item.get("sql")
        if not isinstance(name, str) or not _valid_name(name):
            raise DataTransformError("结果名只能是字母、数字和下划线，且不能以数字开头")
        if name in seen:
            raise DataTransformError("结果名不能重复")
        if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL_CHARS:
            raise DataTransformError("SELECT 不能为空，且不能超过 50000 个字符")
        _statement_kind(sql)
        seen.add(name)
        queries.append({"name": name, "sql": sql})
    return queries


def _timeout_seconds(value: Any) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataTransformError("超时必须是整数秒")
    if not MIN_TIMEOUT_SECONDS <= value <= MAX_TIMEOUT_SECONDS:
        raise DataTransformError("超时必须在 1 到 120 秒之间")
    return value


def _execute_query(connection: sqlite3.Connection, name: str, sql: str) -> Any:
    try:
        cursor = connection.execute(sql)
        columns = [item[0] for item in cursor.description or ()]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    except sqlite3.Error as error:
        message = str(error).lower()
        if "interrupt" in message:
            raise DataTransformError("查询超时") from error
        if "authorized" in message:
            raise DataTransformError("查询只能读取 input 表") from error
        raise DataTransformError(f"查询 {name} 执行失败") from error
    return _shape_rows(rows)


def run_data_transform(data: Any, queries: Any, timeout_seconds: Any = None) -> dict[str, Any]:
    """把 data 写入临时库的 input.payload，按查询名把结果盖到副本上。"""
    if not isinstance(data, dict):
        raise DataTransformError("输入数据必须是 JSON 对象")
    normalized = _normalize_queries(queries)
    timeout = _timeout_seconds(timeout_seconds)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise DataTransformError("输入数据超过 5 MiB")
    directory = Path(tempfile.mkdtemp(prefix="bklite-data-transform-"))
    try:
        connection = sqlite3.connect(directory / "transform.sqlite3")
        try:
            connection.execute("CREATE TABLE input (payload TEXT NOT NULL)")
            connection.execute("INSERT INTO input (payload) VALUES (?)", (payload,))
            connection.execute("PRAGMA query_only = ON")
            connection.set_authorizer(_authorizer)
            deadline = time.monotonic() + timeout

            def progress() -> int:
                return 1 if time.monotonic() >= deadline else 0

            connection.set_progress_handler(progress, 10_000)
            output = json.loads(payload)
            for query in normalized:
                output[query["name"]] = _execute_query(connection, query["name"], query["sql"])
            if not isinstance(output, dict):
                raise DataTransformError("转换结果必须是 JSON 对象")
            return output
        finally:
            connection.close()
    finally:
        shutil.rmtree(directory, ignore_errors=True)
