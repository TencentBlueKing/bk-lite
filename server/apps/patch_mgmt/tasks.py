"""补丁管理 Celery 任务入口（源连通性、周期评估）

涵盖：
  - check_patch_source_connectivity  源连通性探测入口
  - run_periodic_compliance_scan     周期性合规评估入口

不涵盖（由端到端集成接入）：
  - 实际 NATS/SSH 扫描/安装命令下发
  - 流式结果回调的完整解析逻辑
"""

import logging
from datetime import timedelta

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("app")


@shared_task(max_retries=0)
def check_patch_source_connectivity(source_id: int) -> None:
    """补丁源连通性探测 Celery 入口。

    执行真实 HTTP 探测（connectivity_prober.probe_source）：
      - 有 URL：探测可达性 → record_connectivity_result 写回 CONNECTED/FAILED。
      - 无 URL：无法探测 → 重置为 UNKNOWN。

    Args:
        source_id: PatchSource.pk
    """
    from apps.patch_mgmt.models import PatchSource
    from apps.patch_mgmt.services.connectivity_prober import probe_source
    from apps.patch_mgmt.services.source_sync_service import SourceSyncService

    logger.info("[check_patch_source_connectivity] 开始: source_id=%s", source_id)
    try:
        source = PatchSource.objects.get(pk=source_id)
    except PatchSource.DoesNotExist:
        logger.error(
            "[check_patch_source_connectivity] 补丁源不存在: source_id=%s", source_id
        )
        return

    result = probe_source(source)
    if result is None:
        # 源未配置 URL，无法探测，保持/置为 UNKNOWN。
        SourceSyncService.trigger_connectivity_check(source)
        logger.info(
            "[check_patch_source_connectivity] 无 URL 跳过探测: source_id=%s name=%s",
            source_id, source.name,
        )
        return

    SourceSyncService.record_connectivity_result(source, reachable=result.reachable)
    logger.info(
        "[check_patch_source_connectivity] 探测完成: source_id=%s name=%s %s",
        source_id, source.name, result.detail,
    )


@shared_task(max_retries=0)
def run_periodic_compliance_scan() -> None:
    """周期性合规评估入口。

    由全局扫描设置（ScanSetting）对应的 django_celery_beat 周期任务触发，
    为当前所有 PatchTarget 创建一条类型为 assess 的 GovernanceTask 记录。
    实际的扫描/评估执行逻辑由后续端到端集成补充。
    """
    from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
    from apps.patch_mgmt.models import GovernanceTask, PatchTarget, ScanSetting

    setting = ScanSetting.get_singleton()
    if not setting.is_enabled:
        logger.info("[run_periodic_compliance_scan] 扫描设置已禁用，跳过本次评估")
        return

    target_ids = list(PatchTarget.objects.values_list("id", flat=True))
    if not target_ids:
        logger.info("[run_periodic_compliance_scan] 暂无目标主机，跳过本次评估")
        return

    task = GovernanceTask.objects.create(
        name=f"周期性合规评估 ({timezone.now().strftime('%Y-%m-%d %H:%M')})",
        task_type=GovernanceTaskType.ASSESS,
        execution_mode="now",
        status=GovernanceTaskStatus.PENDING,
        target_list=target_ids,
        patch_list=[],
    )
    execute_governance_task.delay(task.id)
    logger.info(
        "[run_periodic_compliance_scan] 已创建并触发评估任务: task_id=%s targets=%s",
        task.id, len(target_ids),
    )


@shared_task(max_retries=0)
def execute_governance_task(task_id: int) -> None:
    """启动治理父任务，并将每台主机拆成独立 Celery 子任务。"""
    from apps.patch_mgmt.config import CHAIN_TIMEOUT, get_host_task_limits
    from apps.patch_mgmt.constants import GovernanceTaskStatus
    from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, PatchTarget
    from apps.patch_mgmt.services.patch_execution_service import _finalize_task_status

    try:
        task = GovernanceTask.objects.get(pk=task_id)
    except GovernanceTask.DoesNotExist:
        logger.error("[execute_governance_task] 任务不存在: task_id=%s", task_id)
        return

    if task.status not in (GovernanceTaskStatus.PENDING,):
        logger.info(
            "[execute_governance_task] 任务非待执行状态: task_id=%s status=%s",
            task_id, task.status,
        )
        return

    now = timezone.now()
    task.status = GovernanceTaskStatus.RUNNING
    task.started_at = task.started_at or now
    chain_fields = []
    if task.task_type == "install" and task.chain_started_at is None:
        task.chain_started_at = now
        task.chain_deadline_at = now + timedelta(seconds=CHAIN_TIMEOUT)
        chain_fields = ["chain_started_at", "chain_deadline_at"]
    task.save(update_fields=["status", "started_at", *chain_fields, "updated_at"])
    logger.info(
        "[execute_governance_task] 已切到 running: task_id=%s type=%s targets=%s",
        task_id, task.task_type, len(task.target_list or []),
    )

    targets = {
        target.id: target
        for target in PatchTarget.objects.filter(pk__in=task.target_list or [])
    }
    existing_hosts = {
        host.target_id: host
        for host in GovernanceTaskHost.objects.filter(task=task)
    }
    soft_limit, hard_limit = get_host_task_limits(task.task_type)
    dispatched = 0

    for target_id in task.target_list or []:
        target = targets.get(target_id)
        host = existing_hosts.get(target_id)
        if host is None:
            host = GovernanceTaskHost.objects.create(
                task=task,
                target_id=target_id,
                target_name=target.name if target else "",
                target_ip=target.ip if target else "",
                stage="waiting",
                stage_color="default",
            )
            existing_hosts[target_id] = host

        if target is None:
            GovernanceTaskHost.objects.filter(pk=host.pk, stage="waiting").update(
                stage="failed",
                stage_color="error",
                failed_stage="dispatch",
                reason="目标不存在或已删除",
                can_retry=False,
                updated_at=timezone.now(),
            )
            continue
        if host.stage != "waiting":
            continue

        try:
            execute_governance_host.apply_async(
                args=[task.id, target_id],
                soft_time_limit=soft_limit,
                time_limit=hard_limit,
            )
            dispatched += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[execute_governance_task] 主机子任务投递失败: task_id=%s target_id=%s",
                task.id, target_id,
            )
            GovernanceTaskHost.objects.filter(pk=host.pk, stage="waiting").update(
                stage="failed",
                stage_color="error",
                failed_stage="dispatch",
                reason=f"主机子任务投递失败: {exc}",
                can_retry=True,
                updated_at=timezone.now(),
            )

    if dispatched == 0:
        _finalize_task_status(task)


@shared_task(max_retries=0)
def execute_governance_host(task_id: int, target_id: int) -> None:
    """执行治理任务中的一台主机；不自动重试有副作用的操作。"""
    from apps.patch_mgmt.constants import GovernanceTaskStatus
    from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost
    from apps.patch_mgmt.services.patch_execution_service import (
        finalize_governance_task,
        handle_host_execution_timeout,
        run_governance_host,
    )

    try:
        task = GovernanceTask.objects.get(pk=task_id)
    except GovernanceTask.DoesNotExist:
        logger.error(
            "[execute_governance_host] 任务不存在: task_id=%s target_id=%s",
            task_id, target_id,
        )
        return

    try:
        if (
            task.execution_mode == "window"
            and task.execution_window_end
            and timezone.now() > task.execution_window_end
        ):
            GovernanceTaskHost.objects.filter(
                task=task, target_id=target_id, stage="waiting"
            ).update(
                stage="failed",
                stage_color="error",
                failed_stage="dispatch",
                error_code="execution_window_expired",
                reason="执行窗口已结束，主机任务未在窗口内开始",
                can_retry=True,
                updated_at=timezone.now(),
            )
            return

        blocking = GovernanceTaskHost.objects.filter(
            target_id=target_id,
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).exclude(task_id=task.id).exclude(
            stage__in=(
                "completed",
                "failed",
                "cancelled",
                "pending_reboot",
                "reboot_failed",
                "pending_confirmation",
            )
        ).filter(
            Q(task__created_at__lt=task.created_at)
            | Q(task__created_at=task.created_at, task_id__lt=task.id)
        ).exists()
        if blocking:
            if task.execution_mode == "window" and (
                not task.execution_window_end or timezone.now() <= task.execution_window_end
            ):
                execute_governance_host.apply_async(
                    args=[task.id, target_id], countdown=10
                )
                logger.info(
                    "[execute_governance_host] 主机忙，窗口任务稍后重试 task_id=%s target_id=%s",
                    task.id,
                    target_id,
                )
                return
            GovernanceTaskHost.objects.filter(
                task=task, target_id=target_id, stage="waiting"
            ).update(
                stage="failed",
                stage_color="error",
                failed_stage="dispatch",
                error_code="host_busy",
                reason="主机正在执行其他补丁任务，未能在允许时间内开始",
                can_retry=True,
                updated_at=timezone.now(),
            )
            return
        run_governance_host(task, target_id)
    except SoftTimeLimitExceeded:
        logger.warning(
            "[execute_governance_host] 主机子任务触发 soft time limit: task_id=%s target_id=%s",
            task_id, target_id,
        )
        handle_host_execution_timeout(task_id, target_id)
    finally:
        finalize_governance_task(task_id)


@shared_task(max_retries=0)
def reconcile_governance_host(task_id: int, target_id: int) -> None:
    """对安装或重启超时的单台主机执行只读结果核验。"""
    from apps.patch_mgmt.services.patch_execution_service import reconcile_host_result

    reconcile_host_result(task_id, target_id)


@shared_task(max_retries=0)
def watch_governance_timeouts() -> None:
    """周期收口调度/阶段超时；安装和重启只进入结果确认，不直接判失败。"""
    from apps.patch_mgmt.config import DISPATCH_TIMEOUT, RECONCILE_TIMEOUT
    from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
    from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost
    from apps.patch_mgmt.services.patch_execution_service import _finalize_task_status
    from apps.patch_mgmt.services.windows_package import expire_stale_windows_package_uploads

    now = timezone.now()
    changed_task_ids: set[int] = set()

    expire_stale_windows_package_uploads(now=now)

    GovernanceTask.objects.filter(
        status__in=GovernanceTaskStatus.ACTIVE_STATES,
        chain_deadline_at__lt=now,
        overdue_at__isnull=True,
    ).update(overdue_at=now, updated_at=now)

    waiting_ids = list(
        GovernanceTaskHost.objects.filter(
            stage="waiting",
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
            created_at__lt=now - timedelta(seconds=DISPATCH_TIMEOUT),
        ).exclude(
            task__execution_mode="window",
            task__execution_window_end__gt=now,
        ).values_list("id", flat=True)
    )
    for host_id in waiting_ids:
        with transaction.atomic():
            host = GovernanceTaskHost.objects.select_for_update().get(pk=host_id)
            if host.stage != "waiting":
                continue
            host.stage = "failed"
            host.stage_color = "error"
            host.failed_stage = "dispatch"
            host.error_code = "dispatch_timeout"
            host.reason = "主机任务超过 5 分钟未被执行器领取"
            host.timeout_reason = host.reason
            host.can_retry = True
            host.save(update_fields=[
                "stage", "stage_color", "failed_stage", "error_code", "reason",
                "timeout_reason", "can_retry", "updated_at",
            ])
            changed_task_ids.add(host.task_id)

    expired_ids = list(
        GovernanceTaskHost.objects.filter(
            stage__in=["scanning", "installing", "rebooting"],
            stage_deadline_at__lt=now,
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).values_list("id", flat=True)
    )
    for host_id in expired_ids:
        should_reconcile = False
        with transaction.atomic():
            host = GovernanceTaskHost.objects.select_for_update().select_related("task").get(pk=host_id)
            if host.stage not in {"scanning", "installing", "rebooting"}:
                continue
            task_type = host.task.task_type
            host.timeout_reason = f"{host.task.get_task_type_display()}阶段超过时限"
            host.reason = host.timeout_reason
            if task_type in (GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT):
                host.stage = "reconciling"
                host.stage_color = "processing"
                host.error_code = f"{task_type}_timeout_unknown"
                host.failed_stage = task_type
                host.reconcile_deadline_at = now + timedelta(seconds=RECONCILE_TIMEOUT)
                host.can_retry = False
                should_reconcile = True
            else:
                host.stage = "failed"
                host.stage_color = "error"
                host.error_code = f"{task_type}_timeout"
                host.failed_stage = task_type
                host.can_retry = True
            host.last_heartbeat_at = now
            host.save(update_fields=[
                "stage", "stage_color", "error_code", "failed_stage", "reason",
                "timeout_reason", "reconcile_deadline_at", "can_retry",
                "last_heartbeat_at", "updated_at",
            ])
            changed_task_ids.add(host.task_id)
            task_id = host.task_id
            target_id = host.target_id
        if should_reconcile:
            reconcile_governance_host.apply_async(args=[task_id, target_id])

    for task in GovernanceTask.objects.filter(pk__in=changed_task_ids):
        _finalize_task_status(task)


@shared_task(max_retries=0)
def ingest_patch_source(source_id: int, keys: list) -> dict:
    """补丁源「同步入库」异步入口（当前用于 WSUS 元数据入库）。

    Linux yum/dnf/apt 走同步入库即可（只写元数据），本任务也兼容调用。

    Args:
        source_id: PatchSource.pk
        keys: 候选补丁 key 列表（Linux 为 advisory_id，WSUS 为 update_id）。

    Returns:
        ingest_selected 的返回结果，或失败时返回 {"error": ...}。
    """
    from apps.patch_mgmt.models import PatchSource
    from apps.patch_mgmt.services.source_sync_service import SourceSyncError, SourceSyncService

    logger.info("[ingest_patch_source] 开始: source_id=%s keys=%s", source_id, len(keys))
    try:
        source = PatchSource.objects.get(pk=source_id)
    except PatchSource.DoesNotExist:
        logger.error("[ingest_patch_source] 补丁源不存在: source_id=%s", source_id)
        return {"error": "补丁源不存在"}

    try:
        result = SourceSyncService.ingest_selected(source, [str(k) for k in keys])
    except (SourceSyncError,) as exc:
        logger.warning("[ingest_patch_source] 同步入库失败: source_id=%s %s", source_id, exc)
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ingest_patch_source] 同步入库异常: source_id=%s", source_id, exc_info=True)
        return {"error": f"同步入库异常: {exc}"}

    logger.info("[ingest_patch_source] 完成: source_id=%s result=%s", source_id, result)
    return result


@shared_task(max_retries=0)
def probe_target_connectivity(target_id: int) -> None:
    """异步探测目标主机连通性（TCP 端口可达），结果写回 connectivity_status。"""
    from apps.patch_mgmt.constants import ConnectivityStatus
    from apps.patch_mgmt.models import PatchTarget
    from apps.patch_mgmt.services.target_connectivity import probe_target

    try:
        target = PatchTarget.objects.get(pk=target_id)
    except PatchTarget.DoesNotExist:
        logger.warning("[probe_target_connectivity] 目标不存在: target_id=%s", target_id)
        return

    result = probe_target(target)
    target.connectivity_status = (
        ConnectivityStatus.CONNECTED if result.reachable else ConnectivityStatus.FAILED
    )
    target.last_checked_at = timezone.now()
    target.save(update_fields=["connectivity_status", "last_checked_at", "updated_at"])
    logger.info(
        "[probe_target_connectivity] target_id=%s reachable=%s detail=%s",
        target_id, result.reachable, result.detail,
    )


@shared_task(max_retries=0)
def verify_pending_reboot_hosts() -> None:
    """扫描 pending_reboot 状态的 reboot 任务主机，探测连通性后自动创建验证任务。

    由 CELERY_BEAT_SCHEDULE 每 60 秒触发一次。只处理 task_type=reboot 的主机
    （install 的 pending_reboot 表示等待用户触发重启，不在此处理）。
    """
    from datetime import timedelta

    from apps.patch_mgmt.config import REBOOT_VERIFY_MAX_WAIT
    from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
    from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, PatchTarget
    from apps.patch_mgmt.services.patch_execution_service import (
        _check_host_reachable,
        _finalize_task_status,
        _read_boot_marker,
    )

    pending_hosts = GovernanceTaskHost.objects.filter(
        stage="pending_reboot",
        task__task_type=GovernanceTaskType.REBOOT,
    ).select_related("task")

    if not pending_hosts.exists():
        return

    logger.info(
        "[verify_pending_reboot_hosts] 发现 %s 台 pending_reboot 主机",
        pending_hosts.count(),
    )

    now = timezone.now()
    max_wait = timedelta(seconds=REBOOT_VERIFY_MAX_WAIT)
    min_wait = timedelta(seconds=60)  # reboot 命令发出后至少等 60 秒再探测

    for host in pending_hosts:
        wait_duration = now - host.updated_at

        # 刚发完 reboot 命令，机器还在关机过程中，跳过
        if wait_duration < min_wait:
            continue

        if wait_duration > max_wait:
            host.stage = "reboot_failed"
            host.stage_color = "error"
            host.reason = f"重启后主机超过 {REBOOT_VERIFY_MAX_WAIT // 60} 分钟未恢复"
            host.can_retry = True
            host.failed_stage = "reboot"
            host.save(update_fields=[
                "stage", "stage_color", "reason",
                "can_retry", "failed_stage", "updated_at",
            ])
            logger.warning(
                "[verify_pending_reboot_hosts] 主机 %s 超时未恢复，标记失败",
                host.target_name,
            )
            _finalize_task_status(host.task)
            continue

        try:
            target = PatchTarget.objects.get(pk=host.target_id)
        except PatchTarget.DoesNotExist:
            continue

        if not _check_host_reachable(target):
            logger.info(
                "[verify_pending_reboot_hosts] 主机 %s 尚未恢复，等待下次轮询",
                host.target_name,
            )
            continue

        current_marker = _read_boot_marker(
            target,
            execution_id=f"reboot-verify:{host.task_id}:{host.target_id}",
        )
        if not host.boot_marker_before or not current_marker:
            logger.warning(
                "[verify_pending_reboot_hosts] 主机 %s 启动标识不可用，继续等待",
                host.target_name,
            )
            continue
        if current_marker == host.boot_marker_before:
            logger.info(
                "[verify_pending_reboot_hosts] 主机 %s 已可达但启动标识未变化，继续等待",
                host.target_name,
            )
            continue

        verify_task = GovernanceTask.objects.create(
            name=f"重启后自动验证 · {host.target_name} · {now.strftime('%m-%d %H:%M')}",
            task_type=GovernanceTaskType.VERIFY,
            execution_mode="now",
            status=GovernanceTaskStatus.PENDING,
            target_list=[host.target_id],
            patch_list=[],
            risk_snapshot=[
                item
                for item in (host.task.risk_snapshot or [])
                if int(item.get("host_id") or 0) == host.target_id
            ],
            team=host.task.team or [],
            created_by=host.task.created_by,
            timeout=host.task.timeout or 3600,
            parent_task=host.task,
            chain_started_at=host.task.chain_started_at,
            chain_deadline_at=host.task.chain_deadline_at,
        )
        GovernanceTaskHost.objects.create(
            task=verify_task,
            target_id=host.target_id,
            target_name=host.target_name,
            target_ip=host.target_ip,
            stage="waiting",
            stage_color="default",
        )

        host.stage = "completed"
        host.stage_color = "success"
        host.reason = f"主机已恢复，已创建自动验证任务 {verify_task.id}"
        host.save(update_fields=["stage", "stage_color", "reason", "updated_at"])
        _finalize_task_status(host.task)

        execute_governance_task.delay(verify_task.id)
        logger.info(
            "[verify_pending_reboot_hosts] 主机 %s 已恢复，创建验证任务 %s",
            host.target_name, verify_task.id,
        )
