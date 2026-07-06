import re
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields

SELECT_RE = re.compile(r"^\s*select\b", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_select_sql(sql: str) -> str:
    cleaned = (sql or "").strip()
    if not cleaned:
        raise ConnectorError("SQL 不能为空", code="db_sql_required", status_code=400)
    if ";" in cleaned:
        raise ConnectorError("SQL 预览不支持多语句", code="db_sql_multi_statement", status_code=400)
    if not SELECT_RE.match(cleaned):
        raise ConnectorError("SQL 预览仅支持 SELECT", code="db_sql_not_select", status_code=400)
    return cleaned


def quote_identifier(identifier: str, source_type: str) -> str:
    if not IDENTIFIER_RE.match(identifier or ""):
        raise ConnectorError("表名格式不合法", code="db_table_invalid", status_code=400)
    if source_type == "postgresql":
        return f'"{identifier}"'
    return f"`{identifier}`"


def build_preview_sql(query_config: dict[str, Any], limit: int, source_type: str = "mysql") -> str:
    safe_limit = min(max(int(limit or 100), 1), 1000)
    if query_config.get("sql"):
        sql = ensure_select_sql(str(query_config["sql"]))
        if LIMIT_RE.search(sql):
            return sql
        return f"{sql} LIMIT {safe_limit}"

    table = query_config.get("table")
    if not table:
        raise ConnectorError("请选择表或填写 SELECT 查询", code="db_query_required", status_code=400)
    return f"SELECT * FROM {quote_identifier(str(table), source_type)} LIMIT {safe_limit}"


def normalize_db_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(dict(row))
        elif hasattr(row, "_mapping"):
            normalized.append(dict(row._mapping))
        else:
            normalized.append(dict(row))
    return normalized


def build_database_url(source_type: str, connection_config: dict[str, Any]) -> str:
    username = connection_config.get("username")
    password = connection_config.get("password")
    host = connection_config.get("host")
    port = connection_config.get("port")
    database = connection_config.get("database")
    if not all([username, password, host, port, database]):
        raise ConnectorError("数据库连接信息不完整", code="db_config_incomplete", status_code=400)

    encoded_username = quote_plus(str(username))
    encoded_password = quote_plus(str(password))
    encoded_database = quote_plus(str(database))

    if source_type == "mysql":
        return f"mysql+pymysql://{encoded_username}:{encoded_password}@{host}:{port}/{encoded_database}?charset=utf8mb4"
    if source_type == "postgresql":
        return f"postgresql+psycopg2://{encoded_username}:{encoded_password}@{host}:{port}/{encoded_database}"
    raise ConnectorError("数据库类型不支持", code="db_type_not_supported", status_code=400)


class DatabaseConnectorExecutor(BaseConnectorExecutor):
    def __init__(self, source_type: str, engine_factory=create_engine):
        self.source_type = source_type
        self.engine_factory = engine_factory

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        database_url = build_database_url(self.source_type, connection_config)
        engine = self.engine_factory(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
    ) -> PreviewResult:
        safe_limit = min(max(int(limit or 100), 1), 1000)
        database_url = build_database_url(self.source_type, connection_config)
        sql = build_preview_sql(query_config, safe_limit, self.source_type)

        try:
            engine = self.engine_factory(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
            with engine.connect() as conn:
                rows = conn.execute(text(sql)).fetchmany(safe_limit)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"数据库预览失败: {exc}", code="db_preview_failed", status_code=502)

        items = normalize_db_rows(rows)
        return PreviewResult(items=items, count=len(items), fields=infer_fields(items))
