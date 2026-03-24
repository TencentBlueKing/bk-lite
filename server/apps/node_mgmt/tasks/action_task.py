from celery import shared_task
from django.db.models import Count, Q

from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.utils.step_tracker import (
    append_step,
    now_iso,
    update_last_running_step,
    update_step_by_action,
)


RUNNING_STATUS = 0
FAILED_STATUS = 2
STOPPED_STATUS = {3, 4}
ACTION_TASK_TIMEOUT_SECONDS = 300


def _add_step(task_node, action, status, message, details=None):
    result = task_node.result or {}
    append_step(result, action, status, message, timestamp=now_iso(), details=details)
    task_node.result = result


def _update_step_by_action(task_node, action, status, message, details=None):
    result = task_node.result or {}
    updated = update_step_by_action(
        result,
        action,
        status,
        message,
        details=details,
        timestamp=now_iso(),
    )
    task_node.result = result
    return updated


def _update_last_running_step(task_node, status, message, details=None):
    result = task_node.result or {}
    update_last_running_step(
        result,
        status,
        message,
        details=details,
        timestamp=now_iso(),
    )
    task_node.result = result


def _save_node_result(task_node, node_status, overall_status, final_message):
    result = task_node.result or {}
    result["overall_status"] = overall_status
    result["final_message"] = final_message
    task_node.status = node_status
    task_node.result = result
    task_node.save(update_fields=["status", "result"])


def _is_expected_status(action, collector_status):
    if collector_status == FAILED_STATUS:
        return "error"

    if action in ["start", "restart"] and collector_status == RUNNING_STATUS:
        return "success"

    if action == "stop" and collector_status in STOPPED_STATUS:
        return "success"

    return "running"


def _extract_collector_message(collector_item):
    if not isinstance(collector_item, dict):
        return ""

    message = collector_item.get("message")
    verbose_message = collector_item.get("verbose_message")

    message_text = ""
    if isinstance(message, dict):
        message_text = (
            message.get("final_message")
            or message.get("message")
            or message.get("detail")
            or ""
        )
    elif isinstance(message, str):
        message_text = message

    if message_text:
        return message_text

    if isinstance(verbose_message, str):
        return verbose_message

    return ""


def _reconcile_collector_action_tasks(task_ids):
    if not task_ids:
        return

    stats = (
        CollectorActionTaskNode.objects.filter(task_id__in=task_ids)
        .values("task_id")
        .annotate(
            success_count=Count("id", filter=Q(status="success")),
            error_count=Count("id", filter=Q(status="error")),
            pending_count=Count("id", filter=Q(status__in=["waiting", "running"])),
        )
    )

    running_ids = []
    finished_ids = []
    success_count_map = {}
    error_count_map = {}

    for item in stats:
        task_id = item["task_id"]
        success_count_map[task_id] = item["success_count"]
        error_count_map[task_id] = item["error_count"]
        if item["pending_count"]:
            running_ids.append(task_id)
        else:
            finished_ids.append(task_id)

    if running_ids:
        CollectorActionTask.objects.filter(id__in=running_ids).update(status="running")
    if finished_ids:
        CollectorActionTask.objects.filter(id__in=finished_ids).update(
            status="finished"
        )

    for task_id in task_ids:
        CollectorActionTask.objects.filter(id=task_id).update(
            success_count=success_count_map.get(task_id, 0),
            error_count=error_count_map.get(task_id, 0),
        )


@shared_task
def converge_collector_action_task_for_node(node_id):
    node = Node.objects.filter(id=node_id).first()
    if not node:
        return

    node_status = node.status or {}
    collectors = node_status.get("collectors", [])
    if not isinstance(collectors, list) or not collectors:
        return

    collector_status_map = {}
    for collector_item in collectors:
        collector_id = collector_item.get("collector_id")
        if collector_id is None:
            continue
        collector_status_map[collector_id] = collector_item

    running_task_nodes = CollectorActionTaskNode.objects.filter(
        node_id=node_id,
        status="running",
    ).select_related("task")

    affected_task_ids = set()

    for task_node in running_task_nodes:
        task_obj = task_node.task
        collector_item = collector_status_map.get(task_obj.collector_id)
        if not collector_item:
            continue

        collector_status = collector_item.get("status")
        if collector_status is None:
            continue

        collector_message = _extract_collector_message(collector_item)

        expected_node_status = _is_expected_status(task_obj.action, collector_status)
        if expected_node_status in ["success", "error"]:
            step_message = (
                "Collector command execution finished"
                if expected_node_status == "success"
                else (collector_message or "Collector action failed")
            )
            final_message = (
                "Collector action completed"
                if expected_node_status == "success"
                else (collector_message or "Collector action failed")
            )
            _update_last_running_step(
                task_node,
                expected_node_status,
                step_message,
                details={
                    "collector_status": collector_status,
                    "operation": task_obj.action,
                },
            )
            _save_node_result(
                task_node,
                expected_node_status,
                expected_node_status,
                final_message,
            )
            affected_task_ids.add(task_obj.id)

    _reconcile_collector_action_tasks(affected_task_ids)


@shared_task
def timeout_collector_action_task(task_id):
    task_obj = CollectorActionTask.objects.filter(id=task_id).first()
    if not task_obj:
        return

    if task_obj.status not in ["waiting", "running"]:
        return

    pending_nodes = CollectorActionTaskNode.objects.filter(
        task_id=task_id,
        status__in=["waiting", "running"],
    )

    for task_node in pending_nodes:
        _update_last_running_step(
            task_node,
            "timeout",
            "Collector command execution timeout",
            details={"timeout": True},
        )
        _add_step(
            task_node,
            "callback_or_timeout",
            "timeout",
            "Action task timeout",
            details={"timeout": True},
        )
        _save_node_result(
            task_node,
            "error",
            "timeout",
            "Collector action timeout",
        )

    _reconcile_collector_action_tasks({task_id})
