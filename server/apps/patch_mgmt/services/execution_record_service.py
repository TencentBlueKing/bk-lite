"""执行记录聚合服务。

公开执行记录以用户发起的根任务为单位；安装、重启、验证子任务只是步骤尝试，
不会各自占据一行。风险项摘要不携带日志，只有选中详情才返回对应主机的完整日志。
"""

from collections import defaultdict

from apps.patch_mgmt.constants import GovernanceTaskType
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, HostComplianceSnapshot


STATUS_META = {
    "waiting": ("等待中", "default"),
    "running": ("执行中", "processing"),
    "pending_reboot": ("待重启", "warning"),
    "completed": ("已完成", "success"),
    "failed": ("失败", "error"),
    "partial_success": ("部分失败", "warning"),
    "partial_cancelled": ("部分取消", "warning"),
    "cancelled": ("已取消", "default"),
    "skipped": ("已跳过", "default"),
    "unknown": ("未知", "warning"),
    "unmet": ("未满足", "error"),
}

STEP_NAMES = {
    GovernanceTaskType.INSTALL: "安装补丁",
    GovernanceTaskType.REBOOT: "重启主机",
    GovernanceTaskType.VERIFY: "验证结果",
}


def _task_chain(root: GovernanceTask) -> list[GovernanceTask]:
    """按创建顺序返回根任务及所有层级的内部子任务。"""
    cached = getattr(root, "_execution_record_chain", None)
    if cached is not None:
        return cached

    result = [root]
    if root.task_type == GovernanceTaskType.INSTALL:
        linked_reboots = [
            task
            for task in GovernanceTask.objects.filter(
                parent_task__isnull=True,
                task_type=GovernanceTaskType.REBOOT,
            ).order_by("created_at", "id")
            if any(
                int(item.get("source_task_id") or 0) == root.id
                for item in (task.risk_snapshot or [])
            )
        ]
        result.extend(linked_reboots)
    frontier = [task.id for task in result]
    seen = set(frontier)
    while frontier:
        children = list(
            GovernanceTask.objects.filter(parent_task_id__in=frontier).order_by("created_at", "id")
        )
        children = [task for task in children if task.id not in seen]
        result.extend(children)
        frontier = [task.id for task in children]
        seen.update(frontier)
    root._execution_record_chain = result
    return result


def _chain_hosts(root: GovernanceTask) -> list[GovernanceTaskHost]:
    """一次读取整条链的主机尝试，避免风险项数量导致 N+1 查询。"""
    cached = getattr(root, "_execution_record_hosts", None)
    if cached is not None:
        return cached
    chain = _task_chain(root)
    hosts = list(
        GovernanceTaskHost.objects.filter(task_id__in=[task.id for task in chain])
        .select_related("task")
        .order_by("created_at", "id")
    )
    root._execution_record_hosts = hosts
    return hosts


def _compliance_by_pair(root: GovernanceTask) -> dict[tuple[int, int], bool]:
    """一次读取快照内所有主机补丁的最终合规结果。"""
    cached = getattr(root, "_execution_record_compliance", None)
    if cached is not None:
        return cached
    items = _risk_snapshot(root)
    target_ids = {int(item["host_id"]) for item in items}
    patch_ids = {int(item.get("patch_id") or 0) for item in items if item.get("patch_id")}
    values = HostComplianceSnapshot.objects.filter(
        binding__target_id__in=target_ids,
        requirement__patch_id__in=patch_ids,
    ).values_list("binding__target_id", "requirement__patch_id", "satisfied")
    result = {
        (int(target_id), int(patch_id)): satisfied
        for target_id, patch_id, satisfied in values
    }
    root._execution_record_compliance = result
    return result


def _step_status(task_type: str, stage: str) -> str:
    if stage == "cancelled":
        return "cancelled"
    if stage in {"failed", "reboot_failed", "pending_confirmation"}:
        return "failed"
    if stage in {"installing", "rebooting", "scanning", "reconciling"}:
        return "running"
    if stage == "waiting":
        return "waiting"
    if stage == "pending_reboot":
        return "running" if task_type == GovernanceTaskType.REBOOT else "completed"
    if stage in {"completed", "reboot_scheduled"}:
        return "completed"
    return "unknown"


def _attempt(task: GovernanceTask, host: GovernanceTaskHost, include_log: bool) -> dict:
    status = _step_status(task.task_type, host.stage)
    display, color = STATUS_META[status]
    data = {
        "id": host.id,
        "task_id": task.id,
        "status": status,
        "status_display": display,
        "status_color": color,
        "started_at": host.stage_started_at or host.started_at,
        "finished_at": task.finished_at if status in {"completed", "failed", "cancelled"} else None,
        "reason": host.reason or host.timeout_reason or "",
        "suggestion": host.suggestion or "",
        "exit_code": host.exit_code,
    }
    if include_log:
        data["log"] = host.log or ""
    return data


def _risk_snapshot(root: GovernanceTask) -> list[dict]:
    """返回创建时快照；重启任务兼容按主机生成占位项。"""
    if root.risk_snapshot:
        return list(root.risk_snapshot)
    return [
        {
            "id": f"{target_id}:0:0",
            "host_id": target_id,
            "host_name": host.target_name if host else str(target_id),
            "host_ip": host.target_ip if host else "",
            "patch_id": 0,
            "patch_name": "重启",
            "baseline_id": 0,
            "baseline_name": "",
        }
        for target_id in (root.target_list or [])
        for host in [root.host_results.filter(target_id=target_id).first()]
    ]


def _group_attempts(root: GovernanceTask, target_id: int, include_log: bool) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    chain = _task_chain(root)
    hosts = {
        (host.task_id, host.target_id): host
        for host in _chain_hosts(root)
        if host.target_id == target_id
    }
    for task in chain:
        if task.task_type not in STEP_NAMES:
            continue
        host = hosts.get((task.id, target_id))
        if host:
            grouped[task.task_type].append(_attempt(task, host, include_log))
    return grouped


def _item_status(root: GovernanceTask, item: dict) -> str:
    target_id = int(item["host_id"])
    attempts = _group_attempts(root, target_id, include_log=False)
    verify = attempts.get(GovernanceTaskType.VERIFY, [])
    reboot = attempts.get(GovernanceTaskType.REBOOT, [])
    install = attempts.get(GovernanceTaskType.INSTALL, [])
    for current_attempts in (install, reboot, verify):
        if current_attempts and current_attempts[-1]["status"] in {"running", "waiting"}:
            return current_attempts[-1]["status"]
    if install:
        tasks_by_id = {task.id: task for task in _task_chain(root)}
        latest_install = max(
            install,
            key=lambda attempt: (
                tasks_by_id[attempt["task_id"]].created_at,
                attempt["task_id"],
            ),
        )
        latest_verify = max(
            verify,
            key=lambda attempt: (
                tasks_by_id[attempt["task_id"]].created_at,
                attempt["task_id"],
            ),
        ) if verify else None
        latest_install_host = next(
            (
                host
                for host in _chain_hosts(root)
                if host.task_id == latest_install["task_id"] and host.target_id == target_id
            ),
            None,
        )
        install_is_newer = latest_verify is None or (
            tasks_by_id[latest_install["task_id"]].created_at,
            latest_install["task_id"],
        ) > (
            tasks_by_id[latest_verify["task_id"]].created_at,
            latest_verify["task_id"],
        )
        if latest_install_host and latest_install_host.stage == "pending_reboot" and install_is_newer:
            return "pending_reboot"
    for current_attempts in (install, reboot, verify):
        if current_attempts and current_attempts[-1]["status"] == "failed":
            return "failed"
    if verify:
        verify_status = verify[-1]["status"]
        if verify_status == "completed" and item.get("patch_id"):
            satisfied = _compliance_by_pair(root).get(
                (target_id, int(item["patch_id"]))
            )
            if satisfied is False:
                return "unmet"
        return verify_status
    if reboot:
        return reboot[-1]["status"]
    if install:
        return install[-1]["status"]
    return "waiting"


def build_risk_item_summaries(root: GovernanceTask) -> list[dict]:
    cached = getattr(root, "_execution_record_risk_summaries", None)
    if cached is not None:
        return cached
    result = []
    for item in _risk_snapshot(root):
        status = _item_status(root, item)
        display, color = STATUS_META.get(status, STATUS_META["unknown"])
        result.append(
            {
                "id": str(item["id"]),
                "display_name": f'{item.get("host_name") or item["host_id"]}-{item.get("patch_name") or "补丁"}',
                "host_id": int(item["host_id"]),
                "patch_id": int(item.get("patch_id") or 0),
                "status": status,
                "status_display": display,
                "status_color": color,
            }
        )
    root._execution_record_risk_summaries = result
    return result


def build_record_status(root: GovernanceTask) -> tuple[str, str, str]:
    """按整条步骤链聚合可见执行记录状态。"""
    statuses = [item["status"] for item in build_risk_item_summaries(root)]
    if not statuses:
        fallback = {
            "pending": "waiting",
            "running": "running",
            "completed": "completed",
            "partial_success": "partial_success",
            "partial_cancelled": "partial_cancelled",
            "failed": "failed",
            "cancelled": "cancelled",
        }.get(root.status, "unknown")
        display, color = STATUS_META[fallback]
        return fallback, display, color
    values = {"failed" if value == "unmet" else value for value in statuses}
    if "running" in values or ("waiting" in values and len(values) > 1):
        status = "running"
    elif values == {"waiting"}:
        status = "waiting"
    elif "pending_reboot" in values:
        status = "pending_reboot"
    elif values == {"completed"}:
        status = "completed"
    elif values == {"cancelled"}:
        status = "cancelled"
    elif "cancelled" in values:
        status = "partial_cancelled"
    elif "failed" in values and "completed" in values:
        status = "partial_success"
    elif "failed" in values:
        status = "failed"
    else:
        status = "unknown"
    display, color = STATUS_META[status]
    return status, display, color


def build_risk_item_detail(root: GovernanceTask, risk_item_id: str) -> dict | None:
    item = next((entry for entry in _risk_snapshot(root) if str(entry.get("id")) == str(risk_item_id)), None)
    if item is None:
        return None

    target_id = int(item["host_id"])
    grouped = _group_attempts(root, target_id, include_log=True)
    step_types = (
        [GovernanceTaskType.REBOOT, GovernanceTaskType.VERIFY]
        if root.task_type == GovernanceTaskType.REBOOT
        else [GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT, GovernanceTaskType.VERIFY]
    )
    steps = []
    for task_type in step_types:
        attempts = grouped.get(task_type, [])
        if attempts:
            status = attempts[-1]["status"]
        elif task_type == GovernanceTaskType.REBOOT and grouped.get(GovernanceTaskType.INSTALL):
            install_status = grouped[GovernanceTaskType.INSTALL][-1]["status"]
            status = (
                "skipped"
                if install_status in {"completed", "failed", "cancelled"}
                else "waiting"
            )
        else:
            status = "waiting"
        display, color = STATUS_META[status]
        steps.append(
            {
                "key": task_type,
                "name": STEP_NAMES[task_type],
                "status": status,
                "status_display": display,
                "status_color": color,
                "attempts": attempts,
            }
        )

    status = _item_status(root, item)
    display, color = STATUS_META.get(status, STATUS_META["unknown"])
    return {
        **item,
        "id": str(item["id"]),
        "display_name": f'{item.get("host_name") or target_id}-{item.get("patch_name") or "补丁"}',
        "status": status,
        "status_display": display,
        "status_color": color,
        "steps": steps,
    }
