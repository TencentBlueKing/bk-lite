"""执行记录聚合服务。

一条公开执行记录只聚合该次用户动作及其自动子步骤。后续手动重启、
重试都是新的根记录，只通过 source_record 保留来源，不得回写或并入旧记录。
验证结果从 verify 任务的 result_snapshot 读取，不依赖当前合规快照。
"""

from collections import defaultdict
from typing import Any

from apps.patch_mgmt.constants import GovernanceTaskType
from apps.patch_mgmt.models import BaselineRequirement, GovernanceTask, GovernanceTaskHost, HostBaselineBinding, HostComplianceSnapshot, Patch
from apps.patch_mgmt.utils.i18n import patch_message

STATUS_COLORS = {
    "waiting": "default",
    "running": "processing",
    "completed": "success",
    "failed": "error",
    "partial_success": "warning",
    "partial_cancelled": "warning",
    "cancelled": "default",
    "skipped": "default",
    "unknown": "warning",
    "unmet": "error",
}

_STATUS_DEFAULTS = {
    "waiting": "Waiting",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "partial_success": "Partially Failed",
    "partial_cancelled": "Partially Cancelled",
    "cancelled": "Cancelled",
    "skipped": "Skipped",
    "unknown": "Unknown",
    "unmet": "Unmet",
}

STEP_TYPES = frozenset(
    {
        GovernanceTaskType.INSTALL,
        GovernanceTaskType.REBOOT,
        GovernanceTaskType.VERIFY,
    }
)

_STEP_NAME_DEFAULTS = {
    GovernanceTaskType.INSTALL: "Install Patches",
    GovernanceTaskType.REBOOT: "Reboot Host",
    GovernanceTaskType.VERIFY: "Verify Result",
}


def _request_locale(request: Any) -> str:
    return getattr(getattr(request, "user", None), "locale", None) or "en"


def _status_meta(request: Any, status: str) -> tuple[str, str]:
    key = status if status in STATUS_COLORS else "unknown"
    display = patch_message(
        request,
        f"status.execution.{key}",
        _STATUS_DEFAULTS[key],
    )
    return display, STATUS_COLORS[key]


def _step_name(request: Any, task_type: str) -> str:
    return patch_message(
        request,
        f"status.execution_step.{task_type}",
        _STEP_NAME_DEFAULTS[task_type],
    )


def _default_patch_label(request: Any) -> str:
    return patch_message(request, "message.default_patch_name", "Patch")


def _reboot_patch_label(request: Any) -> str:
    return patch_message(request, "message.reboot_patch_name", "Reboot")


def filter_execution_record_roots(queryset):
    """只保留可对用户公开的执行记录根任务。"""
    return queryset.filter(
        parent_task__isnull=True,
        task_type__in=(GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT),
    )


def build_host_requirement_projection(target_ids, patch_ids=None) -> dict[int, list[dict]]:
    """按可见主机批量投影基线要求与每条要求的最新合规快照。

    查询次数有上界，不随主机数线性放大。无绑定主机映射为 []。
    安装任务传入 patch_ids 时只保留这些补丁对应的要求。
    """
    unique_ids = list(dict.fromkeys(int(target_id) for target_id in target_ids))
    index = {target_id: [] for target_id in unique_ids}
    if not unique_ids:
        return index

    bindings = list(HostBaselineBinding.objects.filter(target_id__in=unique_ids).select_related("baseline"))
    if not bindings:
        return index

    binding_by_target = {}
    for binding in bindings:
        binding_by_target.setdefault(int(binding.target_id), binding)

    req_qs = BaselineRequirement.objects.filter(baseline_id__in={binding.baseline_id for binding in binding_by_target.values()}).select_related(
        "patch"
    )
    if patch_ids:
        req_qs = req_qs.filter(patch_id__in=patch_ids)

    reqs_by_baseline: dict[int, list] = defaultdict(list)
    for requirement in req_qs:
        reqs_by_baseline[requirement.baseline_id].append(requirement)

    latest_snapshots = {}
    for snapshot in HostComplianceSnapshot.objects.filter(binding_id__in=[binding.id for binding in binding_by_target.values()]).order_by(
        "-evaluated_at"
    ):
        key = (snapshot.binding_id, snapshot.requirement_id)
        if key not in latest_snapshots:
            latest_snapshots[key] = snapshot

    for target_id, binding in binding_by_target.items():
        rows = []
        for requirement in reqs_by_baseline.get(binding.baseline_id, []):
            snapshot = latest_snapshots.get((binding.id, requirement.id))
            rows.append(
                {
                    "baseline_name": binding.baseline.name,
                    "patch_id": requirement.patch_id,
                    "patch_title": requirement.patch.title,
                    "condition": requirement.condition,
                    "satisfied": snapshot.satisfied if snapshot else None,
                    "status": snapshot.status if snapshot else None,
                    "reason": snapshot.reason if snapshot else "",
                    "evidence": snapshot.evidence if snapshot else {},
                }
            )
        index[target_id] = rows
    return index


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
        children = list(GovernanceTask.objects.filter(parent_task_id__in=frontier).order_by("created_at", "id"))
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
    queryset = GovernanceTaskHost.objects.filter(task_id__in=[task.id for task in _task_chain(root)])
    visible_target_ids = getattr(root, "_visible_target_ids", None)
    if visible_target_ids is not None:
        queryset = queryset.filter(target_id__in=visible_target_ids)
    hosts = list(queryset.select_related("task").order_by("created_at", "id"))
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


def _host_stage(host: GovernanceTaskHost) -> str:
    from apps.patch_mgmt.services.governance_convergence import project_host_state

    return project_host_state(host).stage


def _attempt(
    task: GovernanceTask,
    host: GovernanceTaskHost,
    include_log: bool,
    request: Any = None,
) -> dict:
    status = _step_status(task.task_type, _host_stage(host))
    display, color = _status_meta(request, status)
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


def _risk_snapshot(root: GovernanceTask, request: Any = None) -> list[dict]:
    visible_target_ids = getattr(root, "_visible_target_ids", None)
    if root.risk_snapshot:
        snapshot = list(root.risk_snapshot)
        if visible_target_ids is not None:
            snapshot = [item for item in snapshot if int(item.get("host_id") or 0) in visible_target_ids]
        return snapshot
    reboot_label = _reboot_patch_label(request)
    return [
        {
            "id": f"{target_id}:0:0",
            "host_id": target_id,
            "host_name": host.target_name if host else str(target_id),
            "host_ip": host.target_ip if host else "",
            "patch_id": 0,
            "patch_name": reboot_label,
            "baseline_id": 0,
            "baseline_name": "",
        }
        for target_id in (root.target_list or [])
        if visible_target_ids is None or int(target_id) in visible_target_ids
        for host in [root.host_results.filter(target_id=target_id).first()]
    ]


def _group_attempts(
    root: GovernanceTask,
    target_id: int,
    include_log: bool,
    request: Any = None,
) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    hosts = {(host.task_id, host.target_id): host for host in _chain_hosts(root) if host.target_id == target_id}
    for task in _task_chain(root):
        if task.task_type not in STEP_TYPES:
            continue
        host = hosts.get((task.id, target_id))
        if host:
            grouped[task.task_type].append(_attempt(task, host, include_log, request))
    return grouped


def _summary_index(root: GovernanceTask, request: Any = None) -> dict:
    """为一条根记录构建状态/重试判定所需的任务链索引。"""
    locale = _request_locale(request)
    cached = getattr(root, "_execution_record_summary_index", None)
    if cached is not None and getattr(root, "_execution_record_summary_index_locale", None) == locale:
        return cached

    chain = _task_chain(root)
    hosts = _chain_hosts(root)
    snapshot = _risk_snapshot(root, request)
    hosts_by_task: dict[int, list[GovernanceTaskHost]] = defaultdict(list)
    root_host_by_target: dict[int, GovernanceTaskHost] = {}
    retryable_target_ids: set[int] = set()
    for host in hosts:
        hosts_by_task[host.task_id].append(host)
        if host.task_id == root.id and host.target_id not in root_host_by_target:
            root_host_by_target[host.target_id] = host
        if host.can_retry:
            retryable_target_ids.add(host.target_id)

    attempts_by_target: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for task in chain:
        if task.task_type not in STEP_TYPES:
            continue
        for host in hosts_by_task.get(task.id, []):
            attempts_by_target[host.target_id][task.task_type].append(_attempt(task, host, include_log=False, request=request))

    verification_hits: dict[tuple, tuple[int, dict]] = {}
    sequence = 0
    for task in chain:
        if task.task_type != GovernanceTaskType.VERIFY:
            continue
        for result in task.result_snapshot or []:
            sequence += 1
            risk_item_id = str(result.get("risk_item_id") or "")
            pair = (
                int(result.get("host_id") or 0),
                int(result.get("patch_id") or 0),
            )
            if risk_item_id:
                verification_hits[("id", risk_item_id)] = (sequence, result)
            verification_hits[("pair", pair)] = (sequence, result)

    patch_ids = {int(item.get("patch_id") or 0) for item in snapshot if int(item.get("patch_id") or 0)}
    existing_patch_ids = set(Patch.objects.filter(pk__in=patch_ids).values_list("pk", flat=True)) if patch_ids else set()
    risk_ids = [str(item.get("id") or "") for item in snapshot]
    retried_risk_ids = (
        set(
            GovernanceTask.objects.filter(
                parent_task__isnull=True,
                source_record=root,
                source_risk_item_id__in=risk_ids,
            ).values_list("source_risk_item_id", flat=True)
        )
        if risk_ids
        else set()
    )

    index = {
        "attempts_by_target": attempts_by_target,
        "root_host_by_target": root_host_by_target,
        "verification_hits": verification_hits,
        "existing_patch_ids": existing_patch_ids,
        "retried_risk_ids": retried_risk_ids,
        "retryable_target_ids": retryable_target_ids,
    }
    root._execution_record_summary_index = index
    root._execution_record_summary_index_locale = locale
    return index


def _indexed_verification(index: dict, item: dict) -> dict | None:
    hits = index["verification_hits"]
    candidates = []
    risk_item_id = str(item.get("id") or "")
    pair = (int(item["host_id"]), int(item.get("patch_id") or 0))
    if risk_item_id:
        hit = hits.get(("id", risk_item_id))
        if hit is not None:
            candidates.append(hit)
    hit = hits.get(("pair", pair))
    if hit is not None:
        candidates.append(hit)
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry[0])[1]


def _verification_result(root: GovernanceTask, item: dict, request: Any = None) -> dict | None:
    """读取该次执行内最新的验证结果快照。"""
    return _indexed_verification(_summary_index(root, request), item)


def _root_host(root: GovernanceTask, target_id: int, request: Any = None) -> GovernanceTaskHost | None:
    return _summary_index(root, request)["root_host_by_target"].get(target_id)


def _item_status(root: GovernanceTask, item: dict, request: Any = None) -> str:
    index = _summary_index(root, request)
    target_id = int(item["host_id"])
    attempts = index["attempts_by_target"].get(target_id) or {}

    # 后续自动步骤优先于前置步骤展示。
    for task_type in (
        GovernanceTaskType.VERIFY,
        GovernanceTaskType.REBOOT,
        GovernanceTaskType.INSTALL,
    ):
        current = attempts.get(task_type, [])
        if current and current[-1]["status"] in {"running", "waiting"}:
            return current[-1]["status"]

    root_host = index["root_host_by_target"].get(target_id)
    if root_host:
        root_status = _step_status(root.task_type, _host_stage(root_host))
        if root_status in {"failed", "cancelled", "unknown"}:
            return root_status
        if root.auto_reboot and root_host.error_code == "reboot_requirement_unknown":
            return "failed"

    verify = attempts.get(GovernanceTaskType.VERIFY, [])
    if verify:
        if verify[-1]["status"] in {"failed", "cancelled", "unknown"}:
            return verify[-1]["status"]
        result = _indexed_verification(index, item)
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
            request=request,
        )
        if verify_status == "waiting":
            # 批量任务中单台主机可能先安装/重启完成，但自动验证要等
            # 根任务收口后才创建。此时详情仍显示“验证等待中”，摘要
            # 也必须保持等待，不能把前置步骤完成误报为整条链路完成。
            return "waiting"

    if install:
        if install[-1]["status"] in {"failed", "cancelled", "unknown"}:
            return install[-1]["status"]
        if root.auto_reboot and root_host and root_host.error_code == "reboot_requirement_unknown":
            # 用户要求了自动重启，但系统无法判定重启需求，
            # 本次动作未能按设置完成。
            return "failed"
        return install[-1]["status"]

    if reboot:
        return reboot[-1]["status"]
    return "waiting"


def _item_can_retry(
    root: GovernanceTask,
    item: dict,
    status: str,
    request: Any = None,
) -> bool:
    if status not in {"failed", "unknown", "unmet"}:
        return False
    index = _summary_index(root, request)
    patch_id = int(item.get("patch_id") or 0)
    if patch_id and patch_id not in index["existing_patch_ids"]:
        return False
    risk_item_id = str(item.get("id") or "")
    if risk_item_id in index["retried_risk_ids"]:
        return False
    if status == "unmet":
        return True
    return int(item["host_id"]) in index["retryable_target_ids"]


def build_risk_item_summaries(root: GovernanceTask, request: Any = None) -> list[dict]:
    locale = _request_locale(request)
    cached = getattr(root, "_execution_record_risk_summaries", None)
    if cached is not None and getattr(root, "_execution_record_risk_summaries_locale", None) == locale:
        return cached
    result = []
    default_patch = _default_patch_label(request)
    for item in _risk_snapshot(root, request):
        status = _item_status(root, item, request)
        display, color = _status_meta(request, status)
        result.append(
            {
                "id": str(item["id"]),
                "display_name": (f'{item.get("host_name") or item["host_id"]}-' f'{item.get("patch_name") or default_patch}'),
                "host_name": item.get("host_name") or str(item["host_id"]),
                "host_ip": item.get("host_ip") or "",
                "patch_name": item.get("patch_name") or "",
                "host_id": int(item["host_id"]),
                "patch_id": int(item.get("patch_id") or 0),
                "status": status,
                "status_display": display,
                "status_color": color,
                "can_retry": _item_can_retry(root, item, status, request),
            }
        )
    root._execution_record_risk_summaries = result
    root._execution_record_risk_summaries_locale = locale
    return result


def build_record_status(root: GovernanceTask, request: Any = None) -> tuple[str, str, str]:
    """按本次动作及自动步骤聚合记录状态。"""
    statuses = [item["status"] for item in build_risk_item_summaries(root, request)]
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
        display, color = _status_meta(request, fallback)
        return fallback, display, color

    values = {"failed" if value in {"unmet", "unknown"} else value for value in statuses}
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
    display, color = _status_meta(request, status)
    return status, display, color


def _skipped_step_reason(
    root: GovernanceTask,
    target_id: int,
    task_type: str,
    grouped: dict[str, list[dict]],
    request: Any = None,
) -> tuple[str, str]:
    root_host = _root_host(root, target_id, request)
    install = grouped.get(GovernanceTaskType.INSTALL, [])
    reboot = grouped.get(GovernanceTaskType.REBOOT, [])

    def reason(key: str, default: str) -> tuple[str, str]:
        return "skipped", patch_message(request, key, default)

    if task_type == GovernanceTaskType.REBOOT and install:
        install_status = install[-1]["status"]
        if install_status == "failed":
            return reason(
                "message.skip.install_failed_no_reboot",
                "Install failed; reboot was not executed",
            )
        if install_status == "cancelled":
            return reason(
                "message.skip.install_cancelled_no_reboot",
                "Install was cancelled; reboot was not executed",
            )
        if root_host and root_host.error_code == "reboot_requirement_unknown":
            return reason(
                "message.skip.reboot_requirement_unknown",
                "Could not determine whether a reboot is required; automatic reboot was not executed",
            )
        if root_host and root_host.error_code == "container_reboot_skipped":
            return reason(
                "message.skip.container_reboot_skipped",
                "This node is a container node and does not support host reboot commands; "
                "restart or redeploy through the container platform if processes need reloading",
            )
        if root_host and _host_stage(root_host) == "pending_reboot" and not root.auto_reboot:
            return reason(
                "message.skip.auto_reboot_disabled",
                "Automatic reboot after installation is not enabled",
            )
        if root_host and _host_stage(root_host) == "completed":
            return reason(
                "message.skip.reboot_not_needed",
                "Confirmed that a reboot is not required after installation",
            )
        if install_status in {"completed", "failed", "cancelled"}:
            return reason(
                "message.skip.reboot_not_executed",
                "Reboot was not executed for this action",
            )

    if task_type == GovernanceTaskType.VERIFY:
        if install and install[-1]["status"] == "failed":
            return reason(
                "message.skip.install_failed_no_verify",
                "Install failed; verification was not executed",
            )
        if install and install[-1]["status"] == "cancelled":
            return reason(
                "message.skip.install_cancelled_no_verify",
                "Install was cancelled; verification was not executed",
            )
        if root_host and root.task_type == GovernanceTaskType.INSTALL:
            if root_host.error_code == "reboot_requirement_unknown":
                return reason(
                    "message.skip.reboot_unknown_no_verify",
                    "Reboot requirement could not be determined; verification was not executed",
                )
            if _host_stage(root_host) == "pending_reboot" and not root.auto_reboot:
                return reason(
                    "message.skip.no_reboot_no_verify",
                    "Reboot was not executed; verification is skipped for this record",
                )
        if reboot and reboot[-1]["status"] == "failed":
            return reason(
                "message.skip.reboot_failed_no_verify",
                "Reboot failed; verification was not executed",
            )
        if reboot and reboot[-1]["status"] == "cancelled":
            return reason(
                "message.skip.reboot_cancelled_no_verify",
                "Reboot was cancelled; verification was not executed",
            )

    return "waiting", ""


def _source_record_data(root: GovernanceTask, item: dict) -> dict | None:
    source_id = int(item.get("source_record_id") or root.source_record_id or 0)
    if not source_id:
        return None
    source = GovernanceTask.objects.filter(pk=source_id).only("id", "name").first()
    return {"id": source.id, "name": source.name} if source else None


def build_risk_item_detail(
    root: GovernanceTask,
    risk_item_id: str,
    request: Any = None,
) -> dict | None:
    item = next(
        (entry for entry in _risk_snapshot(root, request) if str(entry.get("id")) == str(risk_item_id)),
        None,
    )
    if item is None:
        return None

    target_id = int(item["host_id"])
    grouped = _group_attempts(root, target_id, include_log=True, request=request)
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
            status, reason = _skipped_step_reason(root, target_id, task_type, grouped, request=request)
        display, color = _status_meta(request, status)
        steps.append(
            {
                "key": task_type,
                "name": _step_name(request, task_type),
                "status": status,
                "status_display": display,
                "status_color": color,
                "reason": reason,
                "attempts": attempts,
            }
        )

    status = _item_status(root, item, request)
    display, color = _status_meta(request, status)
    verification = _verification_result(root, item, request)
    default_patch = _default_patch_label(request)
    return {
        **item,
        "id": str(item["id"]),
        "display_name": (f'{item.get("host_name") or target_id}-' f'{item.get("patch_name") or default_patch}'),
        "host_ip": item.get("host_ip") or "",
        "status": status,
        "status_display": display,
        "status_color": color,
        "can_retry": _item_can_retry(root, item, status, request),
        "source_record": _source_record_data(root, item),
        "verification_result": verification,
        "steps": steps,
    }
