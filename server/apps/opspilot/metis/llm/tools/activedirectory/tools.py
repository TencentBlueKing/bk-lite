"""Active Directory 内置工具（对齐 CData MCP: get_tables / get_columns / run_query）。"""

from __future__ import annotations

import json
from typing import Any, Sequence

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from ldap3 import SUBTREE
from ldap3.core.exceptions import LDAPException

from apps.opspilot.metis.llm.tools.activedirectory.connection import build_ad_normalized_from_runnable, get_ad_connection_from_item, safe_unbind
from apps.opspilot.metis.llm.tools.activedirectory.csv_utils import meta_columns_csv, meta_tables_csv, rows_to_csv
from apps.opspilot.metis.llm.tools.activedirectory.schema import AD_TABLES, get_table, list_table_names
from apps.opspilot.metis.llm.tools.activedirectory.sql_engine import execute_select
from apps.opspilot.metis.llm.tools.common.credentials import execute_with_credentials


def _error(message: str) -> str:
    return f"ERROR: {message}"


def _ldap_searcher(conn, base_dn: str, search_filter: str, attrs: Sequence[str], size_limit: int) -> list[Any]:
    ok = conn.search(
        search_base=base_dn,
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=list(attrs),
        size_limit=size_limit,
    )
    if not ok and conn.result.get("result") not in {0, 4}:  # 4 = size limit exceeded
        raise LDAPException(conn.result.get("description") or conn.last_error or "LDAP search failed")
    return list(conn.entries)


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
    Output is CSV."""
    try:
        normalized = build_ad_normalized_from_runnable(config, instance_name, instance_id)

        def _executor(item):
            conn = get_ad_connection_from_item(item)
            try:
                base_dn = item["config"]["base_dn"]

                def searcher(search_base, search_filter, attrs, size_limit):
                    return _ldap_searcher(conn, search_base, search_filter, attrs, size_limit)

                columns, rows = execute_select(sql, base_dn=base_dn, searcher=searcher)
                return rows_to_csv(columns, rows)
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
