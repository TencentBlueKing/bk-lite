"""CSV 输出（对齐 CData MCP 的 resultSet → CSV 行为）。"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Mapping, Sequence


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ";".join(_cell(v) for v in value)
    if isinstance(value, bytes):
        try:
            return value.hex()
        except Exception:
            return str(value)
    return str(value)


def rows_to_csv(columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([_cell(row.get(col)) for col in columns])
    return buf.getvalue().rstrip("\n")


def meta_tables_csv(tables: Sequence[Mapping[str, str]]) -> str:
    return rows_to_csv(["Table", "Description"], tables)


def meta_columns_csv(columns: Sequence[Mapping[str, str]]) -> str:
    return rows_to_csv(["Table", "Column", "DataType", "Remarks"], columns)
