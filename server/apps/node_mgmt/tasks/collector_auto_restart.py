from collections import defaultdict
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.core.logger import node_mgmt_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.models import Collector, Node
from apps.node_mgmt.models.action import CollectorActionTaskNode

FAILED_STATUS = 2
STOPPED_STATUSES = frozenset({3, 4})
IN_FLIGHT_STATUSES = ("waiting", "running")
RESTART_ACTION = "restart"
SYSTEM_CREATED_BY = "system"
HEARTBEAT_ACTIVE_WINDOW = timedelta(minutes=1)
SKIP_STOPPED = "stopped"
SKIP_EMPTY_BEATS = "empty_beats"
SKIP_OFFLINE = "offline"
SKIP_IN_FLIGHT = "in_flight"
EMPTY_BEATS_NAMES = frozenset(CollectorConstants.IGNORE_ERROR_COLLECTORS)

COMPLETED_LOG = (
    "event=collector_auto_restart_completed scanned_nodes=%s hit_count=%s dispatched_tasks=%s "
    "skip_stopped=%s skip_empty_beats=%s skip_offline=%s skip_in_flight=%s"
)
SKIPPED_LOG = "event=collector_auto_restart_skipped node_id=%s collector_id=%s reason=%s"
DISPATCHED_LOG = "event=collector_auto_restart_dispatched collector_id=%s node_count=%s task_id=%s"
FAILED_LOG = "event=collector_auto_restart_failed collector_id=%s failed_stage=%s error_type=%s"


def _coerce_status(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _verbose_message(collector_item):
    verbose_message = collector_item.get("verbose_message") or ""
    if isinstance(verbose_message, str):
        return verbose_message
    return ""


def _is_empty_beats_config(collector_name, verbose_message):
    if collector_name not in EMPTY_BEATS_NAMES:
        return False
    return any(message in verbose_message for message in CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES)


def _iter_collector_items(status):
    if not isinstance(status, dict):
        return []
    collectors = status.get("collectors")
    if not isinstance(collectors, list):
        return []
    return collectors


def _load_collector_names():
    return dict(Collector.objects.values_list("id", "name"))


def _in_flight_restart_pairs(pairs):
    if not pairs:
        return set()
    node_ids = {node_id for node_id, _collector_id in pairs}
    collector_ids = {collector_id for _node_id, collector_id in pairs}
    rows = CollectorActionTaskNode.objects.filter(
        node_id__in=node_ids,
        task__collector_id__in=collector_ids,
        task__action=RESTART_ACTION,
        status__in=IN_FLIGHT_STATUSES,
    ).values_list("node_id", "task__collector_id")
    return set(rows)


def _collect_restart_candidates():
    collector_names = _load_collector_names()
    heartbeat_since = timezone.now() - HEARTBEAT_ACTIVE_WINDOW
    scanned_nodes = 0
    skip_counts = {
        SKIP_STOPPED: 0,
        SKIP_EMPTY_BEATS: 0,
        SKIP_OFFLINE: 0,
        SKIP_IN_FLIGHT: 0,
    }
    potential_hits = []

    for node in Node.objects.order_by("id").only("id", "status", "updated_at").iterator(chunk_size=200):
        online = node.updated_at is not None and node.updated_at >= heartbeat_since
        if online:
            scanned_nodes += 1

        for collector_item in _iter_collector_items(node.status):
            collector_id = collector_item.get("collector_id")
            if not collector_id:
                continue
            status = _coerce_status(collector_item.get("status"))
            if status in STOPPED_STATUSES:
                skip_counts[SKIP_STOPPED] += 1
                logger.debug(SKIPPED_LOG, safe_log_value(node.id), safe_log_value(collector_id), SKIP_STOPPED)
                continue
            if status != FAILED_STATUS:
                continue
            if not online:
                skip_counts[SKIP_OFFLINE] += 1
                logger.debug(SKIPPED_LOG, safe_log_value(node.id), safe_log_value(collector_id), SKIP_OFFLINE)
                continue
            collector_name = collector_names.get(collector_id, "")
            if _is_empty_beats_config(collector_name, _verbose_message(collector_item)):
                skip_counts[SKIP_EMPTY_BEATS] += 1
                logger.debug(SKIPPED_LOG, safe_log_value(node.id), safe_log_value(collector_id), SKIP_EMPTY_BEATS)
                continue
            potential_hits.append((node.id, collector_id))

    in_flight = _in_flight_restart_pairs(potential_hits)
    hits = []
    for node_id, collector_id in potential_hits:
        if (node_id, collector_id) in in_flight:
            skip_counts[SKIP_IN_FLIGHT] += 1
            logger.debug(SKIPPED_LOG, safe_log_value(node_id), safe_log_value(collector_id), SKIP_IN_FLIGHT)
            continue
        hits.append((node_id, collector_id))
    return scanned_nodes, hits, skip_counts


def _group_hits_by_collector(hits):
    grouped = defaultdict(list)
    seen = set()
    for node_id, collector_id in hits:
        pair = (node_id, collector_id)
        if pair in seen:
            continue
        seen.add(pair)
        grouped[collector_id].append(node_id)
    return grouped


def _dispatch_restarts(grouped):
    from apps.node_mgmt.services.node import NodeService

    dispatched_tasks = 0
    for collector_id, node_ids in grouped.items():
        try:
            task_id = NodeService.batch_operate_node_collector(
                node_ids,
                collector_id,
                RESTART_ACTION,
                created_by=SYSTEM_CREATED_BY,
            )
        except Exception as exc:
            logger.error(
                FAILED_LOG,
                safe_log_value(collector_id),
                "dispatch",
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            continue
        dispatched_tasks += 1
        logger.debug(DISPATCHED_LOG, safe_log_value(collector_id), len(node_ids), task_id)
    return dispatched_tasks


@shared_task
def restart_failed_collectors():
    """扫描在线节点上失败的托管采集器，按 collector_id 批量下发 restart。"""
    try:
        scanned_nodes, hits, skip_counts = _collect_restart_candidates()
    except Exception as exc:
        logger.error(
            FAILED_LOG,
            "-",
            "scan",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        raise

    dispatched_tasks = _dispatch_restarts(_group_hits_by_collector(hits))
    logger.info(
        COMPLETED_LOG,
        scanned_nodes,
        len(hits),
        dispatched_tasks,
        skip_counts[SKIP_STOPPED],
        skip_counts[SKIP_EMPTY_BEATS],
        skip_counts[SKIP_OFFLINE],
        skip_counts[SKIP_IN_FLIGHT],
    )
    return {
        "scanned_nodes": scanned_nodes,
        "hit_count": len(hits),
        "dispatched_tasks": dispatched_tasks,
        "skip_stopped": skip_counts[SKIP_STOPPED],
        "skip_empty_beats": skip_counts[SKIP_EMPTY_BEATS],
        "skip_offline": skip_counts[SKIP_OFFLINE],
        "skip_in_flight": skip_counts[SKIP_IN_FLIGHT],
    }
