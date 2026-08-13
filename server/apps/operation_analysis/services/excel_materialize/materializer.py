"""ExcelMaterializer: materialize a candidate slot and atomically promote on success."""

from __future__ import annotations

import gzip
import hashlib
import json
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.models.excel_materialization_models import ExcelMaterializationSlot
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.schema import infer_fields
from apps.operation_analysis.services.excel_materialize.row_probe import read_excel_rows_for_materialize
from apps.operation_analysis.services.transform.errors import TransformError
from apps.operation_analysis.services.transform.executor import get_transform_executor


class ExcelMaterializer:
    """Only public capability: materialize a candidate slot and try to switch."""

    def materialize_candidate(self, slot_id: int) -> dict[str, Any]:
        try:
            slot = ExcelMaterializationSlot.objects.select_related("datasource").get(pk=slot_id)
        except ExcelMaterializationSlot.DoesNotExist:
            return {"ok": False, "code": "slot_missing", "slot_id": slot_id}

        if slot.role != ExcelMaterializationSlot.ROLE_CANDIDATE:
            return {"ok": False, "code": "slot_not_candidate", "slot_id": slot_id}

        datasource = slot.datasource
        if datasource.excel_candidate_slot_id != slot.id:
            # Stale candidate; do not overwrite newer state.
            return {"ok": False, "code": "slot_stale", "slot_id": slot_id}

        claimed = ExcelMaterializationSlot.objects.filter(
            pk=slot.id,
            role=ExcelMaterializationSlot.ROLE_CANDIDATE,
            status=ExcelMaterializationSlot.STATUS_PENDING,
        ).update(
            status=ExcelMaterializationSlot.STATUS_PROCESSING,
            error_code="",
            error_summary="",
        )
        if not claimed:
            slot.refresh_from_db()
            code = (
                "slot_in_progress"
                if slot.status == ExcelMaterializationSlot.STATUS_PROCESSING
                else "slot_not_pending"
            )
            return {"ok": False, "code": code, "slot_id": slot_id}
        slot.refresh_from_db()

        try:
            if not slot.source_file:
                raise ConnectorError("候选缺少原文件", code="excel_file_required", status_code=400)
            query_config = datasource.query_config if isinstance(datasource.query_config, dict) else {}
            sheet_name = query_config.get("sheet_name") or None
            with slot.source_file.open("rb") as file_obj:
                # Ensure name for type check.
                if not getattr(file_obj, "name", None):
                    file_obj.name = slot.source_filename or "source.xlsx"
                rows = read_excel_rows_for_materialize(file_obj, sheet_name=sheet_name)

            if slot.transform_enabled:
                script = slot.script_snapshot or ""
                rows = get_transform_executor().execute(
                    rows,
                    {},
                    script,
                    org_id=(datasource.groups or ["default"])[0] if datasource.groups else "default",
                )

            fields = infer_fields(rows)
            self._write_result_file(slot, rows)
            # FileField.save(..., save=False) 只更新内存；切换前必须落库，否则
            # select_for_update 重载会丢掉 result_file 路径。
            slot.save(update_fields=["result_file", "updated_at"])
            self._promote_success(slot, rows=rows, fields=fields)
            logger.info(
                "[ExcelMaterializer] succeeded slot_id=%s datasource_id=%s rows=%s generation=%s",
                slot.id,
                datasource.id,
                len(rows),
                slot.generation,
            )
            return {"ok": True, "slot_id": slot.id, "row_count": len(rows)}
        except (ConnectorError, TransformError) as exc:
            code = getattr(exc, "code", "excel_materialize_failed")
            message = getattr(exc, "message", str(exc))
            self._mark_failed(slot, code=code, summary=message)
            logger.info(
                "[ExcelMaterializer] failed slot_id=%s datasource_id=%s code=%s",
                slot.id,
                datasource.id,
                code,
            )
            return {"ok": False, "code": code, "slot_id": slot.id, "message": message}
        except Exception as exc:  # noqa: BLE001
            summary = safe_materialize_error_summary(exc)
            self._mark_failed(slot, code="excel_materialize_internal_error", summary=summary)
            logger.error(
                "[ExcelMaterializer] internal error slot_id=%s: %s",
                slot.id,
                exc,
                exc_info=True,
            )
            return {
                "ok": False,
                "code": "excel_materialize_internal_error",
                "slot_id": slot.id,
                "message": summary,
            }

    def _write_result_file(self, slot: ExcelMaterializationSlot, rows: list[dict[str, Any]]) -> None:
        payload = gzip.compress(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            compresslevel=6,
        )
        filename = f"excel_result_{slot.datasource_id}_{slot.generation}.json.gz"
        slot.result_file.save(filename, ContentFile(payload), save=False)

    def _promote_success(
        self,
        slot: ExcelMaterializationSlot,
        *,
        rows: list[dict[str, Any]],
        fields: list[dict[str, str]],
    ) -> None:
        with transaction.atomic():
            locked = (
                ExcelMaterializationSlot.objects.select_for_update()
                .select_related("datasource")
                .get(pk=slot.id)
            )
            datasource = locked.datasource
            if datasource.excel_candidate_slot_id != locked.id:
                # Newer candidate won; keep this result file but do not switch pointers.
                locked.status = ExcelMaterializationSlot.STATUS_SUCCEEDED
                locked.row_count = len(rows)
                locked.field_schema = fields
                locked.error_code = ""
                locked.error_summary = ""
                locked.save(
                    update_fields=[
                        "status",
                        "row_count",
                        "field_schema",
                        "error_code",
                        "error_summary",
                        "result_file",
                        "updated_at",
                    ]
                )
                return

            previous_success_id = datasource.excel_success_slot_id
            locked.role = ExcelMaterializationSlot.ROLE_SUCCESS
            locked.status = ExcelMaterializationSlot.STATUS_SUCCEEDED
            locked.row_count = len(rows)
            locked.field_schema = fields
            locked.error_code = ""
            locked.error_summary = ""
            locked.save(
                update_fields=[
                    "role",
                    "status",
                    "row_count",
                    "field_schema",
                    "error_code",
                    "error_summary",
                    "result_file",
                    "updated_at",
                ]
            )

            datasource.excel_success_slot = locked
            datasource.excel_candidate_slot = None
            if fields:
                datasource.field_schema = fields
            # 新物化结果不写入 imported_items；切换成功后清理存量行集。
            query_config = dict(datasource.query_config or {})
            query_config.pop("imported_items", None)
            query_config.pop("imported_fields", None)
            datasource.query_config = query_config
            datasource.save(
                update_fields=[
                    "excel_success_slot",
                    "excel_candidate_slot",
                    "field_schema",
                    "query_config",
                    "updated_at",
                ]
            )

            if previous_success_id and previous_success_id != locked.id:
                ExcelMaterializationSlot.objects.filter(pk=previous_success_id).delete()

    def _mark_failed(self, slot: ExcelMaterializationSlot, *, code: str, summary: str) -> None:
        ExcelMaterializationSlot.objects.filter(
            pk=slot.id,
            role=ExcelMaterializationSlot.ROLE_CANDIDATE,
            status=ExcelMaterializationSlot.STATUS_PROCESSING,
        ).update(
            status=ExcelMaterializationSlot.STATUS_FAILED,
            error_code=code[:64],
            error_summary=(summary or "")[:512],
        )


def script_hash(script: str) -> str:
    return hashlib.sha256((script or "").encode("utf-8")).hexdigest()


def safe_materialize_error_summary(exc: BaseException) -> str:
    """面向用户的短摘要：可行动、不泄露凭据与堆栈。"""
    text = str(exc or "").lower()
    if any(token in text for token in ("accessdenied", "access denied", "invalidaccesskey", "signaturedoesnotmatch")):
        return "文件保存失败：存储服务无权限，请检查配置后重试"
    if "nosuchbucket" in text or ("bucket" in text and "not exist" in text):
        return "文件保存失败：存储空间未就绪，请联系管理员初始化后重试"
    if any(
        token in text
        for token in (
            "connection refused",
            "nodename nor servname",
            "name or service not known",
            "timed out",
            "timeout",
        )
    ):
        return "无法连接文件存储或转换服务，请确认相关服务已启动后重试"
    if any(token in text for token in ("transform_runner", "runner_unavailable", "unauthorized")):
        return "Python 转换服务不可用，请确认转换服务已启动且认证配置正确"
    if any(token in text for token in ("celery", "kombu", "broker")):
        return "后台处理服务异常，请确认任务服务已启动后重试"
    return "Excel 处理失败，请重新选择文件并保存；若持续失败请查看服务端日志"


def load_slot_result_rows(slot: ExcelMaterializationSlot) -> list[dict[str, Any]]:
    if not slot.result_file:
        return []
    with slot.result_file.open("rb") as handle:
        raw = handle.read()
    try:
        text = gzip.decompress(raw).decode("utf-8")
    except OSError:
        text = raw.decode("utf-8")
    data = json.loads(text)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _slot_has_source_file(slot: ExcelMaterializationSlot | None) -> bool:
    if not slot:
        return False
    name = getattr(slot.source_file, "name", None) or ""
    return bool(str(name).strip())


def excel_has_saved_source(datasource) -> bool:
    """Whether a recompute/retry can use an already stored original .xlsx."""
    return _slot_has_source_file(datasource.excel_candidate_slot) or _slot_has_source_file(
        datasource.excel_success_slot
    )


def resolve_excel_runtime_status(datasource) -> str:
    """Derive Spec runtime status without requiring frontend."""
    success = datasource.excel_success_slot
    candidate = datasource.excel_candidate_slot
    query_config = datasource.query_config if isinstance(datasource.query_config, dict) else {}
    has_legacy = isinstance(query_config.get("imported_items"), list) and bool(query_config.get("imported_items"))

    if candidate and candidate.status in {
        ExcelMaterializationSlot.STATUS_PENDING,
        ExcelMaterializationSlot.STATUS_PROCESSING,
    }:
        return "processing" if success or has_legacy else "processing"
    if candidate and candidate.status == ExcelMaterializationSlot.STATUS_FAILED:
        return "update_failed_using_previous" if (success or has_legacy) else "failed"
    if success and success.status == ExcelMaterializationSlot.STATUS_SUCCEEDED:
        return "ready"
    if has_legacy:
        return "ready"
    return "needs_upload"


def excel_can_retry(datasource) -> bool:
    """Retry only when a saved original exists and the latest candidate failed."""
    if not excel_has_saved_source(datasource):
        return False
    status = resolve_excel_runtime_status(datasource)
    return status in {"failed", "update_failed_using_previous"}


def build_excel_materialization_payload(datasource) -> dict[str, Any]:
    """API-facing Excel runtime state (status + retry capability)."""
    candidate = datasource.excel_candidate_slot
    success = datasource.excel_success_slot
    return {
        "status": resolve_excel_runtime_status(datasource),
        "generation": datasource.excel_materialization_generation,
        "success_slot_id": datasource.excel_success_slot_id,
        "candidate_slot_id": datasource.excel_candidate_slot_id,
        "candidate_status": candidate.status if candidate else None,
        "error_code": candidate.error_code if candidate else "",
        "error_summary": candidate.error_summary if candidate else "",
        "success_updated_at": success.updated_at.isoformat() if success and success.updated_at else None,
        "has_saved_source": excel_has_saved_source(datasource),
        "can_retry": excel_can_retry(datasource),
    }
