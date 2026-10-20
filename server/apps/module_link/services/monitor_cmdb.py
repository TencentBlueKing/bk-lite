"""监控 → CMDB 同步任务：第一段只写关联指针，确认后才新建缺失 CI。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.cmdb.services.host_sync_identity import parse_cloud_id
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.module_ingest import ensure_model_monitor_id_attr
from apps.cmdb.services.monitor_link import MonitorLinkService
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import module_link_logger as logger
from apps.module_link.constants import (
    BATCH_LIMIT,
    IP_IDENTITY_MODEL_IDS,
    ITEM_ALREADY_LINKED,
    ITEM_CONFLICT,
    ITEM_FAILED,
    ITEM_NOT_FOUND,
    ITEM_OK,
    ITEM_SKIPPED,
    RECYCLE_BATCH_SIZE,
    RETAIN_DELTA,
    REVERSE_ITEM_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_WAITING_CREATE,
    builtin_model_id,
)
from apps.module_link.models import MonitorCmdbTask, MonitorCmdbTaskItem
from apps.module_link.services.cmdb_monitor import can_see_task
from apps.module_link.services.row_message import item_message
from apps.monitor.models import MonitorInstance
from apps.monitor.services.module_push import build_monitor_push_actor_scope
from apps.monitor.utils.alert_name_variables import resolve_resource_ip

_CREATE_DONE = (
    "event=module_link_monitor_cmdb_task_completed task_id=%s total=%s ok=%s " "already_linked=%s not_found=%s conflict=%s failed=%s skipped_model=%s"
)
_CREATE_FAILED = "event=module_link_monitor_cmdb_task_failed failed_stage=%s error_type=%s total=%s"
_CREATE_MISSING_DONE = "event=module_link_monitor_cmdb_create_missing_completed task_id=%s count=%s created=%s failed=%s"
_RECYCLE_DONE = "event=module_link_monitor_cmdb_recycle_completed deleted=%s"
_ROW_FAILED = "event=module_link_monitor_cmdb_row_failed monitor_id=%s failed_stage=%s error_type=%s"
_SAFE_ROW_ERROR = "module link monitor cmdb row failed"
_SAFE_CREATE_ERROR = "module link monitor cmdb task failed"
_COUNT_KEYS = (
    ITEM_OK,
    ITEM_ALREADY_LINKED,
    ITEM_NOT_FOUND,
    ITEM_CONFLICT,
    ITEM_FAILED,
    ITEM_SKIPPED,
)
_LOG_ID_LIMIT = 128
CMDB_CREATE_PERMISSION = "asset_info-Edit"


def _safe_exc_info(exc: BaseException, message: str = _SAFE_ROW_ERROR):
    return (type(exc), RuntimeError(message), exc.__traceback__)


def _as_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _log_id(value: Any) -> str:
    text = _as_text(value).replace("\r", " ").replace("\n", " ")
    return text[:_LOG_ID_LIMIT]


def _as_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _default_monitor_cloud_region_id() -> int:
    from apps.node_mgmt.constants.database import CloudRegionConstants

    return CloudRegionConstants.DEFAULT_CLOUD_REGION_ID


def _monitor_ip(instance: MonitorInstance) -> str:
    ip = _as_text(getattr(instance, "ip", None))
    if ip:
        return ip
    return _as_text(resolve_resource_ip(getattr(instance, "summary_facts", None), None))


def _load_node_cloud_maps(instances: list[MonitorInstance]) -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    """实例未填云区域/IP 时，从监控节点侧按 node_id / 唯一 IP 取云区域和节点 IP。"""
    node_ids = [_as_text(getattr(row, "node_id", "")) for row in instances]
    node_ids = [node_id for node_id in node_ids if node_id]
    ips_need = []
    for row in instances:
        if parse_cloud_id(getattr(row, "cloud_region_id", None)) is not None:
            continue
        ip = _monitor_ip(row)
        if ip:
            ips_need.append(ip)
    by_id: dict[str, int] = {}
    by_ip: dict[str, int] = {}
    node_ip_by_id: dict[str, str] = {}
    try:
        from apps.node_mgmt.models.sidecar import Node
    except ImportError:
        return by_id, by_ip, node_ip_by_id
    if node_ids:
        for node_id, cloud_id, ip in Node.objects.filter(pk__in=node_ids).values_list("id", "cloud_region_id", "ip"):
            parsed = parse_cloud_id(cloud_id)
            if parsed is not None:
                by_id[str(node_id)] = parsed
            text = _as_text(ip)
            if text:
                node_ip_by_id[str(node_id)] = text
    if ips_need:
        grouped: dict[str, set[int]] = {}
        for ip, cloud_id in Node.objects.filter(ip__in=ips_need).values_list("ip", "cloud_region_id"):
            parsed = parse_cloud_id(cloud_id)
            if parsed is None:
                continue
            grouped.setdefault(str(ip), set()).add(parsed)
        for ip, clouds in grouped.items():
            if len(clouds) == 1:
                by_ip[ip] = next(iter(clouds))
    return by_id, by_ip, node_ip_by_id


def _resolve_cloud_region_id(
    instance: MonitorInstance,
    *,
    node_cloud_by_id: dict[str, int] | None = None,
    node_cloud_by_ip: dict[str, int] | None = None,
) -> int | None:
    parsed = parse_cloud_id(getattr(instance, "cloud_region_id", None))
    if parsed is not None:
        return parsed
    if node_cloud_by_id is None and node_cloud_by_ip is None:
        node_cloud_by_id, node_cloud_by_ip, _ = _load_node_cloud_maps([instance])
    node_id = _as_text(getattr(instance, "node_id", ""))
    if node_id and node_cloud_by_id:
        parsed = parse_cloud_id(node_cloud_by_id.get(node_id))
        if parsed is not None:
            return parsed
    ip = _monitor_ip(instance)
    if ip and node_cloud_by_ip:
        parsed = parse_cloud_id(node_cloud_by_ip.get(ip))
        if parsed is not None:
            return parsed
    return None


def _resolve_instance_ip(
    instance: MonitorInstance,
    *,
    node_ip_by_id: dict[str, str] | None = None,
) -> str:
    ip = _monitor_ip(instance)
    if ip:
        return ip
    object_name = _as_text(getattr(getattr(instance, "monitor_object", None), "name", ""))
    if object_name != "Host":
        return ""
    node_id = _as_text(getattr(instance, "node_id", ""))
    if not node_id:
        return ""
    if node_ip_by_id is None:
        _, _, node_ip_by_id = _load_node_cloud_maps([instance])
    return _as_text((node_ip_by_id or {}).get(node_id))


def _as_org_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _int_id_set(values) -> set[int]:
    result: set[int] = set()
    for value in values or []:
        if value in (None, ""):
            continue
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _orgs_in_scope(organization, actor_scope: dict[str, Any]) -> list:
    allowed = _int_id_set(actor_scope.get("allowed_org_ids"))
    selected: list[int] = []
    seen: set[int] = set()
    for org_id in organization if isinstance(organization, list) else []:
        if org_id in (None, ""):
            continue
        try:
            parsed = int(org_id)
        except (TypeError, ValueError):
            continue
        if parsed in allowed and parsed not in seen:
            selected.append(parsed)
            seen.add(parsed)
    return selected


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in _COUNT_KEYS}


def _summary_from_items(items: list[MonitorCmdbTaskItem]) -> dict[str, int]:
    counts = _empty_counts()
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
    counts["total"] = len(items)
    return counts


def _task_status_from_items(items: list[MonitorCmdbTaskItem]) -> str:
    if any(item.status == ITEM_NOT_FOUND for item in items):
        return STATUS_WAITING_CREATE
    return STATUS_COMPLETED


def _has_cmdb_asset_edit(request) -> bool:
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return True
    perms = getattr(user, "permission", None)
    if isinstance(perms, dict):
        return CMDB_CREATE_PERMISSION in (perms.get("cmdb") or set())
    if isinstance(perms, set):
        return CMDB_CREATE_PERMISSION in perms
    return False


def _is_monitor_id_authorized(request, monitor_id: str) -> bool:
    from apps.monitor.views.monitor_instance import _ensure_operate_instances

    try:
        _ensure_operate_instances(request, [monitor_id])
        return True
    except Exception:
        return False


def _authorized_monitor_ids(request, monitor_ids: list[str]) -> set[str]:
    ids = [monitor_id for monitor_id in monitor_ids if monitor_id]
    if not ids:
        return set()
    from apps.monitor.views.monitor_instance import _ensure_operate_instances

    try:
        _ensure_operate_instances(request, ids)
        return set(ids)
    except Exception:
        return {monitor_id for monitor_id in ids if _is_monitor_id_authorized(request, monitor_id)}


def serialize_task(task: MonitorCmdbTask) -> dict[str, Any]:
    items = list(task.items.all())
    return {
        "id": str(task.id),
        "status": task.status,
        "operator": task.operator,
        "object_name": task.object_name,
        "team": task.team,
        "summary": task.summary,
        "retain_until": task.retain_until.isoformat() if task.retain_until else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "items": [
            {
                "id": str(item.id),
                "monitor_id": item.monitor_id,
                "model_id": item.model_id,
                "object_name": item.object_name,
                "inst_name": item.inst_name,
                "ip": item.ip,
                "status": item.status,
                "cmdb_id": item.cmdb_id,
                "message": item.message or "",
            }
            for item in items
        ],
    }


def _empty_snapshot(monitor_id: str) -> dict[str, Any]:
    return {
        "monitor_id": monitor_id,
        "inst_name": "",
        "ip": "",
        "organization": [],
        "cloud_region_id": None,
    }


def _snapshot(
    instance: MonitorInstance,
    *,
    node_cloud_by_id: dict[str, int] | None = None,
    node_cloud_by_ip: dict[str, int] | None = None,
    node_ip_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    org_ids = [rel.organization for rel in instance.monitorinstanceorganization_set.all()]
    return {
        "monitor_id": str(instance.id),
        "inst_name": _as_text(instance.name),
        "ip": _resolve_instance_ip(instance, node_ip_by_id=node_ip_by_id),
        "organization": _as_org_list(org_ids),
        "cloud_region_id": _resolve_cloud_region_id(instance, node_cloud_by_id=node_cloud_by_id, node_cloud_by_ip=node_cloud_by_ip),
        "cmdb_id": _as_text(instance.cmdb_id),
        "object_name": _as_text(getattr(instance.monitor_object, "name", "")),
    }


def _public_cmdb_id(entity: dict[str, Any] | None) -> str:
    if not isinstance(entity, dict):
        return ""
    return _as_text(entity.get("inst_uuid"))


def _lookup_by_uuid(cmdb_id: str, *, monitor_id: str = "") -> dict[str, Any] | None:
    if not cmdb_id:
        return None
    try:
        found = InstanceManage.query_entity_by_uuid(cmdb_id)
    except Exception as exc:
        logger.error(
            _ROW_FAILED,
            _log_id(monitor_id or cmdb_id),
            "query_entity",
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
        raise
    return found if isinstance(found, dict) and found else None


def _lookup_identity(model_id: str, identity: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    try:
        found = InstanceManage.query_entity_by_identity(model_id, identity)
    except BaseAppException:
        return ITEM_CONFLICT, None
    except Exception as exc:
        logger.error(
            _ROW_FAILED,
            _log_id(identity.get("monitor_id") or identity.get("inst_name") or identity.get("ip_addr")),
            "query_identity",
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
        return ITEM_FAILED, None
    if isinstance(found, dict) and found:
        return ITEM_OK, found
    return ITEM_NOT_FOUND, None


def _find_by_identity(model_id: str, snapshot: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    ip = snapshot["ip"]
    if model_id == "host":
        cloud = parse_cloud_id(snapshot.get("cloud_region_id"))
        if not ip or cloud is None:
            return ITEM_NOT_FOUND, None
        return _lookup_identity(model_id, {"ip_addr": ip, "cloud": cloud})
    if model_id in IP_IDENTITY_MODEL_IDS and ip:
        status, found = _lookup_identity(model_id, {"ip_addr": ip})
        if status != ITEM_NOT_FOUND:
            return status, found
    inst_name = snapshot["inst_name"]
    if not inst_name:
        return ITEM_NOT_FOUND, None
    return _lookup_identity(model_id, {"inst_name": inst_name})


def _bind_pair(cmdb_id: str, monitor_id: str, actor_scope: dict[str, Any]) -> tuple[str, str, str]:
    try:
        result = MonitorLinkService.bind(cmdb_id, monitor_id, actor_scope)
    except Exception as exc:
        logger.error(
            _ROW_FAILED,
            _log_id(monitor_id),
            "bind",
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
        return ITEM_FAILED, "", item_message(stage="bind", exc=exc)
    if not isinstance(result, dict):
        return ITEM_FAILED, "", item_message(stage="bind")
    status = result.get("status")
    if status == "ok":
        return ITEM_OK, cmdb_id, ""
    if status in {"occupied", "confirm_required"}:
        return ITEM_CONFLICT, "", item_message(stage="bind_occupied")
    if status in {"not_found", "type_mismatch"}:
        return ITEM_NOT_FOUND, "", item_message(stage="bind_mismatch")
    return ITEM_FAILED, "", item_message(stage="bind")


def _pair_status(entity: dict[str, Any], monitor_id: str, actor_scope: dict[str, Any]) -> tuple[str, str, str]:
    cmdb_id = _public_cmdb_id(entity)
    if not cmdb_id:
        return ITEM_FAILED, "", item_message(stage="missing_cmdb_id")
    existing_monitor = _as_text(entity.get("monitor_id"))
    if existing_monitor == monitor_id:
        current_cmdb = ""
        try:
            instance = MonitorInstance.objects.filter(pk=monitor_id).only("cmdb_id").first()
            current_cmdb = _as_text(getattr(instance, "cmdb_id", ""))
        except Exception:
            current_cmdb = ""
        if current_cmdb == cmdb_id:
            return ITEM_ALREADY_LINKED, cmdb_id, ""
        return _bind_pair(cmdb_id, monitor_id, actor_scope)
    if existing_monitor and existing_monitor != monitor_id:
        return ITEM_CONFLICT, "", item_message(stage="bind_occupied")
    return _bind_pair(cmdb_id, monitor_id, actor_scope)


def _link_one(snapshot: dict[str, Any], model_id: str, actor_scope: dict[str, Any]) -> tuple[str, str, str]:
    monitor_id = snapshot["monitor_id"]
    existing_cmdb = snapshot["cmdb_id"]
    if existing_cmdb:
        try:
            entity = _lookup_by_uuid(existing_cmdb, monitor_id=monitor_id)
        except Exception as exc:
            return ITEM_FAILED, "", item_message(stage="query_entity", exc=exc)
        if entity:
            return _pair_status(entity, monitor_id, actor_scope)

    status, found = _lookup_identity(model_id, {"monitor_id": monitor_id})
    if status == ITEM_CONFLICT:
        return ITEM_CONFLICT, "", item_message(stage="identity_conflict")
    if status == ITEM_FAILED:
        return ITEM_FAILED, "", item_message(stage="query_identity")
    if found:
        return _pair_status(found, monitor_id, actor_scope)

    status, found = _find_by_identity(model_id, snapshot)
    if status == ITEM_FAILED:
        return ITEM_FAILED, "", item_message(stage="query_identity")
    if status == ITEM_CONFLICT:
        return ITEM_CONFLICT, "", item_message(stage="identity_conflict")
    if status == ITEM_NOT_FOUND or not found:
        stage = "host_identity_not_found" if model_id == "host" else "identity_not_found"
        return ITEM_NOT_FOUND, "", item_message(stage=stage)
    return _pair_status(found, monitor_id, actor_scope)


def _create_ci(item: MonitorCmdbTaskItem, actor_scope: dict[str, Any]) -> tuple[str, str, str]:
    model_id = item.model_id
    operator = actor_scope.get("operator") or ""
    allowed_org_ids = list(actor_scope.get("allowed_org_ids") or [])
    orgs = _orgs_in_scope(item.organization, actor_scope)
    if not orgs:
        return ITEM_FAILED, "", item_message(stage="missing_org")
    payload: dict[str, Any] = {
        "inst_name": item.inst_name or item.ip or item.monitor_id,
        "organization": orgs,
    }
    ip = _as_text(item.ip)
    cloud = parse_cloud_id(item.cloud_region_id)
    instance = None
    if not ip or cloud is None:
        instance = MonitorInstance.objects.filter(pk=item.monitor_id, is_deleted=False).select_related("monitor_object").first()
    if not ip and instance is not None:
        ip = _resolve_instance_ip(instance)
    if ip:
        payload["ip_addr"] = ip
    if cloud is None and instance is not None:
        cloud = _resolve_cloud_region_id(instance)
    if model_id == "host":
        if not ip:
            return ITEM_FAILED, "", item_message(stage="host_missing_ip")
        if cloud is None:
            cloud = _default_monitor_cloud_region_id()
        payload["cloud"] = cloud
    try:
        ensure_model_monitor_id_attr(model_id, username=operator or "admin")
        created = InstanceManage.instance_create(
            model_id=model_id,
            instance_info=payload,
            operator=operator,
            allowed_org_ids=allowed_org_ids,
            schedule_post_actions=False,
        )
    except Exception as exc:
        logger.error(
            _ROW_FAILED,
            _log_id(item.monitor_id),
            "create_ci",
            type(exc).__name__,
            exc_info=_safe_exc_info(exc),
        )
        return ITEM_FAILED, "", item_message(stage="create_ci", exc=exc)
    cmdb_id = _public_cmdb_id(created if isinstance(created, dict) else None)
    if not cmdb_id:
        return ITEM_FAILED, "", item_message(stage="missing_cmdb_id")
    bind_status, bound_id, message = _bind_pair(cmdb_id, item.monitor_id, actor_scope)
    if bind_status != ITEM_OK:
        return bind_status, "", message
    return ITEM_OK, bound_id or cmdb_id, ""


class MonitorCmdbTaskService:
    @classmethod
    def create(cls, monitor_ids: list[str], object_name: str, *, request) -> MonitorCmdbTask:
        object_name = _as_text(object_name)
        model_id = builtin_model_id(object_name)
        if not model_id:
            raise ValueError("object_name 没有内置反向映射")
        if not monitor_ids:
            raise ValueError("monitor_ids 必须是非空数组")
        if len(monitor_ids) > BATCH_LIMIT:
            raise ValueError("batch push exceeds limit of 100")
        actor_scope = build_monitor_push_actor_scope(request)
        try:
            with transaction.atomic():
                return cls._create_in_txn(monitor_ids, object_name, model_id, request=request, actor_scope=actor_scope)
        except ValueError:
            raise
        except Exception as exc:
            logger.error(
                _CREATE_FAILED,
                "create",
                type(exc).__name__,
                len(monitor_ids),
                exc_info=_safe_exc_info(exc, _SAFE_CREATE_ERROR),
            )
            raise

    @classmethod
    def _create_in_txn(cls, monitor_ids, object_name, model_id, *, request, actor_scope) -> MonitorCmdbTask:
        instances = {
            str(row.id): row
            for row in MonitorInstance.objects.filter(id__in=monitor_ids, is_deleted=False)
            .select_related("monitor_object")
            .prefetch_related("monitorinstanceorganization_set")
        }
        node_cloud_by_id, node_cloud_by_ip, node_ip_by_id = _load_node_cloud_maps(list(instances.values()))
        allowed = _authorized_monitor_ids(request, monitor_ids)
        prepared: list[dict[str, Any]] = []
        for monitor_id in monitor_ids:
            if monitor_id not in allowed:
                prepared.append(
                    {
                        "snapshot": _empty_snapshot(monitor_id),
                        "status": ITEM_FAILED,
                        "cmdb_id": "",
                        "message": item_message(stage="unauthorized"),
                    }
                )
                continue
            instance = instances.get(monitor_id)
            if instance is None:
                prepared.append(
                    {
                        "snapshot": _empty_snapshot(monitor_id),
                        "status": ITEM_FAILED,
                        "cmdb_id": "",
                        "message": item_message(stage="missing_instance"),
                    }
                )
                continue
            snapshot = _snapshot(
                instance,
                node_cloud_by_id=node_cloud_by_id,
                node_cloud_by_ip=node_cloud_by_ip,
                node_ip_by_id=node_ip_by_id,
            )
            if snapshot["object_name"] and snapshot["object_name"] != object_name:
                prepared.append(
                    {
                        "snapshot": snapshot,
                        "status": ITEM_FAILED,
                        "cmdb_id": "",
                        "message": item_message(stage="object_mismatch"),
                    }
                )
                continue
            status, cmdb_id, message = _link_one(snapshot, model_id, actor_scope)
            if status not in REVERSE_ITEM_STATUSES:
                status = ITEM_FAILED
                message = message or item_message(stage="bind")
            prepared.append({"snapshot": snapshot, "status": status, "cmdb_id": cmdb_id, "message": message})

        now = timezone.now()
        task = MonitorCmdbTask.objects.create(
            operator=actor_scope.get("operator") or "",
            team=list(actor_scope.get("allowed_org_ids") or []),
            object_name=object_name,
            status=STATUS_WAITING_CREATE,
            summary={},
            retain_until=now + RETAIN_DELTA,
        )
        items = [
            MonitorCmdbTaskItem(
                task=task,
                monitor_id=row["snapshot"]["monitor_id"],
                object_name=object_name,
                model_id=model_id,
                inst_name=row["snapshot"].get("inst_name") or "",
                ip=row["snapshot"].get("ip") or "",
                organization=row["snapshot"].get("organization") or [],
                cloud_region_id=row["snapshot"].get("cloud_region_id"),
                status=row["status"],
                cmdb_id=row["cmdb_id"] or "",
                message=row.get("message") or "",
            )
            for row in prepared
        ]
        MonitorCmdbTaskItem.objects.bulk_create(items)
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
        )
        return task

    @classmethod
    def refresh(cls, task: MonitorCmdbTask) -> MonitorCmdbTask:
        waiting = list(task.items.filter(status__in=[ITEM_NOT_FOUND, ITEM_CONFLICT]))
        if not waiting:
            return task
        changed = False
        for item in waiting:
            instance = MonitorInstance.objects.filter(pk=item.monitor_id, is_deleted=False).only("cmdb_id").first()
            cmdb_id = _as_text(getattr(instance, "cmdb_id", ""))
            if not cmdb_id:
                continue
            item.status = ITEM_OK
            item.cmdb_id = cmdb_id
            item.save(update_fields=["status", "cmdb_id"])
            changed = True
        if changed:
            items = list(task.items.all())
            if task.status != STATUS_CANCELLED:
                task.status = _task_status_from_items(items)
                task.summary = _summary_from_items(items)
                task.save(update_fields=["status", "summary", "updated_at"])
        return task

    @classmethod
    def cancel(cls, task: MonitorCmdbTask) -> MonitorCmdbTask:
        if task.status == STATUS_CANCELLED:
            return task
        task.status = STATUS_CANCELLED
        task.save(update_fields=["status", "updated_at"])
        return task

    @classmethod
    def create_missing(cls, task: MonitorCmdbTask, item_ids: list[str], *, request) -> MonitorCmdbTask:
        if task.status == STATUS_CANCELLED:
            raise ValueError("task is cancelled")
        if len(item_ids) > BATCH_LIMIT:
            raise ValueError("batch push exceeds limit of 100")
        actor_scope = build_monitor_push_actor_scope(request)
        items = list(task.items.filter(id__in=item_ids, status=ITEM_NOT_FOUND))
        created = 0
        failed = 0
        has_edit = _has_cmdb_asset_edit(request)
        allowed = _authorized_monitor_ids(request, [item.monitor_id for item in items])
        for item in items:
            if item.monitor_id not in allowed:
                item.status = ITEM_FAILED
                item.message = item_message(stage="unauthorized")
                item.save(update_fields=["status", "message"])
                failed += 1
                continue
            if not has_edit:
                logger.warning(_ROW_FAILED, _log_id(item.monitor_id), "create_ci", "PermissionDenied")
                item.status = ITEM_FAILED
                item.message = item_message(stage="create_ci_permission")
                item.save(update_fields=["status", "message"])
                failed += 1
                continue
            status, cmdb_id, message = _create_ci(item, actor_scope)
            item.status = status if status in REVERSE_ITEM_STATUSES else ITEM_FAILED
            item.cmdb_id = cmdb_id if item.status == ITEM_OK else ""
            item.message = "" if item.status == ITEM_OK else message
            item.save(update_fields=["status", "cmdb_id", "message"])
            if item.status == ITEM_OK:
                created += 1
            else:
                failed += 1
        items = list(task.items.all())
        task.status = _task_status_from_items(items)
        task.summary = _summary_from_items(items)
        task.save(update_fields=["status", "summary", "updated_at"])
        logger.info(_CREATE_MISSING_DONE, str(task.id), len(item_ids), created, failed)
        return task

    @classmethod
    def recycle_expired(cls, now: datetime | None = None) -> int:
        cutoff = now or timezone.now()
        if cutoff.tzinfo is None:
            cutoff = timezone.make_aware(cutoff, timezone.get_current_timezone())
        deleted = 0
        while True:
            ids = list(MonitorCmdbTask.objects.filter(retain_until__lte=cutoff).values_list("id", flat=True)[:RECYCLE_BATCH_SIZE])
            if not ids:
                break
            MonitorCmdbTask.objects.filter(id__in=ids).delete()
            deleted += len(ids)
            if len(ids) < RECYCLE_BATCH_SIZE:
                break
        if deleted:
            logger.info(_RECYCLE_DONE, deleted)
        return deleted

    @classmethod
    def get_task(cls, task_id: UUID, *, request) -> MonitorCmdbTask | None:
        task = MonitorCmdbTask.objects.filter(id=task_id).first()
        if task is None:
            return None
        actor_scope = build_monitor_push_actor_scope(request)
        if not can_see_task(task, request, actor_scope):
            return None
        if task.status == STATUS_CANCELLED:
            return task
        if timezone.now() >= task.retain_until:
            return None
        return cls.refresh(task)
