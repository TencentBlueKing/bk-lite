"""CMDB 手绑：按监控实例 ID 写入 / 清除 cmdb_id，并按名称或 IP 列候选。

不创建监控实例，不改 ingest 匹配。调用方按返回的 status 分支，不抛占用/未找到异常。

status:
- ok：绑定或清除成功（含幂等）
- occupied：目标已有其它 CI，或该 cmdb_id 已被其它实例占用
- not_found：实例不存在、已删、或组织不在 allowed_org_ids
- type_mismatch：实例存在且组织在范围内，但对象名不符
- mismatch：clear 时 expected_cmdb_id 与当前值不一致（已空则仍 ok）
"""

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.core.logger import monitor_logger as logger
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization

STATUS_OK = "ok"
STATUS_OCCUPIED = "occupied"
STATUS_NOT_FOUND = "not_found"
STATUS_TYPE_MISMATCH = "type_mismatch"
STATUS_MISMATCH = "mismatch"

DEFAULT_CANDIDATE_LIMIT = 50

BIND_OK_TEMPLATE = "event=cmdb_bind_ok monitor_id=%s cmdb_id=%s"
BIND_OCCUPIED_TEMPLATE = "event=cmdb_bind_occupied monitor_id=%s occupied_cmdb_id=%s"
BIND_NOT_FOUND_TEMPLATE = "event=cmdb_bind_not_found monitor_id=%s failed_stage=%s error_type=%s"
BIND_TYPE_MISMATCH_TEMPLATE = "event=cmdb_bind_type_mismatch monitor_id=%s failed_stage=%s error_type=%s"
CLEAR_OK_TEMPLATE = "event=cmdb_clear_ok monitor_id=%s"
CLEAR_MISMATCH_TEMPLATE = "event=cmdb_clear_mismatch monitor_id=%s failed_stage=%s error_type=%s"
CANDIDATES_LISTED_TEMPLATE = "event=cmdb_bind_candidates_listed object_name=%s count=%s"
CANDIDATE_ROW_TEMPLATE = "event=cmdb_bind_candidate_row monitor_id=%s"


def _normalize_id(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_org_ids(allowed_org_ids):
    if not allowed_org_ids:
        return []
    normalized = []
    seen = set()
    for raw in allowed_org_ids:
        try:
            org_id = int(raw)
        except (TypeError, ValueError):
            continue
        if org_id in seen:
            continue
        seen.add(org_id)
        normalized.append(org_id)
    return normalized


def _clamp_limit(limit):
    if limit is None:
        return DEFAULT_CANDIDATE_LIMIT
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_CANDIDATE_LIMIT
    if parsed < 0:
        return 0
    return min(parsed, DEFAULT_CANDIDATE_LIMIT)


def _in_allowed_orgs(monitor_id, org_ids):
    return MonitorInstanceOrganization.objects.filter(
        monitor_instance_id=monitor_id,
        organization__in=org_ids,
    ).exists()


def list_cmdb_bind_candidates(object_name, query, allowed_org_ids, limit=DEFAULT_CANDIDATE_LIMIT):
    """按对象类型与组织列手绑候选；query 同时 icontains 匹配 name / ip。"""
    org_ids = _normalize_org_ids(allowed_org_ids)
    object_name = (object_name or "").strip()
    clamped = _clamp_limit(limit)
    if not org_ids or not object_name or clamped == 0:
        logger.info(CANDIDATES_LISTED_TEMPLATE, object_name or "", 0)
        return []

    qs = (
        MonitorInstance.objects.filter(
            is_deleted=False,
            monitor_object__name=object_name,
            monitorinstanceorganization__organization__in=org_ids,
        )
        .select_related("monitor_object")
        .distinct()
        .order_by("name", "id")
    )
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(Q(name__icontains=needle) | Q(ip__icontains=needle))

    rows = []
    for instance in qs[:clamped]:
        logger.debug(CANDIDATE_ROW_TEMPLATE, instance.id)
        rows.append(
            {
                "id": instance.id,
                "name": instance.name,
                "ip": str(instance.ip) if instance.ip else None,
                "object_name": instance.monitor_object.name,
                "cmdb_id": instance.cmdb_id or None,
            }
        )
    logger.info(CANDIDATES_LISTED_TEMPLATE, object_name, len(rows))
    return rows


def bind_cmdb_id(monitor_id, cmdb_id, object_name, allowed_org_ids):
    """将 cmdb_id 写入指定监控实例；占用或类型不符时拒绝，不抢绑。"""
    org_ids = _normalize_org_ids(allowed_org_ids)
    monitor_id = _normalize_id(monitor_id)
    cmdb_id = _normalize_id(cmdb_id)
    object_name = (object_name or "").strip()
    if not org_ids or not monitor_id or not cmdb_id:
        logger.warning(BIND_NOT_FOUND_TEMPLATE, monitor_id or "", "lookup", STATUS_NOT_FOUND)
        return {"status": STATUS_NOT_FOUND}

    try:
        with transaction.atomic():
            instance = MonitorInstance.objects.select_for_update().select_related("monitor_object").filter(pk=monitor_id).first()
            if instance is None or instance.is_deleted or not _in_allowed_orgs(instance.id, org_ids):
                logger.warning(BIND_NOT_FOUND_TEMPLATE, monitor_id, "lookup", STATUS_NOT_FOUND)
                return {"status": STATUS_NOT_FOUND}
            if instance.monitor_object.name != object_name:
                logger.warning(BIND_TYPE_MISMATCH_TEMPLATE, instance.id, "type_check", STATUS_TYPE_MISMATCH)
                return {"status": STATUS_TYPE_MISMATCH}

            current = instance.cmdb_id or None
            if current == cmdb_id:
                logger.info(BIND_OK_TEMPLATE, instance.id, cmdb_id)
                return {"status": STATUS_OK, "monitor_id": instance.id, "cmdb_id": cmdb_id}
            if current:
                logger.warning(BIND_OCCUPIED_TEMPLATE, instance.id, current)
                return {"status": STATUS_OCCUPIED, "occupied_cmdb_id": current}

            occupier = MonitorInstance.objects.filter(cmdb_id=cmdb_id).exclude(pk=instance.id).first()
            if occupier is not None:
                logger.warning(BIND_OCCUPIED_TEMPLATE, instance.id, occupier.cmdb_id)
                return {"status": STATUS_OCCUPIED, "occupied_cmdb_id": occupier.cmdb_id}

            instance.cmdb_id = cmdb_id
            instance.save(update_fields=["cmdb_id", "updated_at"])
    except IntegrityError:
        logger.warning(BIND_OCCUPIED_TEMPLATE, monitor_id, cmdb_id)
        return {"status": STATUS_OCCUPIED, "occupied_cmdb_id": cmdb_id}

    logger.info(BIND_OK_TEMPLATE, instance.id, cmdb_id)
    return {"status": STATUS_OK, "monitor_id": instance.id, "cmdb_id": cmdb_id}


def clear_cmdb_id(monitor_id, expected_cmdb_id, allowed_org_ids):
    """仅在 expected 匹配时清空 cmdb_id；不改 node_id。"""
    org_ids = _normalize_org_ids(allowed_org_ids)
    monitor_id = _normalize_id(monitor_id)
    expected = _normalize_id(expected_cmdb_id)
    if not org_ids or not monitor_id:
        logger.warning(BIND_NOT_FOUND_TEMPLATE, monitor_id or "", "clear", STATUS_NOT_FOUND)
        return {"status": STATUS_NOT_FOUND}

    with transaction.atomic():
        instance = MonitorInstance.objects.select_for_update().filter(pk=monitor_id).first()
        if instance is None or instance.is_deleted or not _in_allowed_orgs(instance.id, org_ids):
            logger.warning(BIND_NOT_FOUND_TEMPLATE, monitor_id, "clear", STATUS_NOT_FOUND)
            return {"status": STATUS_NOT_FOUND}

        current = instance.cmdb_id or None
        if current is None:
            logger.info(CLEAR_OK_TEMPLATE, instance.id)
            return {"status": STATUS_OK, "monitor_id": instance.id, "cmdb_id": None}
        if expected is not None and current != expected:
            logger.warning(CLEAR_MISMATCH_TEMPLATE, instance.id, "expected_cmdb_id", STATUS_MISMATCH)
            return {"status": STATUS_MISMATCH}

        instance.cmdb_id = None
        instance.save(update_fields=["cmdb_id", "updated_at"])

    logger.info(CLEAR_OK_TEMPLATE, instance.id)
    return {"status": STATUS_OK, "monitor_id": instance.id, "cmdb_id": None}
