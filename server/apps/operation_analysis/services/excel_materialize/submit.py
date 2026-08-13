"""提交 Excel 候选并在事务提交后投递物化任务。"""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.models.excel_materialization_models import ExcelMaterializationSlot
from apps.operation_analysis.services.excel_materialize.materializer import (
    ExcelMaterializer,
    script_hash,
)


def submit_excel_candidate(
    datasource,
    *,
    uploaded_file,
    transform_config: dict | None = None,
    sheet_name: str | None = None,
    schedule: bool = True,
) -> ExcelMaterializationSlot:
    """持久化原文件为新候选并递增 generation。默认 on_commit 投递 Celery。"""
    transform_config = transform_config if isinstance(transform_config, dict) else (datasource.transform_config or {})
    enabled = bool(transform_config.get("enabled"))
    script = transform_config.get("script") if isinstance(transform_config.get("script"), str) else ""
    if enabled and not script.strip():
        raise ValueError("启用转换时 script 不能为空")

    filename = getattr(uploaded_file, "name", "") or "upload.xlsx"
    if not str(filename).lower().endswith(".xlsx"):
        raise ValueError("仅支持 Excel 文件（.xlsx）")

    slot = None
    try:
        with transaction.atomic():
            datasource = type(datasource).objects.select_for_update().get(pk=datasource.pk)
            generation = int(datasource.excel_materialization_generation or 0) + 1
            slot = ExcelMaterializationSlot(
                datasource=datasource,
                role=ExcelMaterializationSlot.ROLE_CANDIDATE,
                generation=generation,
                status=ExcelMaterializationSlot.STATUS_PENDING,
                source_filename=filename,
                transform_enabled=enabled,
                script_snapshot=script if enabled else "",
                script_hash=script_hash(script) if enabled else "",
            )
            slot.source_file.save(filename, uploaded_file, save=False)
            slot.save()

            old_candidate_id = datasource.excel_candidate_slot_id
            datasource.excel_candidate_slot = slot
            datasource.excel_materialization_generation = generation
            query_config = dict(datasource.query_config or {})
            if sheet_name:
                query_config["sheet_name"] = sheet_name
            datasource.query_config = query_config
            datasource.save(
                update_fields=[
                    "excel_candidate_slot",
                    "excel_materialization_generation",
                    "query_config",
                    "updated_at",
                ]
            )
            if old_candidate_id and old_candidate_id != slot.id:
                ExcelMaterializationSlot.objects.filter(pk=old_candidate_id).delete()

            if schedule:
                schedule_materialize_candidate(slot.id)
    except Exception:
        # File storage is outside the DB transaction; compensate a rolled-back upload.
        if slot and slot.source_file and slot.source_file.name:
            try:
                slot.source_file.storage.delete(slot.source_file.name)
            except Exception:  # noqa: BLE001
                logger.error(
                    "[ExcelMaterialize] rollback file cleanup failed name=%s",
                    slot.source_file.name,
                    exc_info=True,
                )
        raise

    return slot


def materialize_candidate_inline(slot_id: int) -> dict[str, Any]:
    """在当前请求内同步物化（上传/重试主路径；Celery 仍用于脚本变更与补扫）。"""
    return ExcelMaterializer().materialize_candidate(int(slot_id))


def discard_unready_excel_datasource(datasource) -> bool:
    """删除从未产生成功结果的 Excel 数据源（界面新建失败清盘）。

    已有成功槽时拒绝删除，避免误伤编辑失败路径。
    """
    datasource.refresh_from_db()
    if datasource.excel_success_slot_id:
        return False
    query_config = datasource.query_config if isinstance(datasource.query_config, dict) else {}
    has_legacy = isinstance(query_config.get("imported_items"), list) and bool(
        query_config.get("imported_items")
    )
    if has_legacy:
        return False

    ds_id = datasource.id
    name = datasource.name
    datasource.delete()
    logger.info(
        "[ExcelMaterialize] discarded unready datasource_id=%s name=%s",
        ds_id,
        name,
    )
    return True


def submit_excel_candidate_from_saved_source(
    datasource,
    *,
    transform_config: dict | None = None,
    schedule: bool = True,
) -> ExcelMaterializationSlot:
    """脚本/开关变更或候选重试：优先候选原文件，避免失败新文件被旧成功文件覆盖。"""
    source_slot = datasource.excel_candidate_slot or datasource.excel_success_slot
    if not source_slot or not source_slot.source_file:
        raise ValueError("缺少可重算的原 Excel 文件，请重新上传")

    with source_slot.source_file.open("rb") as handle:
        content = handle.read()
    uploaded = SimpleUploadedFile(
        name=source_slot.source_filename or "source.xlsx",
        content=content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    sheet_name = None
    query_config = datasource.query_config if isinstance(datasource.query_config, dict) else {}
    if query_config.get("sheet_name"):
        sheet_name = query_config.get("sheet_name")
    return submit_excel_candidate(
        datasource,
        uploaded_file=uploaded,
        transform_config=transform_config,
        sheet_name=sheet_name,
        schedule=schedule,
    )


def schedule_materialize_candidate(slot_id: int) -> None:
    """事务提交后再投递，避免读到未提交候选。"""

    def _enqueue() -> None:
        from apps.core.logger import operation_analysis_logger as logger
        from apps.operation_analysis.tasks.tasks import materialize_excel_candidate_task

        try:
            materialize_excel_candidate_task.delay(slot_id)
        except Exception as exc:  # noqa: BLE001 - broker may be down; slot stays PENDING for rescan
            logger.error(
                "[ExcelMaterialize] enqueue failed slot_id=%s err=%s",
                slot_id,
                type(exc).__name__,
                exc_info=True,
            )

    transaction.on_commit(_enqueue)


def schedule_resubmit_excel_from_saved_source(datasource_id: int) -> None:
    """脚本变更：Celery 只接收 ID，配置与脚本由 Worker 从数据库读取。"""

    def _enqueue() -> None:
        from apps.core.logger import operation_analysis_logger as logger
        from apps.operation_analysis.tasks.tasks import resubmit_excel_from_saved_source_task

        try:
            resubmit_excel_from_saved_source_task.delay(datasource_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[ExcelMaterialize] resubmit enqueue failed datasource_id=%s err=%s",
                datasource_id,
                type(exc).__name__,
                exc_info=True,
            )

    transaction.on_commit(_enqueue)
