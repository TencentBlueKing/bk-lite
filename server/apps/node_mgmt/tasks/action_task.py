from celery import shared_task

from apps.node_mgmt.models.action import CollectorActionTask, CollectorActionTaskNode
from apps.node_mgmt.models.sidecar import Node


RUNNING_STATUS = 0
FAILED_STATUS = 2
STOPPED_STATUS = {3, 4}
ACTION_TASK_TIMEOUT_SECONDS = 300


def _is_expected_status(action, collector_status):
    if collector_status == FAILED_STATUS:
        return "error"

    if action in ["start", "restart"] and collector_status == RUNNING_STATUS:
        return "success"

    if action == "stop" and collector_status in STOPPED_STATUS:
        return "success"

    return "running"


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
        collector_status = collector_item.get("status")
        if collector_id is None:
            continue
        collector_status_map[collector_id] = collector_status

    running_task_nodes = CollectorActionTaskNode.objects.filter(
        node_id=node_id,
        status="running",
    ).select_related("task")

    affected_task_ids = set()

    for task_node in running_task_nodes:
        task_obj = task_node.task
        collector_status = collector_status_map.get(task_obj.collector_id)
        if collector_status is None:
            continue

        expected_node_status = _is_expected_status(task_obj.action, collector_status)
        if expected_node_status in ["success", "error"]:
            task_node.status = expected_node_status
            task_node.result = {
                "message": "Status converged by node collector state",
                "collector_status": collector_status,
                "action": task_obj.action,
            }
            task_node.save(update_fields=["status", "result"])
            affected_task_ids.add(task_obj.id)

    for task_id in affected_task_ids:
        task_nodes = CollectorActionTaskNode.objects.filter(task_id=task_id)
        success_count = task_nodes.filter(status="success").count()
        error_count = task_nodes.filter(status="error").count()
        running_or_waiting_exists = task_nodes.filter(
            status__in=["waiting", "running"]
        ).exists()

        task_status = "running" if running_or_waiting_exists else "finished"

        CollectorActionTask.objects.filter(id=task_id).update(
            status=task_status,
            success_count=success_count,
            error_count=error_count,
        )


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
        current_result = task_node.result or {}
        task_node.status = "error"
        task_node.result = {
            **current_result,
            "message": "Action task timeout",
            "timeout": True,
        }
        task_node.save(update_fields=["status", "result"])

    task_nodes = CollectorActionTaskNode.objects.filter(task_id=task_id)
    success_count = task_nodes.filter(status="success").count()
    error_count = task_nodes.filter(status="error").count()

    CollectorActionTask.objects.filter(id=task_id).update(
        status="finished",
        success_count=success_count,
        error_count=error_count,
    )
