"""执行记录聚合服务。

一条公开执行记录只聚合该次用户动作及其自动子步骤。后续手动重启、
重试都是新的根记录，只通过 source_record 保留来源，不得回写或并入旧记录。
验证结果从 verify 任务的 result_snapshot 读取，不依赖当前合规快照。
"""

from collections import defaultdict

from apps.patch_mgmt.constants import GovernanceTaskType
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost


STATUS_META = {
    "waiting": ("等待中", "default"),
    "running": ("执行中", "processing"),
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


def filter_execution_record_roots(queryset):
    """只保留可对用户公开的执行记录根任务。"""
    return queryset.filter(
        parent_task__isnull=True,
        task_type__in=(GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT),
    )


def _task_chain(root: GovernanceTask) -> list[GovernanceTask]:
    """返回根动作和其自动子任务。

    parent_task 仅表示同一次动作内的自动步骤；后续用户动作使用
    source_record，因此不再搜索或合并其他根任务。
    """
    cached = getattr(root, "_execution_record_chain", None)
    if cached is not None:
        return cached

    result = [root]
    frontier = [root.id]
    seen = {root.id}
    while frontier:
        children = list(
            GovernanceTask.objects.filter(parent_task_id__in=frontier).order_by(
                "created_at", "id"
            )
        )
        children = [task for task in children if task.id not in seen]
        result.extend(children)
        frontier = [task.id for task in children]
        seen.update(frontier)
    root._execution_record_chain = result
    return result


def _chain_hosts(root: GovernanceTask) -> list[GovernanceTaskHost]:
    cached = getattr(root, "_execution_record_hosts", None)
    if cached is not None:
        return cached
    hosts = list(
        GovernanceTaskHost.objects.filter(
            task_id__in=[task.id for task in _task_chain(root)]
        )
        .select_related("task")
        .order_by("created_at", "id")
    )
    root._execution_record_hosts = hosts
    return hosts


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
        "finished_at": task.finished_at
        if status in {"completed", "failed", "cancelled"}
        else None,
        "reason": host.reason or host.timeout_reason or "",
        "suggestion": host.suggestion or "",
        "exit_code": host.exit_code,
    }
    if include_log:
        data["log"] = host.log or ""
    return data


def _risk_snapshot(root: GovernanceTask) -> list[dict]:
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


def _group_attempts(
    root: GovernanceTask, target_id: int, include_log: bool
) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    hosts = {
        (host.task_id, host.target_id): host
        for host in _chain_hosts(root)
        if host.target_id == target_id
    }
    for task in _task_chain(root):
        if task.task_type not in STEP_NAMES:
            continue
        host = hosts.get((task.id, target_id))
        if host:
            grouped[task.task_type].append(_attempt(task, host, include_log))
    return grouped


def _verification_result(root: GovernanceTask, item: dict) -> dict | None:
    """读取该次执行内最新的验证结果快照。"""
    risk_item_id = str(item.get("id") or "")
    pair = (int(item["host_id"]), int(item.get("patch_id") or 0))
    matched = None
    for task in _task_chain(root):
        if task.task_type != GovernanceTaskType.VERIFY:
            continue
        for result in task.result_snapshot or []:
            result_pair = (
                int(result.get("host_id") or 0),
                int(result.get("patch_id") or 0),
            )
            if str(result.get("risk_item_id") or "") == risk_item_id or result_pair == pair:
                matched = result
    return matched


def _root_host(root: GovernanceTask, target_id: int) -> GovernanceTaskHost | None:
    return next(
        (
            host
            for host in _chain_hosts(root)
            if host.task_id == root.id and host.target_id == target_id
        ),
        None,
    )


def _item_status(root: GovernanceTask, item: dict) -> str:
    target_id = int(item["host_id"])
    attempts = _group_attempts(root, target_id, include_log=False)

    # 后续自动步骤优先于前置步骤展示。
    for task_type in (
        GovernanceTaskType.VERIFY,
        GovernanceTaskType.REBOOT,
        GovernanceTaskType.INSTALL,
    ):
        current = attempts.get(task_type, [])
        if current and current[-1]["status"] in {"running", "waiting"}:
            return current[-1]["status"]

    root_host = _root_host(root, target_id)
    if root_host:
        root_status = _step_status(root.task_type, root_host.stage)
        if root_status in {"failed", "cancelled", "unknown"}:
            return root_status
        if root.auto_reboot and root_host.error_code == "reboot_requirement_unknown":
            return "failed"

    verify = attempts.get(GovernanceTaskType.VERIFY, [])
    if verify:
        if verify[-1]["status"] in {"failed", "cancelled", "unknown"}:
            return verify[-1]["status"]
        result = _verification_result(root, item)
        if result:
            if result.get("status") == "failed" or result.get("satisfied") is None:
                return "failed"
            return "completed" if result.get("satisfied") else "unmet"
        return verify[-1]["status"]

    reboot = attempts.get(GovernanceTaskType.REBOOT, [])
    if reboot and reboot[-1]["status"] in {"failed", "cancelled", "unknown"}:
        return reboot[-1]["status"]

    install = attempts.get(GovernanceTaskType.INSTALL, [])
    if not verify and (install or reboot):
        verify_status, _ = _skipped_step_reason(
            root,
            target_id,
            GovernanceTaskType.VERIFY,
            attempts,
        )
        if verify_status == "waiting":
            # 批量任务中单台主机可能先安装/重启完成，但自动验证要等
            # 根任务收口后才创建。此时详情仍显示“验证等待中”，摘要
            # 也必须保持等待，不能把前置步骤完成误报为整条链路完成。
            return "waiting"

    if install:
        if install[-1]["status"] in {"failed", "cancelled", "unknown"}:
            return install[-1]["status"]
        if (
            root.auto_reboot
            and root_host
            and root_host.error_code == "reboot_requirement_unknown"
        ):
            # 用户要求了自动重启，但系统无法判定重启需求，
            # 本次动作未能按设置完成。
            return "failed"
        return install[-1]["status"]

    if reboot:
        return reboot[-1]["status"]
    return "waiting"


def _item_can_retry(root: GovernanceTask, item: dict, status: str) -> bool:
    if status not in {"failed", "unknown", "unmet"}:
        return False
    risk_item_id = str(item.get("id") or "")
    if GovernanceTask.objects.filter(
        parent_task__isnull=True,
        source_record=root,
        source_risk_item_id=risk_item_id,
    ).exists():
        return False
    if status == "unmet":
        return True
    target_id = int(item["host_id"])
    return any(
        host.target_id == target_id and host.can_retry
        for host in _chain_hosts(root)
    )


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
                "host_name": item.get("host_name") or str(item["host_id"]),
                "host_ip": item.get("host_ip") or "",
                "patch_name": item.get("patch_name") or "",
                "host_id": int(item["host_id"]),
                "patch_id": int(item.get("patch_id") or 0),
                "status": status,
                "status_display": display,
                "status_color": color,
                "can_retry": _item_can_retry(root, item, status),
            }
        )
    root._execution_record_risk_summaries = result
    return result


def build_record_status(root: GovernanceTask) -> tuple[str, str, str]:
    """按本次动作及自动步骤聚合记录状态。"""
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

    values = {
        "failed" if value in {"unmet", "unknown"} else value for value in statuses
    }
    if "running" in values or "waiting" in values:
        status = "running" if values != {"waiting"} else "waiting"
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


def _skipped_step_reason(
    root: GovernanceTask,
    target_id: int,
    task_type: str,
    grouped: dict[str, list[dict]],
) -> tuple[str, str]:
    root_host = _root_host(root, target_id)
    install = grouped.get(GovernanceTaskType.INSTALL, [])
    reboot = grouped.get(GovernanceTaskType.REBOOT, [])

    if task_type == GovernanceTaskType.REBOOT and install:
        install_status = install[-1]["status"]
        if install_status == "failed":
            return "skipped", "安装失败，未执行重启"
        if install_status == "cancelled":
            return "skipped", "安装已取消，未执行重启"
        if root_host and root_host.error_code == "reboot_requirement_unknown":
            return "skipped", "无法判断是否需要重启，未执行自动重启"
        if root_host and root_host.stage == "pending_reboot" and not root.auto_reboot:
            return "skipped", "未设置安装后自动重启"
        if root_host and root_host.stage == "completed":
            return "skipped", "安装后确认无需重启"
        if install_status in {"completed", "failed", "cancelled"}:
            return "skipped", "本次动作未执行重启"

    if task_type == GovernanceTaskType.VERIFY:
        if install and install[-1]["status"] == "failed":
            return "skipped", "安装失败，未执行验证"
        if install and install[-1]["status"] == "cancelled":
            return "skipped", "安装已取消，未执行验证"
        if root_host and root.task_type == GovernanceTaskType.INSTALL:
            if root_host.error_code == "reboot_requirement_unknown":
                return "skipped", "重启需求无法判定，未执行验证"
            if root_host.stage == "pending_reboot" and not root.auto_reboot:
                return "skipped", "未执行重启，本次记录不执行验证"
        if reboot and reboot[-1]["status"] == "failed":
            return "skipped", "重启失败，未执行验证"
        if reboot and reboot[-1]["status"] == "cancelled":
            return "skipped", "重启已取消，未执行验证"

    return "waiting", ""


def _source_record_data(root: GovernanceTask, item: dict) -> dict | None:
    source_id = int(item.get("source_record_id") or root.source_record_id or 0)
    if not source_id:
        return None
    source = GovernanceTask.objects.filter(pk=source_id).only("id", "name").first()
    return {"id": source.id, "name": source.name} if source else None


def build_risk_item_detail(root: GovernanceTask, risk_item_id: str) -> dict | None:
    item = next(
        (
            entry
            for entry in _risk_snapshot(root)
            if str(entry.get("id")) == str(risk_item_id)
        ),
        None,
    )
    if item is None:
        return None

    target_id = int(item["host_id"])
    grouped = _group_attempts(root, target_id, include_log=True)
    step_types = (
        [GovernanceTaskType.REBOOT, GovernanceTaskType.VERIFY]
        if root.task_type == GovernanceTaskType.REBOOT
        else [
            GovernanceTaskType.INSTALL,
            GovernanceTaskType.REBOOT,
            GovernanceTaskType.VERIFY,
        ]
    )
    steps = []
    for task_type in step_types:
        attempts = grouped.get(task_type, [])
        reason = ""
        if attempts:
            status = attempts[-1]["status"]
        else:
            status, reason = _skipped_step_reason(
                root, target_id, task_type, grouped
            )
        display, color = STATUS_META[status]
        steps.append(
            {
                "key": task_type,
                "name": STEP_NAMES[task_type],
                "status": status,
                "status_display": display,
                "status_color": color,
                "reason": reason,
                "attempts": attempts,
            }
        )

    status = _item_status(root, item)
    display, color = STATUS_META.get(status, STATUS_META["unknown"])
    verification = _verification_result(root, item)
    return {
        **item,
        "id": str(item["id"]),
        "display_name": f'{item.get("host_name") or target_id}-{item.get("patch_name") or "补丁"}',
        "host_ip": item.get("host_ip") or "",
        "status": status,
        "status_display": display,
        "status_color": color,
        "can_retry": _item_can_retry(root, item, status),
        "source_record": _source_record_data(root, item),
        "verification_result": verification,
        "steps": steps,
    }
