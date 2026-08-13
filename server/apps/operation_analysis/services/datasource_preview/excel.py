from datetime import date, datetime
from typing import Any

import pandas as pd

from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields
from apps.operation_analysis.services.datasource_preview.rest_api import maybe_apply_transform

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


def _preview_with_optional_transform(
    items: list[dict[str, Any]],
    *,
    limit: int,
    transform_config: dict[str, Any] | None,
    org_id: str | int | None,
    imported_fields: list | None = None,
) -> PreviewResult:
    safe_limit = min(max(int(limit or 100), 1), MAX_EXCEL_ROWS)
    raw_limited = items[:safe_limit]
    raw_fields = (
        imported_fields
        if isinstance(imported_fields, list) and imported_fields
        else infer_fields(raw_limited)
    )
    enabled = bool(isinstance(transform_config, dict) and transform_config.get("enabled"))
    if not enabled:
        return PreviewResult(items=raw_limited, count=len(items), fields=raw_fields)

    try:
        transformed = maybe_apply_transform(items, transform_config, org_id=org_id)
    except ConnectorError as exc:
        return PreviewResult(
            items=raw_limited,
            count=len(items),
            fields=raw_fields,
            raw_items=raw_limited,
            raw_count=len(items),
            raw_fields=raw_fields,
            transform_error={"code": exc.code, "message": exc.message},
        )

    limited_rows = transformed[:safe_limit]
    return PreviewResult(
        items=limited_rows,
        count=len(transformed),
        fields=infer_fields(limited_rows),
        raw_items=raw_limited,
        raw_count=len(items),
        raw_fields=raw_fields,
    )


class ExcelConnectorExecutor(BaseConnectorExecutor):
    source_type = "excel"

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
        *,
        transform_config: dict[str, Any] | None = None,
        org_id: str | int | None = None,
        **kwargs,
    ) -> PreviewResult:
        imported_items = query_config.get("imported_items")
        imported_fields = query_config.get("imported_fields")
        effective_transform = transform_config if isinstance(transform_config, dict) else {}
        enabled = bool(effective_transform.get("enabled"))

        if isinstance(imported_items, list):
            items = [item for item in imported_items if isinstance(item, dict)]
        elif enabled and connection_config.get("file"):
            # Align with materialize: full row set (+ 10001 probe) then transform, then sample.
            from apps.operation_analysis.services.excel_materialize.row_probe import (
                read_excel_rows_for_materialize,
            )

            file_obj = connection_config.get("file")
            file_size = getattr(file_obj, "size", None)
            if file_size and file_size > MAX_EXCEL_BYTES:
                raise ConnectorError("Excel 文件不能超过 2MB", code="excel_file_too_large", status_code=400)
            try:
                items = read_excel_rows_for_materialize(
                    file_obj,
                    sheet_name=query_config.get("sheet_name") or None,
                )
            except ConnectorError:
                raise
            except Exception as exc:
                raise ConnectorError(f"Excel 解析失败: {exc}", code="excel_parse_failed", status_code=400) from exc
        else:
            items = parse_excel_file(
                connection_config.get("file"),
                sheet_name=query_config.get("sheet_name") or None,
                max_rows=MAX_EXCEL_ROWS,
            )

        return _preview_with_optional_transform(
            items,
            limit=limit,
            transform_config=effective_transform,
            org_id=org_id,
            imported_fields=imported_fields if isinstance(imported_fields, list) else None,
        )


def preview_excel_from_saved_source(datasource, *, transform_config: dict | None, limit: int = 100, org_id=None) -> PreviewResult:
    """已保存 Excel：用原文件 + 请求内脚本做预览，避免静默返回旧成功槽结果。"""
    from apps.operation_analysis.services.excel_materialize.row_probe import (
        read_excel_rows_for_materialize,
    )

    source_slot = datasource.excel_candidate_slot or datasource.excel_success_slot
    if not source_slot or not source_slot.source_file:
        # Fall back to legacy imported_items path via runtime only when no source file.
        from apps.operation_analysis.services.excel_materialize import load_excel_runtime

        payload = load_excel_runtime(datasource, limit=limit)
        return PreviewResult(
            items=payload.get("items", []),
            count=payload.get("count", 0),
            fields=payload.get("fields", []),
            warnings=payload.get("warnings"),
        )

    query_config = datasource.query_config if isinstance(datasource.query_config, dict) else {}
    sheet_name = query_config.get("sheet_name") or None
    with source_slot.source_file.open("rb") as handle:
        if not getattr(handle, "name", None):
            handle.name = source_slot.source_filename or "source.xlsx"
        items = read_excel_rows_for_materialize(handle, sheet_name=sheet_name)

    return _preview_with_optional_transform(
        items,
        limit=limit,
        transform_config=transform_config if isinstance(transform_config, dict) else {},
        org_id=org_id if org_id is not None else ((datasource.groups or ["default"])[0] if datasource.groups else "default"),
    )
