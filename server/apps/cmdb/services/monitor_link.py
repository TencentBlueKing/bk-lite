"""CMDB 批量同步监控：逐条走现有无凭据推送并汇总结果。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.constants.monitor_link import CMDB_MONITOR_SYNC_MODEL_IDS
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.module_push import CmdbToMonitorPushService
from apps.core.logger import cmdb_logger as logger

BATCH_PUSH_LIMIT = 100

_ROW_FAILED_TEMPLATE = "event=cmdb_monitor_link_row_failed inst_uuid=%s failed_stage=%s error_type=%s"
_BATCH_DONE_TEMPLATE = "event=cmdb_monitor_link_batch_completed total=%s ok=%s already_linked=%s " "not_found=%s conflict=%s failed=%s"
_SUMMARY_STATUSES = ("ok", "already_linked", "not_found", "conflict", "failed")
_LINK_STATUSES = frozenset({"ok", "not_found", "conflict"})
_SAFE_ROW_ERROR = "cmdb monitor link row failed"


def _safe_exc_info(exc: BaseException):
    return (type(exc), RuntimeError(_SAFE_ROW_ERROR), exc.__traceback__)


class MonitorLinkService:
    """列表勾选批量触发现有无凭据「推送到监控」。调用方负责鉴权。"""

    @classmethod
    def batch_push(cls, inst_uuids: list[str], *, actor_scope: dict[str, Any]) -> dict[str, Any]:
        if len(inst_uuids) > BATCH_PUSH_LIMIT:
            raise ValueError("batch push exceeds limit of 100")

        results: list[dict[str, Any]] = []
        counts = {key: 0 for key in _SUMMARY_STATUSES}

        for inst_uuid in inst_uuids:
            row = cls._push_one(inst_uuid, actor_scope=actor_scope)
            results.append(row)
            status = row["status"]
            if status in counts:
                counts[status] += 1
            logger.debug(
                "event=cmdb_monitor_link_row_status inst_uuid=%s status=%s",
                inst_uuid,
                status,
            )

        summary = {
            "total": len(inst_uuids),
            "ok": counts["ok"],
            "already_linked": counts["already_linked"],
            "not_found": counts["not_found"],
            "conflict": counts["conflict"],
            "failed": counts["failed"],
            "results": results,
        }
        logger.info(
            _BATCH_DONE_TEMPLATE,
            summary["total"],
            summary["ok"],
            summary["already_linked"],
            summary["not_found"],
            summary["conflict"],
            summary["failed"],
        )
        return summary

    @classmethod
    def _push_one(cls, inst_uuid: str, *, actor_scope: dict[str, Any]) -> dict[str, Any]:
        try:
            entity = InstanceManage.query_entity_by_uuid(inst_uuid)
        except Exception as exc:
            cls._log_row_failed(inst_uuid, failed_stage="query_entity", exc=exc)
            return {"inst_uuid": inst_uuid, "status": "failed", "monitor_id": None}

        if not isinstance(entity, dict) or not entity:
            return {"inst_uuid": inst_uuid, "status": "failed", "monitor_id": None}

        if entity.get("model_id") not in CMDB_MONITOR_SYNC_MODEL_IDS:
            return {"inst_uuid": inst_uuid, "status": "skipped_model", "monitor_id": None}

        existing = entity.get("monitor_id")
        if existing not in (None, ""):
            return {
                "inst_uuid": inst_uuid,
                "status": "already_linked",
                "monitor_id": str(existing),
            }

        try:
            pushed = CmdbToMonitorPushService.push_instance(inst_uuid, actor_scope=actor_scope)
        except Exception as exc:
            cls._log_row_failed(inst_uuid, failed_stage="push_instance", exc=exc)
            return {"inst_uuid": inst_uuid, "status": "failed", "monitor_id": None}

        if not isinstance(pushed, dict):
            return {"inst_uuid": inst_uuid, "status": "failed", "monitor_id": None}

        link_status = pushed.get("link_status")
        if link_status not in _LINK_STATUSES:
            return {"inst_uuid": inst_uuid, "status": "failed", "monitor_id": None}

        monitor_id = pushed.get("monitor_id") if link_status == "ok" else None
        if monitor_id not in (None, ""):
            monitor_id = str(monitor_id)
        else:
            monitor_id = None
        return {"inst_uuid": inst_uuid, "status": link_status, "monitor_id": monitor_id}

    @staticmethod
    def _log_row_failed(inst_uuid: str, *, failed_stage: str, exc: BaseException) -> None:
        logger.error(
            _ROW_FAILED_TEMPLATE,
            inst_uuid,
            failed_stage,
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
