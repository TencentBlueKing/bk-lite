"""放弃 Excel 物化身份：解绑槽位、删除原文件/结果，供切类型、导入重置和补偿扫描复用。"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.excel_materialization_models import ExcelMaterializationSlot

EXCEL_QUERY_KEYS = ("imported_items", "imported_fields", "imported_count", "sheet_name")


def abandon_excel_materialization(
    datasource,
    *,
    clear_excel_query_keys: bool = True,
) -> dict[str, Any]:
    """删除数据源上全部 Excel 槽位与对象存储文件，不删除数据源本身。

    幂等：已无槽位时仍把指针和 generation 归零。
    """
    with transaction.atomic():
        locked = type(datasource).objects.select_for_update().get(pk=datasource.pk)
        slot_ids = list(
            ExcelMaterializationSlot.objects.filter(datasource_id=locked.id).values_list("id", flat=True)
        )
        locked.excel_success_slot = None
        locked.excel_candidate_slot = None
        locked.excel_materialization_generation = 0
        update_fields = [
            "excel_success_slot",
            "excel_candidate_slot",
            "excel_materialization_generation",
            "updated_at",
        ]
        if clear_excel_query_keys:
            query_config = dict(locked.query_config or {}) if isinstance(locked.query_config, dict) else {}
            changed = False
            for key in EXCEL_QUERY_KEYS:
                if key in query_config:
                    query_config.pop(key, None)
                    changed = True
            if changed:
                locked.query_config = query_config
                update_fields.append("query_config")
        locked.save(update_fields=update_fields)
        deleted = 0
        if slot_ids:
            deleted, _ = ExcelMaterializationSlot.objects.filter(pk__in=slot_ids).delete()

    logger.info(
        "[ExcelMaterialize] abandoned datasource_id=%s deleted_slots=%s",
        locked.id,
        deleted,
    )
    return {"datasource_id": locked.id, "deleted_slots": deleted}


def sweep_abandoned_excel_materializations(*, limit: int = 50) -> dict[str, Any]:
    """清掉挂在非 Excel 数据源上的残留槽位（切类型漏清或并发窗口补偿）。"""
    ds_ids = list(
        ExcelMaterializationSlot.objects.exclude(
            datasource__source_type=DataSourceAPIModel.SOURCE_TYPE_EXCEL
        )
        .values_list("datasource_id", flat=True)
        .distinct()
        .order_by("datasource_id")[: max(1, int(limit))]
    )
    cleaned = 0
    errors = 0
    for ds_id in ds_ids:
        try:
            datasource = DataSourceAPIModel.objects.get(pk=ds_id)
            abandon_excel_materialization(datasource)
            cleaned += 1
        except DataSourceAPIModel.DoesNotExist:
            continue
        except Exception:  # noqa: BLE001 - 补偿扫描不得因单行失败中断
            errors += 1
            logger.exception(
                "[ExcelMaterialize] sweep abandon failed datasource_id=%s",
                ds_id,
            )
    return {"scanned": len(ds_ids), "cleaned": cleaned, "errors": errors}
