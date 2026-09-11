"""CMDB 批量同步监控：逐条走现有无凭据推送并汇总结果。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT, CMDB_MONITOR_SYNC_MODEL_IDS
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import cmdb_link_identity
from apps.cmdb.services.module_push import EVENT_LIFECYCLE, MODULE_NAME, TARGET_MONITOR, CmdbToMonitorPushService, causation_id_for
from apps.core.logger import cmdb_logger as logger
from apps.rpc.monitor import Monitor

BATCH_PUSH_LIMIT = 100
CANDIDATE_LIMIT = 50

_ROW_FAILED_TEMPLATE = "event=cmdb_monitor_link_row_failed inst_uuid=%s failed_stage=%s error_type=%s"
_BATCH_DONE_TEMPLATE = "event=cmdb_monitor_link_batch_completed total=%s ok=%s already_linked=%s " "not_found=%s conflict=%s failed=%s"
_BIND_DONE_TEMPLATE = "event=cmdb_monitor_link_bind_completed inst_uuid=%s status=%s"
_UNBIND_DONE_TEMPLATE = "event=cmdb_monitor_link_unbind_completed inst_uuid=%s status=%s"
_CANDIDATES_DONE_TEMPLATE = "event=cmdb_monitor_link_candidates_completed inst_uuid=%s count=%s"
_BIND_FAILED_TEMPLATE = "event=cmdb_monitor_link_bind_failed inst_uuid=%s failed_stage=%s error_type=%s"
_UNBIND_FAILED_TEMPLATE = "event=cmdb_monitor_link_unbind_failed inst_uuid=%s failed_stage=%s error_type=%s"
_CANDIDATES_FAILED_TEMPLATE = "event=cmdb_monitor_link_candidates_failed inst_uuid=%s failed_stage=%s error_type=%s"
_BIND_BACKFILL_CLEARED_TEMPLATE = "event=cmdb_monitor_link_bind_backfill_cleared inst_uuid=%s monitor_id=%s"
_BIND_OCCUPIED_TEMPLATE = "event=cmdb_monitor_link_bind_occupied inst_uuid=%s occupied_cmdb_id=%s"
_SUMMARY_STATUSES = ("ok", "already_linked", "not_found", "conflict", "failed")
_LINK_STATUSES = frozenset({"ok", "not_found", "conflict"})
_SAFE_ROW_ERROR = "cmdb monitor link row failed"
_SAFE_BIND_ERROR = "cmdb monitor link bind failed"
_SAFE_UNBIND_ERROR = "cmdb monitor link unbind failed"
_SAFE_CANDIDATES_ERROR = "cmdb monitor link candidates failed"


def _safe_exc_info(exc: BaseException, message: str = _SAFE_ROW_ERROR):
    return (type(exc), RuntimeError(message), exc.__traceback__)


def _normalize_link_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


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

    @classmethod
    def list_candidates(cls, inst_uuid: str, query: str, actor_scope: dict[str, Any]) -> dict[str, Any]:
        entity, load_status = cls._load_syncable_entity(inst_uuid)
        if load_status or entity is None:
            return {"status": load_status or "not_found", "items": []}

        object_name = CMDB_MODEL_TO_MONITOR_OBJECT[entity["model_id"]]
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        logger.debug(
            "event=cmdb_monitor_link_candidates_query inst_uuid=%s object_name=%s",
            inst_uuid,
            object_name,
        )
        try:
            rows = Monitor().list_cmdb_bind_candidates(
                object_name=object_name,
                query=query or "",
                allowed_org_ids=allowed_org_ids,
                limit=CANDIDATE_LIMIT,
            )
        except Exception as exc:
            cls._log_op_failed(
                _CANDIDATES_FAILED_TEMPLATE,
                inst_uuid,
                failed_stage="list_candidates",
                exc=exc,
                safe_message=_SAFE_CANDIDATES_ERROR,
            )
            return {"status": "failed", "items": []}

        if not isinstance(rows, list):
            return {"status": "failed", "items": []}

        logger.info(_CANDIDATES_DONE_TEMPLATE, inst_uuid, len(rows))
        return {"status": "ok", "items": rows}

    @classmethod
    def bind(
        cls,
        inst_uuid: str,
        monitor_id: str,
        actor_scope: dict[str, Any],
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        entity, load_status = cls._load_syncable_entity(inst_uuid)
        if load_status or entity is None:
            return {"status": load_status or "not_found", "monitor_id": None, "failed_side": None}

        requested = _normalize_link_id(monitor_id)
        if not requested:
            return {"status": "not_found", "monitor_id": None, "failed_side": None}

        current = _normalize_link_id(entity.get("monitor_id"))
        if current == requested:
            logger.info(_BIND_DONE_TEMPLATE, inst_uuid, "ok")
            return {"status": "ok", "monitor_id": current, "failed_side": None}

        if current and current != requested:
            if not confirm:
                logger.info(_BIND_DONE_TEMPLATE, inst_uuid, "confirm_required")
                return {"status": "confirm_required", "monitor_id": current, "failed_side": None}
            unbind_result = cls.unbind(inst_uuid, actor_scope)
            if unbind_result.get("status") != "ok":
                return {
                    "status": "failed",
                    "monitor_id": current,
                    "failed_side": unbind_result.get("failed_side") or "monitor",
                }
            entity, load_status = cls._load_syncable_entity(inst_uuid)
            if load_status or entity is None:
                return {"status": load_status or "not_found", "monitor_id": None, "failed_side": None}

        object_name = CMDB_MODEL_TO_MONITOR_OBJECT[entity["model_id"]]
        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""

        try:
            bind_result = Monitor().bind_cmdb_id(
                monitor_id=requested,
                cmdb_id=inst_uuid,
                object_name=object_name,
                allowed_org_ids=allowed_org_ids,
            )
        except Exception as exc:
            cls._log_op_failed(
                _BIND_FAILED_TEMPLATE,
                inst_uuid,
                failed_stage="bind_cmdb_id",
                exc=exc,
                safe_message=_SAFE_BIND_ERROR,
            )
            return {"status": "failed", "monitor_id": None, "failed_side": "monitor"}

        if not isinstance(bind_result, dict):
            return {"status": "failed", "monitor_id": None, "failed_side": "monitor"}

        bind_status = bind_result.get("status")
        if bind_status == "occupied":
            occupied_cmdb_id = _normalize_link_id(bind_result.get("occupied_cmdb_id"))
            occupied_name, occupied_uuid = cls._lookup_occupier(occupied_cmdb_id)
            logger.warning(_BIND_OCCUPIED_TEMPLATE, inst_uuid, occupied_cmdb_id or "")
            return {
                "status": "occupied",
                "monitor_id": None,
                "occupied_cmdb_id": occupied_cmdb_id,
                "occupied_inst_name": occupied_name,
                "occupied_inst_uuid": occupied_uuid,
                "failed_side": None,
            }
        if bind_status in ("not_found", "type_mismatch"):
            logger.info(_BIND_DONE_TEMPLATE, inst_uuid, bind_status)
            return {"status": bind_status, "monitor_id": None, "failed_side": None}
        if bind_status != "ok":
            return {"status": "failed", "monitor_id": None, "failed_side": "monitor"}

        bound_monitor_id = _normalize_link_id(bind_result.get("monitor_id")) or requested
        updated = CmdbToMonitorPushService._backfill_monitor_id(
            entity,
            bound_monitor_id,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
        )
        if str((updated or {}).get("monitor_id") or "").strip() != bound_monitor_id:
            logger.warning(_BIND_BACKFILL_CLEARED_TEMPLATE, inst_uuid, bound_monitor_id)
            try:
                Monitor().clear_cmdb_id(
                    monitor_id=bound_monitor_id,
                    expected_cmdb_id=inst_uuid,
                    allowed_org_ids=allowed_org_ids,
                )
            except Exception as exc:
                cls._log_op_failed(
                    _BIND_FAILED_TEMPLATE,
                    inst_uuid,
                    failed_stage="clear_cmdb_id",
                    exc=exc,
                    safe_message=_SAFE_BIND_ERROR,
                )
            return {"status": "failed", "monitor_id": None, "failed_side": "cmdb"}

        logger.info(_BIND_DONE_TEMPLATE, inst_uuid, "ok")
        return {"status": "ok", "monitor_id": bound_monitor_id, "failed_side": None}

    @classmethod
    def unbind(cls, inst_uuid: str, actor_scope: dict[str, Any]) -> dict[str, Any]:
        try:
            entity = InstanceManage.query_entity_by_uuid(inst_uuid)
        except Exception as exc:
            cls._log_op_failed(
                _UNBIND_FAILED_TEMPLATE,
                inst_uuid,
                failed_stage="query_entity",
                exc=exc,
                safe_message=_SAFE_UNBIND_ERROR,
            )
            return {"status": "failed", "failed_side": "cmdb"}

        if not isinstance(entity, dict) or not entity:
            return {"status": "not_found", "failed_side": None}

        monitor_id = _normalize_link_id(entity.get("monitor_id"))
        if not monitor_id:
            logger.info(_UNBIND_DONE_TEMPLATE, inst_uuid, "ok")
            return {"status": "ok", "failed_side": None}

        cmdb_id, aliases = cmdb_link_identity(entity)
        if not cmdb_id:
            cmdb_id = inst_uuid

        allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
        operator = actor_scope.get("operator") or ""
        raw = CmdbToMonitorPushService._instance_to_raw(entity)
        raw["action"] = "unlink"
        link_ids: dict[str, Any] = {"cmdb_id": cmdb_id, "monitor_id": monitor_id}
        legacy_aliases = [item for item in aliases if item != cmdb_id]
        if legacy_aliases:
            link_ids["cmdb_id_aliases"] = legacy_aliases

        logger.debug("event=cmdb_monitor_link_unbind_monitor inst_uuid=%s", inst_uuid)
        try:
            Monitor().ingest_from_source(
                source_module=MODULE_NAME,
                source_id=cmdb_id,
                event_type=EVENT_LIFECYCLE,
                occurred_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                raw=raw,
                link_ids=link_ids,
                allowed_org_ids=allowed_org_ids,
                operator=operator,
                causation_id=causation_id_for(MODULE_NAME, cmdb_id, TARGET_MONITOR),
            )
        except Exception as exc:
            cls._log_op_failed(
                _UNBIND_FAILED_TEMPLATE,
                inst_uuid,
                failed_stage="ingest_unlink",
                exc=exc,
                safe_message=_SAFE_UNBIND_ERROR,
            )
            return {"status": "failed", "failed_side": "monitor"}

        try:
            InstanceManage.instance_update_by_uuid(
                user_groups=[],
                roles=[],
                inst_uuid=inst_uuid,
                update_attr={"monitor_id": ""},
                operator=operator,
                allowed_org_ids=allowed_org_ids,
                skip_permission_check=True,
            )
        except Exception as exc:
            cls._log_op_failed(
                _UNBIND_FAILED_TEMPLATE,
                inst_uuid,
                failed_stage="clear_monitor_id",
                exc=exc,
                safe_message=_SAFE_UNBIND_ERROR,
            )
            return {"status": "failed", "failed_side": "cmdb"}

        logger.info(_UNBIND_DONE_TEMPLATE, inst_uuid, "ok")
        return {"status": "ok", "failed_side": None}

    @classmethod
    def _load_syncable_entity(cls, inst_uuid: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            entity = InstanceManage.query_entity_by_uuid(inst_uuid)
        except Exception as exc:
            cls._log_op_failed(
                _BIND_FAILED_TEMPLATE,
                inst_uuid,
                failed_stage="query_entity",
                exc=exc,
                safe_message=_SAFE_BIND_ERROR,
            )
            return None, "failed"
        if not isinstance(entity, dict) or not entity:
            return None, "not_found"
        if entity.get("model_id") not in CMDB_MONITOR_SYNC_MODEL_IDS:
            return None, "skipped_model"
        return entity, None

    @staticmethod
    def _lookup_occupier(occupied_cmdb_id: str | None) -> tuple[str | None, str | None]:
        if not occupied_cmdb_id:
            return None, None
        try:
            occupier = InstanceManage.query_entity_by_uuid(occupied_cmdb_id)
        except Exception:
            return None, occupied_cmdb_id
        if not isinstance(occupier, dict) or not occupier:
            return None, occupied_cmdb_id
        name = occupier.get("inst_name")
        uuid = occupier.get("inst_uuid") or occupied_cmdb_id
        occupied_name = str(name) if name not in (None, "") else None
        occupied_uuid = str(uuid) if uuid not in (None, "") else occupied_cmdb_id
        return occupied_name, occupied_uuid

    @staticmethod
    def _log_op_failed(
        template: str,
        inst_uuid: str,
        *,
        failed_stage: str,
        exc: BaseException,
        safe_message: str,
    ) -> None:
        logger.error(
            template,
            inst_uuid,
            failed_stage,
            type(exc).__name__,
            exc_info=_safe_exc_info(exc, safe_message),
        )
