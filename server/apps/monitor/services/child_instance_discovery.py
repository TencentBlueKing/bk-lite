from datetime import datetime, timezone as datetime_timezone

from celery import current_app
from django.db import transaction
from django.utils import timezone

from apps.core.logger import monitor_logger as logger, safe_exception_info
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.tasks.utils.metric_query import _LABEL_NAME_RE, _escape_label_value
from apps.monitor.utils.dimension import build_dimensions, parse_instance_id

CHILD_DISCOVERY_WARMUP_SECONDS = 600
CHILD_DISCOVERY_MIN_INTERVAL_SECONDS = 60
CHILD_DISCOVERY_FULL_SYNC_SECONDS = 600
DEFAULT_COLLECT_INTERVAL_SECONDS = 60
CHILD_DISCOVERY_TASK_ID_PREFIX = "monitor-child-discovery:"

LOG_SCHEDULED = (
    "event=child_instance_discovery_scheduled parent_instance_id=%s countdown=%s interval=%s"
)
LOG_STARTED = "event=child_instance_discovery_started parent_instance_id=%s"
LOG_COMPLETED = (
    "event=child_instance_discovery_completed parent_instance_id=%s added=%s restored=%s"
)
LOG_SKIPPED = "event=child_instance_discovery_skipped parent_instance_id=%s reason=%s"
LOG_STOPPED = "event=child_instance_discovery_stopped parent_instance_id=%s reason=%s"
LOG_CANCELLED = "event=child_instance_discovery_cancelled parent_instance_id=%s"
LOG_FAILED = (
    "event=child_instance_discovery_failed parent_instance_id=%s failed_stage=%s error_type=%s"
)


def normalize_collect_interval(*candidates, default=DEFAULT_COLLECT_INTERVAL_SECONDS):
    """把表单/配置里的采集间隔收成正整数秒，无法解析时回落到默认 60s。"""
    for raw in candidates:
        if raw in (None, ""):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return default


def format_vm_step(interval_seconds):
    """VM instant query 的 step 不得短于采集间隔，避免把尚未上报的子对象当成缺失。"""
    seconds = max(normalize_collect_interval(interval_seconds), CHILD_DISCOVERY_MIN_INTERVAL_SECONDS)
    return f"{seconds}s"


def next_child_discovery_countdown(age_seconds, interval_seconds):
    """计算专用子对象发现任务的下一次 countdown。

    - 采集间隔 > 60s 且创建未满 10 分钟：每 60s
    - 否则按采集间隔（不少于 60s）
    - 间隔已 ≥ 10 分钟且预热结束：停掉专用任务，交给全量 Beat
    """
    interval = max(normalize_collect_interval(interval_seconds), CHILD_DISCOVERY_MIN_INTERVAL_SECONDS)
    try:
        age = max(0, int(age_seconds or 0))
    except (TypeError, ValueError):
        age = 0
    in_warmup = age < CHILD_DISCOVERY_WARMUP_SECONDS
    if in_warmup and interval > CHILD_DISCOVERY_MIN_INTERVAL_SECONDS:
        return CHILD_DISCOVERY_MIN_INTERVAL_SECONDS
    if not in_warmup and interval >= CHILD_DISCOVERY_FULL_SYNC_SECONDS:
        return None
    return interval


def child_discovery_task_id(parent_instance_id):
    return f"{CHILD_DISCOVERY_TASK_ID_PREFIX}{parent_instance_id}"


def parent_has_child_objects(monitor_object_id):
    if monitor_object_id in (None, ""):
        return False
    return MonitorObject.objects.filter(parent_id=monitor_object_id).exists()


def inject_promql_label_matchers(query, labels):
    """把父实例标签注入 default_metric 的第一组 selector，收窄 VM 查询。"""
    if not query or not labels:
        return query
    matchers = []
    for name, value in labels.items():
        if value in (None, "") or not _LABEL_NAME_RE.match(str(name)):
            continue
        matchers.append(f'{name}="{_escape_label_value(value)}"')
    if not matchers:
        return query
    extra = ",".join(matchers)
    start = query.find("{")
    end = query.find("}", start + 1) if start != -1 else -1
    if start == -1 or end == -1:
        return query
    inner = query[start + 1 : end].strip()
    if inner:
        injected = f"{inner}{extra}" if inner.endswith(",") else f"{inner},{extra}"
    else:
        injected = extra
    return f"{query[: start + 1]}{injected}{query[end:]}"


def parent_promql_labels(parent_instance):
    if parent_instance is None:
        return {}
    keys = getattr(parent_instance.monitor_object, "instance_id_keys", None) or []
    return {
        key: value
        for key, value in build_dimensions(parse_instance_id(parent_instance.id), keys).items()
        if value not in (None, "")
    }


def _discovery_task():
    from apps.monitor.tasks.grouping_rule import discover_child_instances

    return discover_child_instances


def enqueue_child_instance_discovery(parent_instance_id, started_at=None, countdown=0):
    """为含子对象的父实例入队专用发现任务；同一父实例固定 task id，避免风暴。"""
    if parent_instance_id in (None, ""):
        return False
    parent = (
        MonitorInstance.objects.filter(id=parent_instance_id, is_deleted=False, is_active=True)
        .only("id", "monitor_object_id", "interval")
        .first()
    )
    if parent is None:
        logger.info(LOG_SKIPPED, parent_instance_id, "parent_inactive")
        return False
    if not parent_has_child_objects(parent.monitor_object_id):
        return False
    if started_at is None:
        started_at = int(timezone.now().timestamp())
    interval = normalize_collect_interval(parent.interval)
    task_id = child_discovery_task_id(parent.id)
    try:
        current_app.control.revoke(task_id, terminate=False)
        _discovery_task().apply_async(
            kwargs={
                "parent_instance_id": parent.id,
                "started_at": started_at,
            },
            countdown=max(0, int(countdown or 0)),
            task_id=task_id,
        )
    except Exception as exc:
        logger.error(
            LOG_FAILED,
            parent.id,
            "enqueue",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return False
    logger.info(LOG_SCHEDULED, parent.id, max(0, int(countdown or 0)), interval)
    return True


def cancel_child_instance_discovery(parent_instance_id):
    if parent_instance_id in (None, ""):
        return False
    task_id = child_discovery_task_id(parent_instance_id)
    try:
        current_app.control.revoke(task_id, terminate=False)
    except Exception as exc:
        logger.warning(
            LOG_FAILED,
            parent_instance_id,
            "cancel",
            type(exc).__name__,
        )
        return False
    logger.info(LOG_CANCELLED, parent_instance_id)
    return True


def schedule_child_instance_discovery_on_commit(parent_instance_id):
    if parent_instance_id in (None, ""):
        return
    transaction.on_commit(lambda: enqueue_child_instance_discovery(parent_instance_id))


def copy_parent_organizations(parent_instance_id, child_instance_ids):
    if not parent_instance_id or not child_instance_ids:
        return 0
    organizations = list(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=parent_instance_id).values_list(
            "organization",
            flat=True,
        )
    )
    if not organizations:
        return 0
    relations = [
        MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=organization)
        for instance_id in child_instance_ids
        for organization in organizations
    ]
    MonitorInstanceOrganization.objects.bulk_create(relations, ignore_conflicts=True)
    return len(relations)


def _parse_started_at(started_at):
    if started_at is None or started_at == "":
        return int(timezone.now().timestamp())
    if isinstance(started_at, datetime):
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=datetime_timezone.utc)
        return int(started_at.timestamp())
    try:
        return int(started_at)
    except (TypeError, ValueError):
        return int(timezone.now().timestamp())


def run_child_instance_discovery(parent_instance_id, started_at=None):
    """执行一次按父实例收窄的子对象投影，并按预热/采集间隔续约。"""
    from apps.monitor.tasks.services.sync_instance import SyncInstance

    logger.info(LOG_STARTED, parent_instance_id)
    parent = (
        MonitorInstance.objects.filter(id=parent_instance_id, is_deleted=False, is_active=True)
        .select_related("monitor_object")
        .first()
    )
    if parent is None:
        logger.info(LOG_SKIPPED, parent_instance_id, "parent_inactive")
        return {"added": 0, "restored": 0, "rescheduled": False}
    if not parent_has_child_objects(parent.monitor_object_id):
        logger.info(LOG_SKIPPED, parent_instance_id, "no_child_objects")
        return {"added": 0, "restored": 0, "rescheduled": False}

    try:
        stats = SyncInstance(parent_instance_id=parent.id).run() or {}
    except Exception as exc:
        logger.error(
            LOG_FAILED,
            parent.id,
            "sync",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        raise

    added = int(stats.get("added") or 0)
    restored = int(stats.get("restored") or 0)
    logger.info(LOG_COMPLETED, parent.id, added, restored)

    started_ts = _parse_started_at(started_at)
    age_seconds = max(0, int(timezone.now().timestamp()) - started_ts)
    countdown = next_child_discovery_countdown(age_seconds, parent.interval)
    if countdown is None:
        logger.info(LOG_STOPPED, parent.id, "warmup_complete")
        return {"added": added, "restored": restored, "rescheduled": False}

    enqueue_child_instance_discovery(parent.id, started_at=started_ts, countdown=countdown)
    return {"added": added, "restored": restored, "rescheduled": True, "countdown": countdown}
