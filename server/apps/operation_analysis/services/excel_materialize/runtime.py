"""Excel 运行时取数：成功槽优先，存量 imported_items 兼容。"""

from __future__ import annotations

from typing import Any

from apps.operation_analysis.models.excel_materialization_models import ExcelMaterializationSlot
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.schema import infer_fields
from apps.operation_analysis.services.excel_materialize.materializer import (
    load_slot_result_rows,
    resolve_excel_runtime_status,
)


def load_excel_runtime(datasource, *, limit: int = 1000) -> dict[str, Any]:
    """返回与 preview/get_source_data 兼容的 items/count/fields/warnings。"""
    safe_limit = min(max(int(limit or 100), 1), 1000)
    status = resolve_excel_runtime_status(datasource)
    warnings: list[str] = []

    success = getattr(datasource, "excel_success_slot", None)
    candidate = getattr(datasource, "excel_candidate_slot", None)
    query_config = datasource.query_config if isinstance(getattr(datasource, "query_config", None), dict) else {}
    imported_items = query_config.get("imported_items")
    imported_fields = query_config.get("imported_fields")
    has_legacy = isinstance(imported_items, list) and bool(imported_items)

    if status == "needs_upload":
        raise ConnectorError(
            "还没有可用的 Excel 文件，请先上传",
            code="excel_needs_upload",
            status_code=400,
        )
    if status == "failed":
        summary = (candidate.error_summary if candidate else "") or "Excel 处理失败"
        raise ConnectorError(summary, code=getattr(candidate, "error_code", None) or "excel_materialize_failed", status_code=400)
    if status == "processing" and not success and not has_legacy:
        raise ConnectorError("Excel 正在处理中，请稍后重试", code="excel_processing", status_code=409)

    rows: list[dict[str, Any]] = []
    fields: list[dict[str, str]] | None = None

    if (
        success
        and getattr(success, "status", None) == ExcelMaterializationSlot.STATUS_SUCCEEDED
    ):
        rows = load_slot_result_rows(success)
        fields = success.field_schema if isinstance(success.field_schema, list) else None
        if status == "processing":
            warnings.append("Excel 正在更新，当前使用上次成功结果")
        elif status == "update_failed_using_previous":
            summary = (candidate.error_summary if candidate else "") or "更新失败"
            warnings.append(f"Excel 更新失败，仍使用上次成功结果：{summary}")
    elif has_legacy:
        rows = [item for item in imported_items if isinstance(item, dict)]
        fields = imported_fields if isinstance(imported_fields, list) else None
        if status == "processing":
            warnings.append("Excel 正在更新，当前使用上次成功结果")
        elif status == "update_failed_using_previous":
            summary = (candidate.error_summary if candidate else "") or "更新失败"
            warnings.append(f"Excel 更新失败，仍使用上次成功结果：{summary}")
    else:
        raise ConnectorError("Excel 暂无可运行结果", code="excel_not_ready", status_code=400)

    if not isinstance(fields, list) or not fields:
        fields = infer_fields(rows[:safe_limit])

    return {
        "items": rows[:safe_limit],
        "count": len(rows),
        "fields": fields,
        "warnings": warnings,
        "status": status,
    }
