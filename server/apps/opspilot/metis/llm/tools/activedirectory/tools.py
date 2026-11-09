"""Active Directory 内置工具（对齐 CData MCP: get_tables / get_columns / run_query）。"""

from __future__ import annotations

import json
from typing import Any, Sequence

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from ldap3 import SUBTREE
from ldap3.core.exceptions import LDAPException

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.activedirectory.connection import build_ad_normalized_from_runnable, get_ad_connection_from_item, safe_unbind
from apps.opspilot.metis.llm.tools.activedirectory.csv_utils import meta_columns_csv, meta_tables_csv, rows_to_csv
from apps.opspilot.metis.llm.tools.activedirectory.schema import AD_TABLES, get_table, list_table_names
from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import AD_LDAP_FETCH_CAP, execute_select
from apps.opspilot.metis.llm.tools.common.credentials import execute_with_credentials

# 低于域控默认 MaxPageSize（1000），避免单页被服务器截断。
AD_LDAP_PAGE_SIZE = 500
_PAGED_RESULTS_OID = "1.2.840.113556.1.4.319"
_AD_LDAP_TRUNCATED = "event=ad_ldap_search_truncated fetched=%s fetch_cap=%s"


def _error(message: str) -> str:
    return f"ERROR: {message}"


class _LdapEntryList(list):
    def __init__(self, entries: Sequence[Any], truncated: bool):
        super().__init__(entries)
        self.truncated = truncated


def _paged_cookie(result: dict[str, Any]) -> bytes | str | None:
    controls = result.get("controls") or {}
    control = controls.get(_PAGED_RESULTS_OID) or {}
    value = control.get("value") or {}
    cookie = value.get("cookie")
    if not cookie:
        return None
    return cookie


def _ldap_searcher(conn, base_dn: str, search_filter: str, attrs: Sequence[str], size_limit: int) -> _LdapEntryList:
    """按 LDAP 分页把一次查询读完，直到没有下一页或达到 size_limit。"""
    if size_limit <= 0:
        return _LdapEntryList([], truncated=False)

    entries: list[Any] = []
    cookie = None
    truncated = False
    while len(entries) < size_limit:
        page_size = min(AD_LDAP_PAGE_SIZE, size_limit - len(entries))
        ok = conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=list(attrs),
            size_limit=0,
            paged_size=page_size,
            paged_cookie=cookie,
        )
        result = conn.result or {}
        result_code = result.get("result")
        if not ok and result_code not in {0, 4}:  # 4 = size limit exceeded
            raise LDAPException(result.get("description") or conn.last_error or "LDAP search failed")
        page = list(conn.entries)
        room = size_limit - len(entries)
        if len(page) > room:
            entries.extend(page[:room])
            truncated = True
            break
        entries.extend(page)
        cookie = _paged_cookie(result)
        if not page or (cookie and len(entries) >= size_limit):
            truncated = bool(cookie)
            break
        if result_code == 4 and not cookie:
            truncated = True
            break
        if not cookie:
            break
    return _LdapEntryList(entries, truncated=truncated)


def _truncation_notice(fetched: int) -> str:
    return (
        f"结果已截断：本次 LDAP 读取在 {fetched} 条停止，目录里还有更多对象。"
        "WHERE 同样只过滤已经读回的记录，不能把上限之外的对象补回来。"
        "LIMIT/OFFSET 只能切分已读取上限内的行，不能读到上限之外的对象。"
    )


@tool()
def activedirectory_get_tables(
    catalog: str | None = None,
    schema: str | None = None,
    instance_name: str | None = None,
    instance_id: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Retrieves a list of objects/entities available as tables in Active Directory.
    Catalog and schema are optional and unused.
    Output is CSV."""
    _ = (catalog, schema)
    try:
        normalized = build_ad_normalized_from_runnable(config, instance_name, instance_id)

        def _executor(item):
            conn = get_ad_connection_from_item(item)
            try:
                rows = [{"Table": t.name, "Description": t.description} for t in AD_TABLES.values()]
                csv_body = meta_tables_csv(rows)
                return csv_body + "\nDefault Catalog: ActiveDirectory\nDefault Schema: AD"
            finally:
                safe_unbind(conn)

        result = execute_with_credentials(normalized, _executor)
        if isinstance(result, dict) and result.get("mode") == "multi":
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as exc:
        return _error(str(exc))


@tool()
def activedirectory_get_columns(
    table: str,
    catalog: str | None = None,
    schema: str | None = None,
    instance_name: str | None = None,
    instance_id: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Retrieves fields/columns for an Active Directory table.
    Output is CSV."""
    _ = (catalog, schema)
    try:
        table_def = get_table(table)
        normalized = build_ad_normalized_from_runnable(config, instance_name, instance_id)

        def _executor(item):
            conn = get_ad_connection_from_item(item)
            try:
                rows = [
                    {
                        "Table": table_def.name,
                        "Column": col.name,
                        "DataType": col.data_type,
                        "Remarks": col.remarks,
                    }
                    for col in table_def.columns
                ]
                return meta_columns_csv(rows)
            finally:
                safe_unbind(conn)

        result = execute_with_credentials(normalized, _executor)
        if isinstance(result, dict) and result.get("mode") == "multi":
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as exc:
        return _error(str(exc))


@tool()
def activedirectory_run_query(
    sql: str,
    instance_name: str | None = None,
    instance_id: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Execute a SQL SELECT statement against Active Directory virtual tables.
    SQL dialect is mostly SQL-92. Identifiers may be quoted with backticks.
    Valid clauses: FROM, INNER JOIN, LEFT JOIN, GROUP BY, ORDER BY, LIMIT/OFFSET.
    One call reads every LDAP page for this query. Do not pass a page number.
    A query without LIMIT returns the full result up to 10000 LDAP entries per table.
    SQL LIMIT/OFFSET only trims returned rows. A truncation notice follows the CSV
    when the directory still has more objects beyond that cap.
    Output is CSV."""
    try:
        normalized = build_ad_normalized_from_runnable(config, instance_name, instance_id)

        def _executor(item):
            conn = get_ad_connection_from_item(item)
            try:
                base_dn = item["config"]["base_dn"]
                truncated_at = 0

                def searcher(search_base, search_filter, attrs, size_limit):
                    nonlocal truncated_at
                    found = _ldap_searcher(conn, search_base, search_filter, attrs, size_limit)
                    if found.truncated and size_limit >= AD_LDAP_FETCH_CAP:
                        truncated_at = max(truncated_at, len(found))
                    return found

                columns, rows = execute_select(sql, base_dn=base_dn, searcher=searcher)
                body = rows_to_csv(columns, rows)
                if truncated_at:
                    logger.warning(_AD_LDAP_TRUNCATED, truncated_at, AD_LDAP_FETCH_CAP)
                    body += "\n" + _truncation_notice(truncated_at)
                return body
            finally:
                safe_unbind(conn)

        result = execute_with_credentials(normalized, _executor)
        if isinstance(result, dict) and result.get("mode") == "multi":
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as exc:
        return _error(str(exc))


# 供文档/测试引用
SUPPORTED_TABLES = list_table_names()
