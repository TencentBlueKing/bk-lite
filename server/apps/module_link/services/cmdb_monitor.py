"""CMDB → 监控同步任务：第一段认领、草稿、指定对象、回收。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.module_push import CmdbToMonitorPushService, build_cmdb_push_actor_scope
from apps.cmdb.services.monitor_link import CANDIDATE_LIMIT, MonitorLinkService
from apps.core.logger import module_link_logger as logger
from apps.core.utils.team_utils import collect_group_tree_ids, get_current_team
from apps.module_link.constants import (
    BATCH_LIMIT,
    ITEM_ALREADY_LINKED,
    ITEM_CONFLICT,
    ITEM_FAILED,
    ITEM_NEEDS_OBJECT,
    ITEM_NOT_FOUND,
    ITEM_OK,
    ITEM_SKIPPED,
    RECYCLE_BATCH_SIZE,
    RETAIN_DELTA,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_WAITING_ACCESS,
    builtin_object_name,
    is_builtin_mapped_model,
    is_platform_tree_model,
)
from apps.module_link.models import ModuleLinkModelMap, MonitorAccessDraft, MonitorLinkTask, MonitorLinkTaskItem
from apps.rpc.monitor import Monitor

_CREATE_DONE = (
    "event=module_link_cmdb_monitor_task_completed task_id=%s total=%s ok=%s "
    "already_linked=%s not_found=%s conflict=%s failed=%s skipped_model=%s needs_object=%s"
)
_CREATE_FAILED = "event=module_link_cmdb_monitor_task_failed failed_stage=%s error_type=%s total=%s"
_ASSIGN_DONE = "event=module_link_assign_object_completed task_id=%s object_name=%s count=%s"
_RECYCLE_DONE = "event=module_link_recycle_completed deleted=%s"
_ROW_FAILED = "event=module_link_cmdb_monitor_row_failed inst_uuid=%s failed_stage=%s error_type=%s"
_SAFE_ROW_ERROR = "module link cmdb monitor row failed"
_SAFE_CREATE_ERROR = "module link cmdb monitor task failed"
_COUNT_KEYS = (
    ITEM_OK,
    ITEM_ALREADY_LINKED,
    ITEM_NOT_FOUND,
    ITEM_CONFLICT,
    ITEM_FAILED,
    ITEM_SKIPPED,
    ITEM_NEEDS_OBJECT,
)


def _safe_exc_info(exc: BaseException, message: str = _SAFE_ROW_ERROR):
    return (type(exc), RuntimeError(message), exc.__traceback__)


def _as_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _first_port(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value) if value > 0 else ""
    if isinstance(value, list):
        for item in value:
            text = _first_port(item)
            if text:
                return text
        return ""
    text = _as_text(value)
    if not text:
        return ""
    try:
        number = int(text)
    except ValueError:
        return text
    return str(number) if number > 0 else ""


def _first_ip(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = _first_ip(item)
            if text:
                return text
        return ""
    text = _as_text(value)
    if not text:
        return ""
    for part in text.replace(";", ",").split(","):
        ip = part.strip()
        if ip:
            return ip
    return ""


def _as_org_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _snapshot(entity: dict[str, Any] | None, inst_uuid: str) -> dict[str, Any]:
    row = entity if isinstance(entity, dict) else {}
    ip = _first_ip(row.get("ip")) or _first_ip(row.get("ip_addr"))
    port = _first_port(row.get("port")) or _first_port(row.get("listen_port"))
    return {
        "inst_uuid": _as_text(row.get("inst_uuid")) or inst_uuid,
        "model_id": _as_text(row.get("model_id")),
        "inst_name": _as_text(row.get("inst_name")),
        "ip": ip,
        "port": port,
        "organization": _as_org_list(row.get("organization")),
        "cloud_region_id": _as_int_or_none(row.get("cloud_region_id")),
    }


def _as_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _draft_row(item: MonitorLinkTaskItem) -> dict[str, Any]:
    group_ids = item.organization if isinstance(item.organization, list) else []
    return {
        "inst_uuid": item.inst_uuid,
        "cmdb_id": item.inst_uuid,
        "inst_name": item.inst_name,
        "instance_name": item.inst_name,
        "ip": item.ip,
        "port": item.port,
        "organization": group_ids,
        "group_ids": group_ids,
        "cloud_region_id": item.cloud_region_id,
        "model_id": item.model_id,
    }


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in _COUNT_KEYS}


def _is_uuid_authorized(request, inst_uuid: str) -> bool:
    from apps.cmdb.views.instance import InstanceViewSet

    return InstanceViewSet()._is_batch_push_uuid_authorized(request, inst_uuid)


def _mapped_object_name(model_id: str, team: int | None) -> str | None:
    builtin = builtin_object_name(model_id)
    if builtin:
        return builtin
    if team is None:
        return None
    mapping = ModuleLinkModelMap.objects.filter(team=team, model_id=model_id).first()
    if mapping is None:
        return None
    return mapping.object_name


def _claim_by_unique_name(entity: dict[str, Any], object_name: str, actor_scope: dict[str, Any]) -> tuple[str, str]:
    inst_name = _as_text(entity.get("inst_name"))
    if not inst_name or not object_name:
        return ITEM_NOT_FOUND, ""
    allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
    try:
        rows = Monitor().list_cmdb_bind_candidates(
            object_name=object_name,
            query=inst_name,
            allowed_org_ids=allowed_org_ids,
            limit=CANDIDATE_LIMIT,
        )
    except Exception as exc:
        logger.error(
            _ROW_FAILED,
            _as_text(entity.get("inst_uuid")),
            "list_candidates",
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
        return ITEM_FAILED, ""
    if not isinstance(rows, list):
        return ITEM_FAILED, ""
    unbound = [row for row in rows if isinstance(row, dict) and _as_text(row.get("name")) == inst_name and not _as_text(row.get("cmdb_id"))]
    if len(unbound) != 1:
        return ITEM_NOT_FOUND, ""
    monitor_id = _as_text(unbound[0].get("id"))
    if not monitor_id:
        return ITEM_NOT_FOUND, ""
    try:
        bind_result = Monitor().bind_cmdb_id(
            monitor_id=monitor_id,
            cmdb_id=_as_text(entity.get("inst_uuid")),
            object_name=object_name,
            allowed_org_ids=allowed_org_ids,
        )
    except Exception as exc:
        logger.error(
            _ROW_FAILED,
            _as_text(entity.get("inst_uuid")),
            "bind_cmdb_id",
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
        return ITEM_FAILED, ""
    if not isinstance(bind_result, dict):
        return ITEM_FAILED, ""
    if bind_result.get("status") == "occupied":
        return ITEM_CONFLICT, ""
    if bind_result.get("status") != "ok":
        return ITEM_NOT_FOUND, ""
    bound_id = _as_text(bind_result.get("monitor_id")) or monitor_id
    updated = CmdbToMonitorPushService._backfill_monitor_id(
        entity,
        bound_id,
        operator=actor_scope.get("operator") or "",
        allowed_org_ids=allowed_org_ids,
    )
    if _as_text((updated or {}).get("monitor_id")) != bound_id:
        return ITEM_FAILED, ""
    return ITEM_OK, bound_id


def _item_kwargs(task, snapshot: dict[str, Any], status: str, object_name: str, monitor_id: str) -> dict[str, Any]:
    return {
        "task": task,
        "inst_uuid": snapshot["inst_uuid"],
        "model_id": snapshot["model_id"],
        "object_name": object_name,
        "inst_name": snapshot["inst_name"],
        "ip": snapshot["ip"],
        "port": snapshot.get("port") or "",
        "organization": snapshot["organization"],
        "cloud_region_id": snapshot["cloud_region_id"],
        "status": status,
        "monitor_id": monitor_id or "",
    }


def _sync_drafts(task: MonitorLinkTask) -> None:
    task.drafts.all().delete()
    grouped: dict[str, list[MonitorLinkTaskItem]] = {}
    for item in task.items.filter(status=ITEM_NOT_FOUND).exclude(object_name=""):
        grouped.setdefault(item.object_name, []).append(item)
    drafts = [
        MonitorAccessDraft(
            task=task,
            object_name=object_name,
            rows=[_draft_row(item) for item in items],
            expires_at=task.retain_until,
        )
        for object_name, items in grouped.items()
    ]
    if drafts:
        MonitorAccessDraft.objects.bulk_create(drafts)


def _task_status_from_items(items: list[MonitorLinkTaskItem]) -> str:
    if any(item.status in {ITEM_NOT_FOUND, ITEM_NEEDS_OBJECT} for item in items):
        return STATUS_WAITING_ACCESS
    return STATUS_COMPLETED


def _summary_from_items(items: list[MonitorLinkTaskItem]) -> dict[str, int]:
    counts = _empty_counts()
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
    counts["total"] = len(items)
    return counts


def serialize_task(task: MonitorLinkTask) -> dict[str, Any]:
    items = list(task.items.all())
    drafts = list(task.drafts.all())
    return {
        "id": str(task.id),
        "status": task.status,
        "operator": task.operator,
        "team": task.team,
        "summary": task.summary,
        "retain_until": task.retain_until.isoformat() if task.retain_until else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "items": [
            {
                "id": str(item.id),
                "inst_uuid": item.inst_uuid,
                "model_id": item.model_id,
                "object_name": item.object_name,
                "inst_name": item.inst_name,
                "ip": item.ip,
                "status": item.status,
                "monitor_id": item.monitor_id,
            }
            for item in items
        ],
        "drafts": [
            {
                "id": str(draft.id),
                "object_name": draft.object_name,
                "row_count": len(draft.rows or []),
            }
            for draft in drafts
        ],
    }


def serialize_draft(draft: MonitorAccessDraft) -> dict[str, Any]:
    rows = draft.rows if isinstance(draft.rows, list) else []
    return {
        "id": str(draft.id),
        "object_name": draft.object_name,
        "task_id": str(draft.task_id),
        "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
        "rows": rows,
    }


def _org_ids(values) -> set[int]:
    ids: set[int] = set()
    for item in values or []:
        number = _as_int_or_none(item)
        if number is not None:
            ids.add(number)
    return ids


def resolved_current_team(request) -> int | None:
    """只接受调用者组织树内的 current_team；空树或伪造 cookie 一律 None。"""
    team = _as_int_or_none(get_current_team(request))
    if team is None:
        return None
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return team
    group_ids = collect_group_tree_ids(getattr(user, "group_list", []) or [])
    if not group_ids or team not in group_ids:
        return None
    return team


def can_see_task(task: MonitorLinkTask, request, actor_scope: dict[str, Any]) -> bool:
    if getattr(request.user, "is_superuser", False):
        return True
    stored = _org_ids(task.team)
    if not stored:
        return False
    allowed = _org_ids(actor_scope.get("allowed_org_ids"))
    if not allowed:
        allowed = collect_group_tree_ids(getattr(request.user, "group_list", []) or [])
    return bool(allowed & stored)


class CmdbMonitorTaskService:
    @classmethod
    def create(cls, inst_uuids: list[str], *, request) -> MonitorLinkTask:
        if len(inst_uuids) > BATCH_LIMIT:
            raise ValueError("batch push exceeds limit of 100")
        actor_scope = build_cmdb_push_actor_scope(request)
        current_team = resolved_current_team(request)
        try:
            with transaction.atomic():
                return cls._create_in_txn(inst_uuids, request=request, actor_scope=actor_scope, current_team=current_team)
        except ValueError:
            raise
        except Exception as exc:
            logger.error(
                _CREATE_FAILED,
                "create",
                type(exc).__name__,
                len(inst_uuids),
                exc_info=_safe_exc_info(exc, _SAFE_CREATE_ERROR),
            )
            raise

    @classmethod
    def _create_in_txn(cls, inst_uuids, *, request, actor_scope, current_team) -> MonitorLinkTask:
        pending_builtin: list[str] = []
        prepared: list[dict[str, Any]] = []
        for inst_uuid in inst_uuids:
            if not _is_uuid_authorized(request, inst_uuid):
                prepared.append(
                    {
                        "snapshot": _snapshot(None, inst_uuid),
                        "status": ITEM_FAILED,
                        "object_name": "",
                        "monitor_id": "",
                    }
                )
                continue
            try:
                entity = InstanceManage.query_entity_by_uuid(inst_uuid)
            except Exception as exc:
                logger.error(
                    _ROW_FAILED,
                    inst_uuid,
                    "query_entity",
                    type(exc).__name__,
                    exc_info=_safe_exc_info(exc),
                )
                prepared.append(
                    {
                        "snapshot": _snapshot(None, inst_uuid),
                        "status": ITEM_FAILED,
                        "object_name": "",
                        "monitor_id": "",
                    }
                )
                continue
            if not isinstance(entity, dict) or not entity:
                prepared.append(
                    {
                        "snapshot": _snapshot(None, inst_uuid),
                        "status": ITEM_FAILED,
                        "object_name": "",
                        "monitor_id": "",
                    }
                )
                continue
            snapshot = _snapshot(entity, inst_uuid)
            model_id = snapshot["model_id"]
            if is_platform_tree_model(model_id):
                prepared.append(
                    {
                        "snapshot": snapshot,
                        "status": ITEM_SKIPPED,
                        "object_name": "",
                        "monitor_id": "",
                    }
                )
                continue
            existing = _as_text(entity.get("monitor_id"))
            if existing:
                prepared.append(
                    {
                        "snapshot": snapshot,
                        "status": ITEM_ALREADY_LINKED,
                        "object_name": _mapped_object_name(model_id, current_team) or "",
                        "monitor_id": existing,
                    }
                )
                continue
            if is_builtin_mapped_model(model_id):
                pending_builtin.append(inst_uuid)
                prepared.append(
                    {
                        "snapshot": snapshot,
                        "status": "pending_builtin",
                        "object_name": builtin_object_name(model_id) or "",
                        "monitor_id": "",
                        "entity": entity,
                    }
                )
                continue
            assigned = _mapped_object_name(model_id, current_team)
            if assigned:
                status, monitor_id = _claim_by_unique_name(entity, assigned, actor_scope)
                prepared.append(
                    {
                        "snapshot": snapshot,
                        "status": status,
                        "object_name": assigned,
                        "monitor_id": monitor_id,
                    }
                )
                continue
            prepared.append(
                {
                    "snapshot": snapshot,
                    "status": ITEM_NEEDS_OBJECT,
                    "object_name": "",
                    "monitor_id": "",
                }
            )

        push_by_uuid: dict[str, dict[str, Any]] = {}
        if pending_builtin:
            summary = MonitorLinkService.batch_push(pending_builtin, actor_scope=actor_scope)
            for row in summary.get("results") or []:
                if isinstance(row, dict) and row.get("inst_uuid"):
                    push_by_uuid[str(row["inst_uuid"])] = row

        now = timezone.now()
        task = MonitorLinkTask.objects.create(
            operator=actor_scope.get("operator") or "",
            team=list(actor_scope.get("allowed_org_ids") or []),
            status=STATUS_WAITING_ACCESS,
            summary={},
            retain_until=now + RETAIN_DELTA,
        )
        items: list[MonitorLinkTaskItem] = []
        for row in prepared:
            status = row["status"]
            monitor_id = row["monitor_id"]
            object_name = row["object_name"]
            if status == "pending_builtin":
                pushed = push_by_uuid.get(row["snapshot"]["inst_uuid"]) or {}
                status = pushed.get("status") or ITEM_FAILED
                if status not in _COUNT_KEYS:
                    status = ITEM_FAILED
                monitor_id = _as_text(pushed.get("monitor_id"))
                if not object_name:
                    object_name = builtin_object_name(row["snapshot"]["model_id"]) or ""
            items.append(MonitorLinkTaskItem(**_item_kwargs(task, row["snapshot"], status, object_name, monitor_id)))
        MonitorLinkTaskItem.objects.bulk_create(items)
        _sync_drafts(task)
        task.status = _task_status_from_items(items)
        task.summary = _summary_from_items(items)
        task.save(update_fields=["status", "summary", "updated_at"])
        logger.info(
            _CREATE_DONE,
            str(task.id),
            task.summary.get("total", 0),
            task.summary.get(ITEM_OK, 0),
            task.summary.get(ITEM_ALREADY_LINKED, 0),
            task.summary.get(ITEM_NOT_FOUND, 0),
            task.summary.get(ITEM_CONFLICT, 0),
            task.summary.get(ITEM_FAILED, 0),
            task.summary.get(ITEM_SKIPPED, 0),
            task.summary.get(ITEM_NEEDS_OBJECT, 0),
        )
        return task

    @classmethod
    def refresh(cls, task: MonitorLinkTask) -> MonitorLinkTask:
        changed = False
        waiting = list(task.items.filter(status__in=[ITEM_NOT_FOUND, ITEM_NEEDS_OBJECT]))
        for item in waiting:
            try:
                entity = InstanceManage.query_entity_by_uuid(item.inst_uuid)
            except Exception:
                continue
            monitor_id = _as_text((entity or {}).get("monitor_id"))
            if not monitor_id:
                continue
            item.status = ITEM_OK
            item.monitor_id = monitor_id
            item.save(update_fields=["status", "monitor_id"])
            changed = True
        if changed:
            items = list(task.items.all())
            task.status = _task_status_from_items(items)
            if task.status != STATUS_CANCELLED:
                task.summary = _summary_from_items(items)
                _sync_drafts(task)
                task.save(update_fields=["status", "summary", "updated_at"])
        return task

    @classmethod
    def cancel(cls, task: MonitorLinkTask) -> MonitorLinkTask:
        if task.status == STATUS_CANCELLED:
            return task
        task.status = STATUS_CANCELLED
        task.save(update_fields=["status", "updated_at"])
        return task

    @classmethod
    def assign_object(
        cls,
        task: MonitorLinkTask,
        *,
        item_ids: list[str],
        object_name: str,
        remember: bool,
        request,
        current_team: int | None,
    ) -> MonitorLinkTask:
        object_name = _as_text(object_name)
        if not object_name:
            raise ValueError("object_name is required")
        if task.status == STATUS_CANCELLED:
            raise ValueError("task is cancelled")
        actor_scope = build_cmdb_push_actor_scope(request)
        items = list(task.items.filter(id__in=item_ids, status=ITEM_NEEDS_OBJECT))
        remembered_models: set[str] = set()
        for item in items:
            if is_platform_tree_model(item.model_id):
                continue
            try:
                entity = InstanceManage.query_entity_by_uuid(item.inst_uuid)
            except Exception as exc:
                logger.error(
                    _ROW_FAILED,
                    item.inst_uuid,
                    "query_entity",
                    type(exc).__name__,
                    exc_info=_safe_exc_info(exc),
                )
                item.status = ITEM_FAILED
                item.object_name = object_name
                item.save(update_fields=["status", "object_name"])
                continue
            if not isinstance(entity, dict) or not entity:
                item.status = ITEM_FAILED
                item.object_name = object_name
                item.save(update_fields=["status", "object_name"])
                continue
            status, monitor_id = _claim_by_unique_name(entity, object_name, actor_scope)
            item.status = status
            item.object_name = object_name
            item.monitor_id = monitor_id
            item.inst_name = _as_text(entity.get("inst_name")) or item.inst_name
            item.ip = _first_ip(entity.get("ip")) or _first_ip(entity.get("ip_addr")) or item.ip
            item.port = _first_port(entity.get("port")) or _first_port(entity.get("listen_port")) or item.port
            item.save(update_fields=["status", "object_name", "monitor_id", "inst_name", "ip", "port"])
            if remember and item.model_id:
                remembered_models.add(item.model_id)
        team_id = resolved_current_team(request)
        if remember and team_id is not None and team_id == current_team:
            for model_id in remembered_models:
                ModuleLinkModelMap.objects.update_or_create(
                    team=team_id,
                    model_id=model_id,
                    defaults={"object_name": object_name},
                )
        items = list(task.items.all())
        task.status = _task_status_from_items(items)
        task.summary = _summary_from_items(items)
        _sync_drafts(task)
        task.save(update_fields=["status", "summary", "updated_at"])
        logger.info(_ASSIGN_DONE, str(task.id), object_name, len(item_ids))
        return task

    @classmethod
    def recycle_expired(cls, now: datetime | None = None) -> int:
        cutoff = now or timezone.now()
        if cutoff.tzinfo is None:
            cutoff = timezone.make_aware(cutoff, timezone.get_current_timezone())
        deleted = 0
        while True:
            ids = list(MonitorLinkTask.objects.filter(retain_until__lte=cutoff).values_list("id", flat=True)[:RECYCLE_BATCH_SIZE])
            if not ids:
                break
            MonitorLinkTask.objects.filter(id__in=ids).delete()
            deleted += len(ids)
            if len(ids) < RECYCLE_BATCH_SIZE:
                break
        if deleted:
            logger.info(_RECYCLE_DONE, deleted)
        return deleted

    @classmethod
    def get_task(cls, task_id: UUID, *, request) -> MonitorLinkTask | None:
        task = MonitorLinkTask.objects.filter(id=task_id).first()
        if task is None:
            return None
        actor_scope = build_cmdb_push_actor_scope(request)
        if not can_see_task(task, request, actor_scope):
            return None
        if task.status == STATUS_CANCELLED:
            return task
        if timezone.now() >= task.retain_until:
            return None
        return cls.refresh(task)

    @classmethod
    def get_draft(cls, draft_id: UUID, *, request) -> MonitorAccessDraft | None:
        draft = MonitorAccessDraft.objects.select_related("task").filter(id=draft_id).first()
        if draft is None:
            return None
        task = draft.task
        actor_scope = build_cmdb_push_actor_scope(request)
        if not can_see_task(task, request, actor_scope):
            return None
        if task.status == STATUS_CANCELLED:
            return None
        now = timezone.now()
        if now >= task.retain_until or now >= draft.expires_at:
            return None
        return draft
