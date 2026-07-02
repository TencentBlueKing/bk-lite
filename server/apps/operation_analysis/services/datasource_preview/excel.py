from datetime import date, datetime
from typing import Any

import pandas as pd

from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields

MAX_EXCEL_BYTES = 2 * 1024 * 1024
MAX_EXCEL_ROWS = 1000


def _normalize_cell(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        if value.time().isoformat() == "00:00:00":
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalize_dataframe_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    dataframe = dataframe.rename(columns=lambda column: str(column).strip())
    dataframe = dataframe.where(pd.notnull(dataframe), None)
    rows = dataframe.to_dict(orient="records")
    return [{str(key): _normalize_cell(value) for key, value in row.items() if str(key).strip()} for row in rows]


def parse_excel_file(file_obj, sheet_name: str | None = None, max_rows: int = MAX_EXCEL_ROWS) -> list[dict[str, Any]]:
    if not file_obj:
        raise ConnectorError("请上传 Excel 文件", code="excel_file_required", status_code=400)

    file_name = getattr(file_obj, "name", "") or ""
    if not file_name.lower().endswith(".xlsx"):
        raise ConnectorError("仅支持 Excel 文件（.xlsx）", code="excel_file_type_invalid", status_code=400)

    file_size = getattr(file_obj, "size", None)
    if file_size and file_size > MAX_EXCEL_BYTES:
        raise ConnectorError("Excel 文件不能超过 2MB", code="excel_file_too_large", status_code=400)

    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        dataframe = pd.read_excel(file_obj, sheet_name=sheet_name or 0, nrows=max_rows)
    except Exception as exc:
        raise ConnectorError(f"Excel 解析失败: {exc}", code="excel_parse_failed", status_code=400)

    dataframe = dataframe.dropna(how="all")
    if dataframe.empty:
        raise ConnectorError("Excel 没有可预览的数据", code="excel_empty", status_code=400)

    return _normalize_dataframe_rows(dataframe)


class ExcelConnectorExecutor(BaseConnectorExecutor):
    source_type = "excel"

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
    ) -> PreviewResult:
        safe_limit = min(max(int(limit or 100), 1), MAX_EXCEL_ROWS)
        imported_items = query_config.get("imported_items")
        imported_fields = query_config.get("imported_fields")

        if isinstance(imported_items, list):
            items = [item for item in imported_items if isinstance(item, dict)]
            return PreviewResult(
                items=items[:safe_limit],
                count=len(items),
                fields=imported_fields if isinstance(imported_fields, list) else infer_fields(items[:safe_limit]),
            )

        rows = parse_excel_file(
            connection_config.get("file"),
            sheet_name=query_config.get("sheet_name") or None,
            max_rows=MAX_EXCEL_ROWS,
        )
        limited_rows = rows[:safe_limit]
        return PreviewResult(items=limited_rows, count=len(rows), fields=infer_fields(limited_rows))
