"""治理任务创建服务

封装一键治理 / 一键重启 / 单主机评估 的统一入口：
- 数据校验
- 创建 GovernanceTask + GovernanceTaskHost 占位
- 触发异步任务（Celery / NATS 调度）
"""

import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.core.utils.team_utils import get_current_team
from apps.patch_mgmt.constants import (
    GovernanceTaskStatus,
    GovernanceTaskType,
    RemediationStatus,
    RebootPolicy,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    Patch,
    PatchTarget,
)

logger = logging.getLogger("app")


class HostBusyError(ValueError):
    """立即执行请求命中了正在运行补丁任务的主机。"""

    def __init__(self, target_ids: list[int]):
        self.target_ids = sorted(set(target_ids))
        super().__init__(f"以下主机正在执行补丁任务: {self.target_ids}")


def _now():
    return timezone.now()


def _validate_window(data: dict) -> tuple[datetime | None, datetime | None]:
    """校验执行窗口；now 模式自动忽略窗口。"""
    mode = data.get("execution_mode", "now")
    if mode == "now":
        return None, None
    start_raw = data.get("execution_window_start")
    end_raw = data.get("execution_window_end")
    if not start_raw or not end_raw:
        raise ValueError("执行窗口模式下必须提供开始/结束时间")
    try:
        start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"执行窗口时间格式错误: {exc}") from exc
    if end <= start:
        raise ValueError("执行窗口结束时间必须晚于开始时间")
    return start, end


def _resolve_reboot_policy(data: dict) -> str:
    """根据请求体推断 reboot_policy。"""
    raw = (data.get("reboot_policy") or "").strip()
    valid = {c[0] for c in RebootPolicy.CHOICES}
    if raw in valid:
        return raw
    if data.get("auto_reboot"):
        return RebootPolicy.IMMEDIATE
    return RebootPolicy.NO_REBOOT


def _resolve_team(request) -> list[int]:
    """从请求上下文解析当前组织 ID，用于任务权限隔离。"""
    team_str = get_current_team(request)
    if team_str:
        try:
            return [int(team_str)]
        except (TypeError, ValueError):
            logger.warning("无法解析 current_team: %s", team_str)
    return []


def _trigger_async(task_id: int) -> None:
    """触发 Celery 异步执行；投递失败必须显式收口，禁止伪成功。"""
    try:
        from apps.patch_mgmt.tasks import execute_governance_task

        task = GovernanceTask.objects.get(pk=task_id)
        if (
            task.execution_mode == "window"
            and task.execution_window_start
            and task.execution_window_start > _now()
        ):
            execute_governance_task.apply_async(
                args=[task_id], eta=task.execution_window_start
            )
        else:
            execute_governance_task.delay(task_id)
    except Exception as exc:  # noqa: BLE001
        reason = f"异步任务投递失败: {exc}"
        GovernanceTask.objects.filter(pk=task_id).update(
            status=GovernanceTaskStatus.FAILED,
            finished_at=_now(),
        )
        GovernanceTaskHost.objects.filter(task_id=task_id).update(
            stage="failed",
            stage_color="error",
            failed_stage="dispatch",
            reason=reason,
            can_retry=True,
        )
        logger.exception("%s task_id=%s", reason, task_id)
        raise RuntimeError(reason) from exc


def _lock_and_assert_hosts_available(target_ids: list[int], execution_mode: str) -> None:
    """锁定目标并原子校验立即执行任务的主机互斥。"""
    list(PatchTarget.objects.select_for_update().filter(pk__in=target_ids).values_list("id", flat=True))
    if execution_mode == "window":
        return
    busy = list(
        GovernanceTaskHost.objects.filter(
            target_id__in=target_ids,
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).values_list("target_id", flat=True).distinct()
    )
    if busy:
        raise HostBusyError(busy)


def _build_task(
    request,
    *,
    name: str,
    task_type: str,
    target_ids: list[int],
    patch_ids: list[int],
    data: dict,
) -> GovernanceTask:
    """构造 GovernanceTask + 主机占位记录。"""
    window_start, window_end = _validate_window(data)
    exec_mode = data.get("execution_mode", "now")
    if exec_mode not in ("now", "window"):
        exec_mode = "now"

    task = GovernanceTask.objects.create(
        name=name,
        task_type=task_type,
        execution_mode=exec_mode,
        execution_window_start=window_start,
        execution_window_end=window_end,
        auto_reboot=bool(data.get("auto_reboot", False)),
        reboot_policy=_resolve_reboot_policy(data),
        status=GovernanceTaskStatus.PENDING,
        target_list=[int(t) for t in target_ids],
        patch_list=[int(p) for p in patch_ids],
        risk_snapshot=data.get("risk_snapshot") or [],
        timeout=int(data.get("timeout") or 3600),
        team=_resolve_team(request),
    )

    # 主机占位
    for tid in target_ids:
        try:
            target = PatchTarget.objects.get(pk=tid)
            target_name, target_ip = target.name, target.ip
        except PatchTarget.DoesNotExist:
            target_name, target_ip = "", ""
        GovernanceTaskHost.objects.create(
            task=task,
            target_id=int(tid),
            target_name=target_name,
            target_ip=target_ip,
            stage="waiting",
            stage_color="default",
        )

    # 审计字段
    user = getattr(request, "user", None)
    if user and getattr(user, "username", None):
        try:
            task.created_by = user.username
            task.save(update_fields=["created_by", "updated_at"])
        except Exception:  # noqa: BLE001
            pass
    return task


@transaction.atomic
def create_remediation_task(request, items: list[dict], data: dict) -> GovernanceTask:
    """一键治理：按 (host_id, patch_id) 对创建 install 任务。

    items: [{"host_id": int, "patch_id": int}, ...]
    自动去重并校验所有 host/patch 必须存在且已绑定基线（未绑定时拒绝）。
    """
    if not items:
        raise ValueError("items 不能为空")

    # 去重 + 类型转换；保留用户选择顺序，供详情左侧风险项稳定展示。
    pairs: list[tuple[int, int]] = []
    seen_pairs: set[tuple[int, int]] = set()
    invalid: list[str] = []
    for it in items:
        try:
            h = int(it.get("host_id"))
            p = int(it.get("patch_id"))
        except (TypeError, ValueError):
            invalid.append(str(it))
            continue
        if not (h and p):
            invalid.append(str(it))
            continue
        pair = (h, p)
        if pair not in seen_pairs:
            pairs.append(pair)
            seen_pairs.add(pair)

    if invalid:
        raise ValueError(f"items 含非法项: {invalid[:3]}{'...' if len(invalid) > 3 else ''}")

    target_ids = list(dict.fromkeys(h for h, _ in pairs))
    patch_ids = list(dict.fromkeys(p for _, p in pairs))

    # 校验存在性
    existing_targets = set(PatchTarget.objects.filter(pk__in=target_ids).values_list("id", flat=True))
    missing_targets = [h for h in target_ids if h not in existing_targets]
    if missing_targets:
        raise ValueError(f"目标主机不存在: {missing_targets}")

    # 校验所有目标必须已绑定基线
    bindings = {
        binding.target_id: binding
        for binding in HostBaselineBinding.objects.filter(target_id__in=target_ids).select_related(
            "baseline", "target"
        )
    }
    bound = set(bindings)
    unbound = [h for h in target_ids if h not in bound]
    if unbound:
        raise ValueError(f"以下主机未绑定基线: {unbound}")
    _lock_and_assert_hosts_available(target_ids, data.get("execution_mode", "now"))

    patches = Patch.objects.in_bulk(patch_ids)
    missing_patches = [patch_id for patch_id in patch_ids if patch_id not in patches]
    if missing_patches:
        raise ValueError(f"补丁不存在: {missing_patches}")

    valid_requirements = set(
        BaselineRequirement.objects.filter(
            baseline_id__in={binding.baseline_id for binding in bindings.values()},
            patch_id__in=patch_ids,
        ).values_list("baseline_id", "patch_id")
    )
    invalid_pairs = [
        (host_id, patch_id)
        for host_id, patch_id in pairs
        if (bindings[host_id].baseline_id, patch_id) not in valid_requirements
    ]
    if invalid_pairs:
        raise ValueError(f"所选补丁不属于对应主机的当前基线: {invalid_pairs}")

    risk_snapshot = [
        {
            "id": f"{host_id}:{patch_id}:{bindings[host_id].baseline_id}",
            "host_id": host_id,
            "host_name": bindings[host_id].target.name,
            "host_ip": bindings[host_id].target.ip,
            "patch_id": patch_id,
            "patch_name": patches[patch_id].title,
            "baseline_id": bindings[host_id].baseline_id,
            "baseline_name": bindings[host_id].baseline.name,
        }
        for host_id, patch_id in pairs
    ]

    default_name = (
        f"治理 · {bindings[target_ids[0]].target.name} · {len(pairs)}项"
        if len(target_ids) == 1
        else f"一键治理 · {len(target_ids)}台 · {len(pairs)}项"
    )
    name = (data.get("name") or "").strip() or default_name
    task = _build_task(
        request,
        name=name,
        task_type=GovernanceTaskType.INSTALL,
        target_ids=target_ids,
        patch_ids=patch_ids,
        data={**data, "risk_snapshot": risk_snapshot},
    )
    _trigger_async(task.id)
    return task


@transaction.atomic
def create_reboot_task(request, target_ids: list, data: dict) -> GovernanceTask:
    """一键重启：创建 reboot 任务。重启任务必须设置窗口。"""
    from apps.patch_mgmt.services.risk_service import compute_risk_items

    target_ids = sorted({int(t) for t in target_ids if t})
    if not target_ids:
        raise ValueError("target_ids 不能为空")

    existing = set(PatchTarget.objects.filter(pk__in=target_ids).values_list("id", flat=True))
    missing = [h for h in target_ids if h not in existing]
    if missing:
        raise ValueError(f"目标主机不存在: {missing}")

    pending_items = [
        item
        for item in compute_risk_items()
        if item.remediation == RemediationStatus.PENDING_REBOOT
        and item.host_id in target_ids
    ]
    pending_reboot_target_ids = {item.host_id for item in pending_items}
    not_pending_reboot = sorted(set(target_ids) - pending_reboot_target_ids)
    if not_pending_reboot:
        raise ValueError(f"以下主机当前不是待重启状态: {not_pending_reboot}")

    # 重启必须有窗口
    if data.get("execution_mode") != "window":
        data = {**data, "execution_mode": "window"}
    _lock_and_assert_hosts_available(target_ids, data.get("execution_mode", "window"))

    source_task_by_pair: dict[tuple[int, int], int] = {}
    for install_task in GovernanceTask.objects.filter(
        parent_task__isnull=True,
        task_type=GovernanceTaskType.INSTALL,
    ).order_by("-created_at"):
        for snapshot in install_task.risk_snapshot or []:
            pair = (int(snapshot.get("host_id") or 0), int(snapshot.get("patch_id") or 0))
            source_task_by_pair.setdefault(pair, install_task.id)

    reboot_snapshot = [
        {
            "id": f"{item.host_id}:{item.patch_id}:{item.baseline_id}",
            "host_id": item.host_id,
            "host_name": item.host_name,
            "host_ip": item.host_ip,
            "patch_id": item.patch_id,
            "patch_name": item.patch_title,
            "baseline_id": item.baseline_id,
            "baseline_name": item.baseline_name,
            "source_task_id": source_task_by_pair.get((item.host_id, item.patch_id)),
        }
        for item in pending_items
    ]
    default_name = (
        f"重启 · {pending_items[0].host_name}"
        if len(target_ids) == 1 and pending_items
        else f"一键重启 · {len(target_ids)}台"
    )
    name = (data.get("name") or "").strip() or default_name
    task = _build_task(
        request,
        name=name,
        task_type=GovernanceTaskType.REBOOT,
        target_ids=target_ids,
        patch_ids=[],
        data={**data, "risk_snapshot": reboot_snapshot},
    )
    _trigger_async(task.id)
    return task


@transaction.atomic
def _create_evaluation_task(
    request,
    target_ids: list,
    data: dict,
    *,
    task_type: str,
    default_name_prefix: str,
) -> GovernanceTask:
    """评估/验证任务创建公共逻辑。"""
    target_ids = [int(t) for t in target_ids if t]
    if not target_ids:
        raise ValueError("target_ids 不能为空")
    _lock_and_assert_hosts_available(target_ids, data.get("execution_mode", "now"))

    name = (data.get("name") or "").strip() or f"{default_name_prefix} · {len(target_ids)} 台 · {_now().strftime('%m-%d %H:%M')}"
    task = _build_task(
        request,
        name=name,
        task_type=task_type,
        target_ids=target_ids,
        patch_ids=[],
        data=data,
    )
    _trigger_async(task.id)
    return task


def create_assess_task(request, target_ids: list, data: dict) -> GovernanceTask:
    """单主机评估：创建 assess 任务。"""
    return _create_evaluation_task(
        request,
        target_ids,
        data,
        task_type=GovernanceTaskType.ASSESS,
        default_name_prefix="评估",
    )


def create_verify_task(request, target_ids: list, data: dict) -> GovernanceTask:
    """修复后验证：创建 verify 任务，执行逻辑与 assess 相同。"""
    return _create_evaluation_task(
        request,
        target_ids,
        data,
        task_type=GovernanceTaskType.VERIFY,
        default_name_prefix="验证",
    )


@transaction.atomic
def create_retry_task(request, original_task: GovernanceTask, target_id: int) -> GovernanceTask:
    """重试失败主机：在同一可见根记录下创建内部步骤尝试。

    - install 任务保留原 patch_list
    - 标记原主机 can_retry=False 防止重复重试
    """
    from apps.patch_mgmt.services.execution_record_service import (
        _task_chain,
        build_risk_item_summaries,
    )

    original_task = GovernanceTask.objects.select_for_update().get(pk=original_task.pk)
    chain = _task_chain(original_task)
    retryable_host = GovernanceTaskHost.objects.filter(
        task__in=chain,
        target_id=target_id,
        can_retry=True,
    ).order_by("-created_at").first()
    has_unmet_item = any(
        item["host_id"] == target_id and item["status"] == "unmet"
        for item in build_risk_item_summaries(original_task)
    )
    if retryable_host is None and not has_unmet_item:
        raise ValueError("该主机不可重试或不存在")
    if not PatchTarget.objects.filter(pk=target_id).exists():
        raise ValueError("目标不存在或已删除，无法重试")

    _lock_and_assert_hosts_available([target_id], "now")
    host = original_task.host_results.filter(target_id=target_id).first() or retryable_host

    # 防止重复重试
    GovernanceTaskHost.objects.filter(
        task__in=chain,
        target_id=target_id,
        can_retry=True,
    ).update(can_retry=False, updated_at=_now())

    task_type = original_task.task_type
    target_snapshot = [
        item
        for item in (original_task.risk_snapshot or [])
        if int(item.get("host_id") or 0) == target_id
    ]
    patch_ids = (
        list(dict.fromkeys(int(item["patch_id"]) for item in target_snapshot if item.get("patch_id")))
        if task_type == GovernanceTaskType.INSTALL
        else []
    )
    if task_type == GovernanceTaskType.INSTALL and not patch_ids:
        patch_ids = list(original_task.patch_list or [])
    name = f"重试 · {host.target_name or str(target_id)} · {_now().strftime('%m-%d %H:%M')}"

    task = _build_task(
        request,
        name=name,
        task_type=task_type,
        target_ids=[target_id],
        patch_ids=patch_ids,
        data={
            "execution_mode": "now",
            "auto_reboot": original_task.auto_reboot,
            "reboot_policy": original_task.reboot_policy,
            "risk_snapshot": target_snapshot,
        },
    )
    task.parent_task = original_task
    task.save(update_fields=["parent_task", "updated_at"])
    _trigger_async(task.id)
    return task
