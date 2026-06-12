import duckdb
import json
from typing import List, Dict, Any
import threading
import pandas as pd

from apps.core.logger import alert_logger as logger


class DuckDBConnection:
    _local = threading.local()

    def __init__(self):
        self._ensure_connection()

    def _ensure_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = duckdb.connect(":memory:")

    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        self._ensure_connection()
        conn = self._local.conn
        result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row)) for row in result]

    def load_events_to_memory(self, events_queryset):
        """
        将 Event QuerySet 加载到 DuckDB 内存表中供聚合查询使用

        每个策略的事件范围不同（基于 window_size），所以需要每次重新加载

        Args:
            events_queryset: Django QuerySet，已过滤的事件集合（必须非空）

        Note:
            调用此方法前应确保 events_queryset 有数据，否则说明上游业务逻辑有误
        """
        self._ensure_connection()
        conn = self._local.conn

        # 1. 从 QuerySet 提取需要的字段
        events_data = list(
            events_queryset.values(
                "event_id",
                "title",
                "description",
                "level",
                "resource_name",
                "resource_id",
                "resource_type",
                "item",
                "external_id",
                "received_at",
                "action",
                "source_id",
                "push_source_id",
                "labels",
                "service",
                "location",
                "event_type",
                "tags",
            )
        )

        # 2. 防御性检查：理论上不应该出现空数据（上游已过滤）
        if not events_data:
            logger.warning("load_events_to_memory 收到空数据，策略调节筛选event为空")
            return

        # 3. 序列化 JSON 字段（DuckDB 要求字符串格式）
        # 性能优化：使用条件表达式，避免重复get()调用
        for event in events_data:
            labels = event.get("labels")
            tags = event.get("tags")
            event["labels"] = json.dumps(labels) if labels else None
            event["tags"] = json.dumps(tags) if tags else None

        # 4. 使用 pandas DataFrame 批量加载数据到 DuckDB
        events_df = pd.DataFrame(events_data)
        # pandas 3.0（或 future.infer_string=True）会把字符串列建成扩展 string dtype
        # （'str' / 'string' / 'string[pyarrow]'），而 duckdb<1.2 不识别它们，register 会抛
        # NotImplementedException("Data type 'str' not recognized")，导致整条聚合失败。
        # 统一把扩展 string 列降级为 object，保证跨 pandas/duckdb 版本兼容；
        # object / datetime / 数值列不受影响（duckdb 本就支持）。
        for col, dtype in events_df.dtypes.items():
            if dtype != object and pd.api.types.is_string_dtype(dtype):
                events_df[col] = events_df[col].astype(object)
        conn.execute("DROP TABLE IF EXISTS events_table")
        conn.register("events_df", events_df)
        conn.execute("CREATE TABLE events_table AS SELECT * FROM events_df")

        return True

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
