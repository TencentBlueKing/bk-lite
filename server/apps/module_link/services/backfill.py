"""监控接入创建后，把实例 ID 回写到 CMDB CI。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.module_push import CmdbToMonitorPushService
from apps.core.logger import module_link_logger as logger

_BACKFILL_DONE = "event=module_link_cmdb_id_backfill_completed count=%s"
_BACKFILL_ROW_FAILED = "event=module_link_cmdb_id_backfill_failed inst_uuid=%s failed_stage=%s error_type=%s"
_SAFE_ERROR = "module link cmdb id backfill failed"


def _safe_exc_info(exc: BaseException):
    return (type(exc), RuntimeError(_SAFE_ERROR), exc.__traceback__)


def _allowed_org_ids(actor_context: dict[str, Any] | None) -> list[int]:
    ctx = actor_context or {}
    scope = ctx.get("data_scope")
    team_ids = getattr(scope, "data_team_ids", None)
    if team_ids:
        return [int(item) for item in team_ids]
    current = ctx.get("current_team")
    if current in (None, ""):
        return []
    try:
        return [int(current)]
    except (TypeError, ValueError):
        return []


def backfill_monitor_ids(pairs: list[tuple[str, str]], actor_context: dict[str, Any] | None = None) -> int:
    """pairs: (cmdb_id, monitor_id)。失败不影响监控接入结果。"""
    if not pairs:
        return 0
    operator = str((actor_context or {}).get("username") or "")
    allowed = _allowed_org_ids(actor_context)
    done = 0
    for cmdb_id, monitor_id in pairs:
        if not cmdb_id or not monitor_id:
            continue
        try:
            entity = InstanceManage.query_entity_by_uuid(cmdb_id)
        except Exception as exc:
            logger.error(
                _BACKFILL_ROW_FAILED,
                cmdb_id,
                "query_entity",
                type(exc).__name__,
                exc_info=_safe_exc_info(exc),
            )
            continue
        if not isinstance(entity, dict) or not entity:
            continue
        try:
            CmdbToMonitorPushService._backfill_monitor_id(
                entity,
                monitor_id,
                operator=operator,
                allowed_org_ids=allowed,
            )
        except Exception as exc:
            logger.error(
                _BACKFILL_ROW_FAILED,
                cmdb_id,
                "backfill_monitor_id",
                type(exc).__name__,
                exc_info=_safe_exc_info(exc),
            )
            continue
        done += 1
    logger.info(_BACKFILL_DONE, done)
    return done
