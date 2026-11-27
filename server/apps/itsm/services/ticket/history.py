"""使用任务实例和操作记录还原流转，不把技术动作名作为步骤名。"""

from apps.itsm.services.ticket.actions import SIDE_OPINION_ACTIONS, TASK_ACTIONS
from apps.job_mgmt.constants import ExecutionStatus

JOB_STATUSES = frozenset(status for status, _ in ExecutionStatus.CHOICES)
OPINION_ACTIONS = TASK_ACTIONS | SIDE_OPINION_ACTIONS | {"resume", "auto_reconcile"}

ACTION_LABELS = {
    "create": "发起工单",
    "submit": "提交",
    "approve": "同意",
    "reject": "驳回",
    "claim": "认领",
    "save": "保存",
    "transfer": "转交",
    "return": "回退",
    "withdraw": "撤回",
    "suspend": "挂起",
    "resume": "恢复",
    "close": "关闭",
    "terminate": "终止",
    "reopen": "重新打开",
    "urge": "催办",
    "respond": "响应",
    "survey_ready": "邀请评价",
    "auto": "自动处理",
    "auto_reconcile": "人工核对",
    "auto_retry": "请求重试",
}


def job_execution_progress(delivery):
    if not delivery:
        return {}
    records = [
        {
            "row": record["row"],
            "job_id": record["job_id"],
            **({"status": record["status"]} if record.get("status") in JOB_STATUSES else {}),
        }
        for record in delivery.get("rows", [])
        if record.get("job_id")
    ]
    progress = {
        "mode": delivery.get("mode", "each"),
        "dispatch_mode": delivery.get("dispatch_mode", "batch" if delivery.get("batch_size") else "parallel"),
        "total": delivery.get("total", len(records)),
    }
    if delivery.get("batch_size"):
        progress["batch_size"] = delivery["batch_size"]
    return {"job_progress": progress, "job_records": records}


def ticket_history(ticket, tasks, design):
    task_map = {task.id: task for task in tasks}
    nodes = {node.get("id"): node for node in design.get("nodes", [])}
    rows = []
    for log in ticket.logs.all():
        task = task_map.get(log.task_id)
        label = ACTION_LABELS.get(log.action, "流程处理")
        detail = log.detail or {}
        destination = detail.get("return_node_name") if log.action == "return" else None
        opinion = detail.get("opinion") if log.operator != "system" and log.action in OPINION_ACTIONS else None
        if destination:
            label = f"回退至 {destination}"
        node_id = (
            task.node_id
            if task
            else (
                next((key for key, node in nodes.items() if node.get("type") == "start"), "start")
                if log.action == "create"
                else detail.get("node_id", "")
            )
        )
        rows.append(
            {
                "id": f"log-{log.id}",
                "node_id": node_id,
                "name": (task.node_name or nodes.get(node_id, {}).get("name") or node_id) if task else nodes.get(node_id, {}).get("name") or label,
                "action_label": label,
                "action": log.action,
                "operator": log.operator,
                "state": "done",
                "started_at": task.created_at.isoformat() if task else log.created_at.isoformat(),
                "finished_at": log.created_at.isoformat(),
                "message": log.message if log.message != log.action else "",
                **({"opinion": opinion} if isinstance(opinion, str) and opinion.strip() else {}),
            }
        )
    for execution in ticket.auto_executions.all():
        node_id = execution.detail.get("node_id", "")
        failed = execution.status in {"unknown", "failed"} or (execution.status == "executed" and bool(execution.detail.get("reason")))
        queued = execution.status == "queued" or execution.detail.get("retry_requested")
        rows.append(
            {
                "id": f"auto-{execution.id}",
                "node_id": node_id,
                "name": nodes.get(node_id, {}).get("name") or "自动处理",
                "action_label": "待核对" if execution.status == "unknown" else "等待重试" if queued else "自动节点失败" if failed else "自动处理",
                "action": "auto",
                "operator": "系统",
                "state": "done" if execution.status == "done" else "failed" if failed and not queued else "current",
                "started_at": execution.created_at.isoformat(),
                "finished_at": execution.updated_at.isoformat() if execution.status == "done" or failed else "",
                "message": execution.detail.get("reason") or ("执行结果未确认，请先核对外部系统" if failed else ""),
                "execution_id": execution.id,
                **job_execution_progress(execution.detail.get("job_template") or {}),
            }
        )
    rows.sort(key=lambda row: row["finished_at"] or row["started_at"])
    for task in tasks:
        if task.status in {"pending", "claimed"}:
            rows.append(
                {
                    "id": f"task-{task.id}",
                    "node_id": task.node_id,
                    "name": task.node_name or nodes.get(task.node_id, {}).get("name") or task.node_id,
                    "action_label": "待处理",
                    "operator": task.assignee,
                    "state": "current",
                    "started_at": task.created_at.isoformat(),
                    "finished_at": "",
                    "message": "",
                }
            )
    return rows


def index_history_by_node(history):
    indexed = {}
    for row in history:
        indexed.setdefault(row["node_id"], []).append(row)
    return indexed


def node_progress(node, history, auto=None):
    rows = history.get(node["id"], []) if isinstance(history, dict) else [row for row in history if row["node_id"] == node["id"]]
    current = [row for row in rows if row["state"] in {"current", "failed"}]
    selected = current or rows[-1:]
    outcome = node["state"]
    if outcome == "done":
        action = selected[-1].get("action") if selected else None
        outcome = {"approve": "accepted", "reject": "rejected"}.get(action, "passed")
    job = next((row for row in reversed(rows) if "job_progress" in row), None)
    job_data = {}
    if job:
        job_data = {"job_progress": job["job_progress"], "job_records": job["job_records"]}
    elif auto and auto.get("kind") == "job_template":
        mode = auto.get("mode") or ("each" if auto.get("table_key") else "once")
        job_data = {
            "job_progress": {
                "mode": mode,
                "dispatch_mode": auto.get("dispatch_mode", "batch" if auto.get("batch_size") else "parallel"),
                **({"batch_size": auto["batch_size"]} if auto.get("batch_size") else {}),
            }
        }
    return {
        **node,
        **job_data,
        "outcome": outcome,
        "assignees": list(dict.fromkeys(row["operator"] for row in selected if row["operator"])),
        "started_at": selected[0]["started_at"] if selected else "",
        "finished_at": selected[-1]["finished_at"] if selected else "",
    }


def current_round_start(ticket, tasks, design):
    """流程图仅展示本次重新打开后的进度，历史日志仍保留完整记录。"""
    from django.utils.dateparse import parse_datetime

    reopened = [log for log in ticket.logs.all() if log.action == "reopen"]
    if not reopened:
        return None
    latest = max(reopened, key=lambda log: (log.created_at, log.id))
    recorded = (latest.detail or {}).get("round_started_at")
    if recorded:
        return parse_datetime(recorded)
    # 已存在的重开记录没有轮次时间：取重开时创建的提单任务作为边界。
    submit_ids = {node.get("id") for node in design.get("nodes", []) if node.get("type") == "submit"}
    candidates = [task.created_at for task in tasks if task.node_id in submit_ids and task.created_at <= latest.created_at]
    return max(candidates) if candidates else latest.created_at
