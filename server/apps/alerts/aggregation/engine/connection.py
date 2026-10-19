import json
import threading
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import duckdb

from apps.alerts.aggregation.batching import AGGREGATION_BATCH_SIZE
from apps.alerts.serializers.strategy import ALLOWED_DIMENSIONS
from apps.core.logger import alert_logger as logger

FIXED_COLUMNS = (
    "pk",
    "event_id",
    "received_at",
    "action",
    "level",
    "title",
    "description",
    "resource_name",
    "external_id",
)

COLUMN_TYPES = {
    "pk": "BIGINT",
    "received_at": "TIMESTAMP",
}


class DuckDBConnection:
    _local = threading.local()

    def __init__(self):
        self.loaded_batches = 0
        self._ensure_connection()

    def _ensure_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = duckdb.connect(":memory:")

    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        self._ensure_connection()
        conn = self._local.conn
        result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [{column: self._aware_utc(value) for column, value in zip(columns, row)} for row in result]

    def load_events_to_memory(self, events_queryset, dimensions: Optional[Sequence[str]] = None):
        """按主键分批把事件投影装入本轮 DuckDB 表。空输入返回 None。"""
        self._ensure_connection()
        self.loaded_batches = 0
        columns = self._columns_for(dimensions)
        inserted = False
        for batch in self._iter_row_batches(events_queryset, columns):
            if not batch:
                continue
            if not inserted:
                self._create_table(columns)
            self._insert_rows(columns, batch)
            self.loaded_batches += 1
            inserted = True
        if not inserted:
            logger.warning("load_events_to_memory 收到空数据，策略调节筛选event为空")
            return None
        return True

    def iter_member_pk_batches(self, grouping_expression: str, group_value, batch_size: int = AGGREGATION_BATCH_SIZE):
        """按与摘要相同的分组表达式分页读取成员主键。"""
        self._ensure_connection()
        conn = self._local.conn
        last_pk = None
        while True:
            sql = f"SELECT pk FROM events_table WHERE ({grouping_expression}) IS NOT DISTINCT FROM ?"
            params: List[Any] = [group_value]
            if last_pk is not None:
                sql += " AND pk > ?"
                params.append(last_pk)
            sql += " ORDER BY pk LIMIT ?"
            params.append(batch_size)
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                return
            yield [row[0] for row in rows]
            last_pk = rows[-1][0]

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def _columns_for(self, dimensions: Optional[Sequence[str]]) -> List[str]:
        columns = list(FIXED_COLUMNS)
        selected = list(dimensions) if dimensions is not None else sorted(ALLOWED_DIMENSIONS)
        needs_enrichment = any(str(name).startswith("enrichment.") for name in selected)
        if needs_enrichment or dimensions is None:
            columns.append("enrichment")
        for name in selected:
            if name in columns or str(name).startswith("enrichment."):
                continue
            columns.append(name)
        return columns

    def _create_table(self, columns: Sequence[str]) -> None:
        definitions = ", ".join(f"{name} {COLUMN_TYPES.get(name, 'VARCHAR')}" for name in columns)
        conn = self._local.conn
        conn.execute("DROP TABLE IF EXISTS events_table")
        conn.execute(f"CREATE TABLE events_table ({definitions})")

    def _insert_rows(self, columns: Sequence[str], rows: Sequence[dict]) -> None:
        placeholders = ", ".join("?" for _ in columns)
        names = ", ".join(columns)
        payload = [tuple(self._cell(row, column) for column in columns) for row in rows]
        self._local.conn.executemany(
            f"INSERT INTO events_table ({names}) VALUES ({placeholders})",
            payload,
        )

    @staticmethod
    def _cell(row: dict, column: str):
        value = row.get(column)
        if column == "enrichment" and value is not None and not isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if column == "received_at" and isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(dt_timezone.utc).replace(tzinfo=None)
        return value

    @staticmethod
    def _aware_utc(value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=dt_timezone.utc)
        return value

    def _iter_row_batches(self, events_queryset, columns: Sequence[str]) -> Iterable[List[dict]]:
        if hasattr(events_queryset, "order_by") and hasattr(events_queryset, "filter"):
            last_pk = None
            while True:
                page = events_queryset
                if last_pk is not None:
                    page = page.filter(pk__gt=last_pk)
                batch = list(page.order_by("pk").values(*columns)[:AGGREGATION_BATCH_SIZE])
                if not batch:
                    return
                yield batch
                last_pk = batch[-1]["pk"]
            return
        rows = list(events_queryset.values(*columns))
        for offset in range(0, len(rows), AGGREGATION_BATCH_SIZE):
            yield rows[offset : offset + AGGREGATION_BATCH_SIZE]
