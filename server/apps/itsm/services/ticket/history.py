"""使用任务实例和操作记录还原流转，不把技术动作名作为步骤名。"""
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
}


def ticket_history(ticket, tasks, design):
    task_map = {task.id: task for task in tasks}
    nodes = {node.get("id"): node for node in design.get("nodes", [])}
    rows = []
    for log in ticket.logs.all():
        task = task_map.get(log.task_id)
        label = ACTION_LABELS.get(log.action, "流程处理")
        node_id = (
            task.node_id
            if task
            else (next((key for key, node in nodes.items() if node.get("type") == "start"), "start") if log.action == "create" else "")
        )
        rows.append(
            {
                "id": f"log-{log.id}",
                "node_id": node_id,
                "name": (task.node_name or nodes.get(node_id, {}).get("name") or node_id) if task else label,
                "action_label": label,
                "action": log.action,
                "operator": log.operator,
                "state": "done",
                "started_at": task.created_at.isoformat() if task else log.created_at.isoformat(),
                "finished_at": log.created_at.isoformat(),
                "message": log.message if log.message != log.action else "",
            }
        )
    for execution in ticket.auto_executions.all():
        node_id = execution.detail.get("node_id", "")
        rows.append(
            {
                "id": f"auto-{execution.id}",
                "node_id": node_id,
                "name": nodes.get(node_id, {}).get("name") or "自动处理",
                "action_label": "自动处理",
                "operator": "系统",
                "state": "done" if execution.status == "done" else "current",
                "started_at": execution.created_at.isoformat(),
                "finished_at": execution.updated_at.isoformat() if execution.status == "done" else "",
                "message": "",
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


def node_progress(node, history):
    rows = [row for row in history if row["node_id"] == node["id"]]
    current = [row for row in rows if row["state"] == "current"]
    selected = current or rows[-1:]
    outcome = node["state"]
    if outcome == "done":
        action = selected[-1].get("action") if selected else None
        outcome = {"approve": "accepted", "reject": "rejected"}.get(action, "passed")
    return {
        **node,
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
