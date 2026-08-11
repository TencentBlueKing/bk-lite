"""治理任务创建服务

封装一键治理 / 一键重启 / 单主机评估 的统一入口：
- 数据校验
- 创建 GovernanceTask + GovernanceTaskHost 占位
- 触发异步任务（Celery / NATS 调度）
"""

import hashlib
import json
from datetime import datetime

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.logger import logger
from apps.core.utils.team_utils import get_current_team
from apps.patch_mgmt.constants import (
    GovernanceTaskStatus,
    GovernanceTaskType,
    RemediationStatus,
    RebootPolicy,
    RequirementAssessmentStatus,
)
from apps.patch_mgmt.exceptions import PatchBusinessError
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    Patch,
    PatchTarget,
)


class HostBusyError(PatchBusinessError):
    """立即执行请求命中了正在运行补丁任务的主机。"""

    def __init__(self, target_ids: list[int]):
        self.target_ids = sorted(set(target_ids))
        super().__init__(
            "hosts_busy",
            "The following targets are running patch tasks: {ids}",
            params={"ids": self.target_ids},
        )


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
        raise PatchBusinessError("execution_window_required", "Start and end times are required in execution-window mode")
    try:
        start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PatchBusinessError("invalid_execution_window", "Invalid execution-window time", raw_detail=str(exc)) from exc
    if end <= start:
        raise PatchBusinessError("execution_window_order", "Execution-window end time must be later than its start time")
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


def _require_manual_task_name(data: dict) -> str:
    """人工治理/重启必须由用户命名；自动评估和子任务不受影响。"""
    name = str(data.get("name") or "").strip()
    if not name:
        raise PatchBusinessError(
            "task_name_required", "Task name is required"
        )
    if len(name) > 128:
        raise PatchBusinessError(
            "task_name_too_long", "Task name must not exceed 128 characters"
        )
    return name


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


def _source_record_by_pair(items) -> dict[tuple[int, int], int]:
    """找到每个待重启风险项最新的安装根记录。"""
    wanted = {(int(item.host_id), int(item.patch_id)) for item in items}
    result: dict[tuple[int, int], int] = {}
    if not wanted:
        return result
    for install_task in GovernanceTask.objects.filter(
        parent_task__isnull=True,
        task_type=GovernanceTaskType.INSTALL,
        host_results__stage="pending_reboot",
    ).distinct().order_by("-created_at", "-id"):
        for snapshot in install_task.risk_snapshot or []:
            pair = (
                int(snapshot.get("host_id") or 0),
                int(snapshot.get("patch_id") or 0),
            )
            if pair in wanted and pair not in result:
                result[pair] = install_task.id
        if len(result) == len(wanted):
            break
    return result


def _build_reboot_scope(target_ids: list[int]) -> tuple[list[dict], str]:
    """生成主机级待重启范围及可校验的快照指纹。"""
    from apps.patch_mgmt.services.risk_service import compute_risk_items

    pending_items = sorted(
        (
            item
            for item in compute_risk_items()
            if item.remediation == RemediationStatus.PENDING_REBOOT
            and item.host_id in target_ids
        ),
        key=lambda item: (item.host_id, item.patch_id, item.baseline_id),
    )
    source_by_pair = _source_record_by_pair(pending_items)
    snapshot = [
        {
            "id": f"{item.host_id}:{item.patch_id}:{item.baseline_id}",
            "host_id": item.host_id,
            "host_name": item.host_name,
            "host_ip": item.host_ip,
            "patch_id": item.patch_id,
            "patch_name": item.patch_title,
            "patch_severity": item.patch_severity,
            "baseline_id": item.baseline_id,
            "baseline_name": item.baseline_name,
            "source_record_id": source_by_pair.get((item.host_id, item.patch_id)),
        }
        for item in pending_items
    ]
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    token = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return snapshot, token


def get_reboot_scope(target_ids: list) -> dict:
    """返回重启确认弹窗必须展示的完整主机-补丁范围。"""
    normalized = sorted({int(target_id) for target_id in target_ids if target_id})
    if not normalized:
        raise PatchBusinessError("target_ids_required", "target_ids is required")
    existing = set(
        PatchTarget.objects.filter(pk__in=normalized).values_list("id", flat=True)
    )
    missing = [target_id for target_id in normalized if target_id not in existing]
    if missing:
        raise PatchBusinessError(
            "targets_not_found", "Targets not found: {ids}", params={"ids": missing}
        )
    snapshot, token = _build_reboot_scope(normalized)
    covered = {int(item["host_id"]) for item in snapshot}
    not_pending = sorted(set(normalized) - covered)
    if not_pending:
        raise PatchBusinessError(
            "targets_not_pending_reboot",
            "The following targets are not pending reboot: {ids}",
            params={"ids": not_pending},
        )
    return {"target_ids": normalized, "items": snapshot, "scope_token": token}


@transaction.atomic
def create_remediation_task(request, items: list[dict], data: dict) -> GovernanceTask:
    """一键治理：按 (host_id, patch_id) 对创建 install 任务。

    items: [{"host_id": int, "patch_id": int}, ...]
    自动去重并校验所有 host/patch 必须存在且已绑定基线（未绑定时拒绝）。
    """
    if not items:
        raise PatchBusinessError("items_required", "items is required")
    name = _require_manual_task_name(data)

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
        raise PatchBusinessError("invalid_items", "items contains invalid entries: {items}", params={"items": invalid[:3]})

    target_ids = list(dict.fromkeys(h for h, _ in pairs))
    patch_ids = list(dict.fromkeys(p for _, p in pairs))

    # 校验存在性
    existing_targets = set(PatchTarget.objects.filter(pk__in=target_ids).values_list("id", flat=True))
    missing_targets = [h for h in target_ids if h not in existing_targets]
    if missing_targets:
        raise PatchBusinessError("targets_not_found", "Targets not found: {ids}", params={"ids": missing_targets})

    _lock_and_assert_hosts_available(target_ids, data.get("execution_mode", "now"))

    # 锁内重新读取绑定，避免评估后切换基线与治理创建并发造成 TOCTOU。
    bindings = {
        binding.target_id: binding
        for binding in HostBaselineBinding.objects.select_for_update()
        .filter(target_id__in=target_ids)
        .select_related("baseline", "target")
    }
    bound = set(bindings)
    unbound = [h for h in target_ids if h not in bound]
    if unbound:
        raise PatchBusinessError("targets_without_baseline", "The following targets have no baseline: {ids}", params={"ids": unbound})

    patches = Patch.objects.in_bulk(patch_ids)
    missing_patches = [patch_id for patch_id in patch_ids if patch_id not in patches]
    if missing_patches:
        raise PatchBusinessError("patches_not_found", "Patches not found: {ids}", params={"ids": missing_patches})

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
        raise PatchBusinessError(
            "patches_not_in_baseline",
            "Selected patches are not in the targets' current baselines: {pairs}",
            params={"pairs": invalid_pairs},
        )

    remediable_snapshots = list(
        HostComplianceSnapshot.objects.filter(
            binding_id__in=[binding.id for binding in bindings.values()],
            requirement__baseline_id__in={binding.baseline_id for binding in bindings.values()},
            requirement__patch_id__in=patch_ids,
            status=RequirementAssessmentStatus.MISSING,
        )
        .filter(requirement__baseline_id=F("binding__baseline_id"))
        .values("binding__target_id", "requirement__patch_id", "evidence")
    )
    remediable_pairs = {
        (snapshot["binding__target_id"], snapshot["requirement__patch_id"])
        for snapshot in remediable_snapshots
    }
    preview_warnings = {
        (snapshot["binding__target_id"], snapshot["requirement__patch_id"]): str(
            ((snapshot.get("evidence") or {}).get("install_impact") or {}).get("error") or ""
        )[:500]
        for snapshot in remediable_snapshots
    }
    not_remediable_pairs = [pair for pair in pairs if pair not in remediable_pairs]
    if not_remediable_pairs:
        raise PatchBusinessError(
            "patches_not_remediable",
            "Selected patches are not missing in the latest assessment: {pairs}",
            params={"pairs": not_remediable_pairs},
        )

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
            **(
                {"preview_warning": preview_warnings[(host_id, patch_id)]}
                if preview_warnings.get((host_id, patch_id))
                else {}
            ),
        }
        for host_id, patch_id in pairs
    ]

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
    name = _require_manual_task_name(data)
    target_ids = sorted({int(t) for t in target_ids if t})
    if not target_ids:
        raise PatchBusinessError("target_ids_required", "target_ids is required")

    existing = set(PatchTarget.objects.filter(pk__in=target_ids).values_list("id", flat=True))
    missing = [h for h in target_ids if h not in existing]
    if missing:
        raise PatchBusinessError("targets_not_found", "Targets not found: {ids}", params={"ids": missing})

    # 重启必须有窗口
    if data.get("execution_mode") != "window":
        data = {**data, "execution_mode": "window"}
    _lock_and_assert_hosts_available(target_ids, data.get("execution_mode", "window"))
    reboot_snapshot, scope_token = _build_reboot_scope(target_ids)
    covered = {int(item["host_id"]) for item in reboot_snapshot}
    not_pending_reboot = sorted(set(target_ids) - covered)
    if not_pending_reboot:
        raise PatchBusinessError(
            "targets_not_pending_reboot",
            "The following targets are not pending reboot: {ids}",
            params={"ids": not_pending_reboot},
        )
    expected_token = str(data.get("scope_token") or "")
    if not expected_token or expected_token != scope_token:
        raise PatchBusinessError(
            "reboot_scope_changed",
            "The pending-reboot scope has changed. Refresh and confirm it again",
        )

    task = _build_task(
        request,
        name=name,
        task_type=GovernanceTaskType.REBOOT,
        target_ids=target_ids,
        patch_ids=list(
            dict.fromkeys(
                int(item["patch_id"])
                for item in reboot_snapshot
                if item.get("patch_id")
            )
        ),
        data={**data, "risk_snapshot": reboot_snapshot},
    )
    source_ids = {
        int(item.get("source_record_id") or 0) for item in reboot_snapshot
    } - {0}
    if len(source_ids) == 1:
        task.source_record_id = source_ids.pop()
        task.save(update_fields=["source_record", "updated_at"])
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
        raise PatchBusinessError("target_ids_required", "target_ids is required")
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
def create_retry_task(
    request,
    original_task: GovernanceTask,
    risk_item_id: str,
) -> GovernanceTask:
    """重试单个风险项，并创建独立的新根执行记录。"""
    from apps.patch_mgmt.services.execution_record_service import (
        build_risk_item_summaries,
    )

    original_task = GovernanceTask.objects.select_for_update().get(pk=original_task.pk)
    item = next(
        (
            snapshot
            for snapshot in (original_task.risk_snapshot or [])
            if str(snapshot.get("id")) == str(risk_item_id)
        ),
        None,
    )
    summary = next(
        (
            current
            for current in build_risk_item_summaries(original_task)
            if str(current["id"]) == str(risk_item_id)
        ),
        None,
    )
    if item is None or summary is None or not summary.get("can_retry"):
        raise PatchBusinessError(
            "risk_item_not_retryable",
            "The risk item does not exist or cannot be retried",
        )
    target_id = int(item["host_id"])
    if not PatchTarget.objects.filter(pk=target_id).exists():
        raise PatchBusinessError("target_deleted", "The target does not exist or has been deleted and cannot be retried")

    _lock_and_assert_hosts_available([target_id], "now")
    if GovernanceTask.objects.filter(
        parent_task__isnull=True,
        source_record=original_task,
        source_risk_item_id=str(risk_item_id),
    ).exists():
        raise PatchBusinessError(
            "risk_item_already_retried",
            "A new retry record has already been created for this risk item",
        )
    host = original_task.host_results.filter(target_id=target_id).first()

    task_type = original_task.task_type
    target_snapshot = [{**item, "source_record_id": original_task.id}]
    patch_ids = list(
        dict.fromkeys(
            int(snapshot["patch_id"])
            for snapshot in target_snapshot
            if snapshot.get("patch_id")
        )
    )
    missing_patch_ids = sorted(
        set(patch_ids)
        - set(Patch.objects.filter(pk__in=patch_ids).values_list("pk", flat=True))
    )
    if missing_patch_ids:
        raise PatchBusinessError(
            "patch_deleted",
            "The patch no longer exists and this risk item cannot be retried",
        )
    host_name = item.get("host_name") or (host.target_name if host else str(target_id))
    name = f"重试 · {host_name} · {_now().strftime('%m-%d %H:%M')}"

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
    task.source_record = original_task
    task.source_risk_item_id = str(risk_item_id)
    task.save(update_fields=["source_record", "source_risk_item_id", "updated_at"])
    _trigger_async(task.id)
    return task
