from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncRegionState
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import CeleryUtils


@dataclass(frozen=True)
class NodeMgmtSyncReconcileResult:
    schedule_status: str
    node_config_status: str
    error_code: str = ""
    error_message: str = ""
    guard_region_failure: bool = False


@dataclass(frozen=True)
class NodeConfigClaimResult:
    outcome: str
    stage: str = ""
    token: str = ""


@dataclass(frozen=True)
class NodeConfigReconcileResult:
    status: str
    error_code: str = ""
    error_message: str = ""
    contended: bool = False
    guard_region_failure: bool = False


class NodeMgmtSyncReconciler:
    NODE_CONFIG_CLAIM_TIMEOUT = timedelta(minutes=5)
    NODE_CONFIG_DIRTY_MARKER = "NODE_CONFIG_DIRTY"

    @staticmethod
    def _node_config_scope(cloud_region_id) -> str:
        return f"node-config:region:{cloud_region_id}"

    @classmethod
    def _get_or_create_region_state(cls, config, cloud_region_id, collect_task):
        """按区域复用唯一交付状态；旧的 version scope 在首次触达时原位迁移。"""
        scope_key = cls._node_config_scope(cloud_region_id)
        state = NodeMgmtSyncRegionState.objects.filter(scope_key=scope_key).first()
        legacy_states = list(
            NodeMgmtSyncRegionState.objects.filter(
                config=config,
                cloud_region_id=cloud_region_id,
                scope_key__startswith="config:",
            ).order_by("-config_version", "-id")
        )
        claim_cutoff = timezone.now() - cls.NODE_CONFIG_CLAIM_TIMEOUT
        active_legacy = [item for item in legacy_states if item.node_config_status.endswith("_in_progress") and item.updated_at > claim_cutoff]
        stale_legacy = [item for item in legacy_states if item.node_config_status.endswith("_in_progress") and item.updated_at <= claim_cutoff]
        if active_legacy:
            # 活动旧 claim 仍可能正在执行远端 RPC。先等待其 CAS 收口，绝不让
            # stable scope 同时取得第二把区域锁。
            return active_legacy[0], False
        if state is not None:
            if state.node_config_status.endswith("_in_progress") and state.updated_at > claim_cutoff:
                # stable scope 的活动 claim 优先级最高。此时合并 legacy 会覆盖
                # token/status，而原 worker 的远端 RPC 仍可能在执行，造成同区域
                # 第二次并发交付。等待当前 claim 收口后再合并遗留意图。
                return state, False
            pending_legacy = (stale_legacy[0] if stale_legacy else None) or next(
                (item for item in legacy_states if item.node_config_status in ("delete_pending", "push_pending")),
                None,
            )
            if pending_legacy is not None and state.node_config_status not in ("delete_pending", "push_pending"):
                NodeMgmtSyncRegionState.objects.filter(pk=state.pk).update(
                    config_version=pending_legacy.config_version,
                    collect_task=pending_legacy.collect_task,
                    node_config_status=pending_legacy.node_config_status,
                    reason_code=pending_legacy.reason_code,
                    error_message=pending_legacy.error_message,
                    updated_at=pending_legacy.updated_at,
                )
                state.config_version = pending_legacy.config_version
                state.collect_task = pending_legacy.collect_task
                state.node_config_status = pending_legacy.node_config_status
                state.reason_code = pending_legacy.reason_code
                state.error_message = pending_legacy.error_message
                state.updated_at = pending_legacy.updated_at
            if legacy_states:
                NodeMgmtSyncRegionState.objects.filter(pk__in=[item.pk for item in legacy_states]).delete()
            return state, False
        if not legacy_states:
            return NodeMgmtSyncRegionState.objects.get_or_create(
                scope_key=scope_key,
                defaults={
                    "config": config,
                    "config_version": config.version,
                    "cloud_region_id": cloud_region_id,
                    "collect_task": collect_task,
                },
            )
        state = (stale_legacy[0] if stale_legacy else None) or next(
            (item for item in legacy_states if item.node_config_status in ("delete_pending", "push_pending")),
            legacy_states[0],
        )
        if state.scope_key != scope_key:
            # scope 迁移不能刷新 lease 时间，否则会把原本可回收的陈旧 claim
            # 伪装成仍在运行。
            NodeMgmtSyncRegionState.objects.filter(pk=state.pk).update(scope_key=scope_key)
            state.scope_key = scope_key
        other_legacy_ids = [item.pk for item in legacy_states if item.pk != state.pk]
        if other_legacy_ids:
            NodeMgmtSyncRegionState.objects.filter(pk__in=other_legacy_ids).delete()
        return state, False

    @classmethod
    def mark_region_delivery_pending(cls, config, *, cloud_region_id, collect_task) -> None:
        """只登记交付意图，不在同步事务中执行远端 RPC。"""
        cloud_region_id = str(cloud_region_id)
        state, _ = cls._get_or_create_region_state(config, cloud_region_id, collect_task)
        for state_id in (state.pk,):
            for _attempt in range(8):
                state = NodeMgmtSyncRegionState.objects.get(pk=state_id)
                guarded = NodeMgmtSyncRegionState.objects.filter(
                    pk=state.pk,
                    node_config_status=state.node_config_status,
                    reason_code=state.reason_code,
                )
                updates = {
                    "config": config,
                    "config_version": config.version,
                    "cloud_region_id": cloud_region_id,
                    "collect_task": collect_task,
                }
                if state.node_config_status.endswith("_in_progress"):
                    updates["error_message"] = cls.NODE_CONFIG_DIRTY_MARKER
                else:
                    updates.update(
                        node_config_status="delete_pending",
                        reason_code="",
                        error_message="",
                        updated_at=timezone.now(),
                    )
                if guarded.update(**updates):
                    break
            else:
                raise RuntimeError("NODE_CONFIG_INTENT_CONTENDED")

    @classmethod
    def reconcile(cls, config, *, reconcile_node_configs: bool = False):
        try:
            from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

            if not cls._reconcile_schedules_if_current(config, service=NodeMgmtSyncService):
                current = config.__class__.objects.get(pk=config.pk)
                return NodeMgmtSyncReconcileResult(
                    current.schedule_status,
                    current.node_config_status,
                    current.reconcile_error_code,
                    current.reconcile_error_message,
                )
            node_status = config.node_config_status or "unknown"
            node_error_code = ""
            node_error_message = ""
            persist_health = True
            node_outcome = NodeConfigReconcileResult(node_status)
            if reconcile_node_configs and config.__class__.objects.filter(pk=config.pk, version=config.version).exists():
                node_outcome = cls._reconcile_node_configs(
                    config,
                    service=NodeMgmtSyncService,
                )
                if node_outcome.contended:
                    config.refresh_from_db(
                        fields=(
                            "schedule_status",
                            "node_config_status",
                            "reconcile_error_code",
                            "reconcile_error_message",
                        )
                    )
                    node_status = config.node_config_status or "unknown"
                    node_error_code = config.reconcile_error_code
                    node_error_message = config.reconcile_error_message
                    persist_health = False
                else:
                    node_status = node_outcome.status
                    node_error_code = node_outcome.error_code
                    node_error_message = node_outcome.error_message
            result = NodeMgmtSyncReconcileResult(
                "healthy",
                node_status,
                node_error_code,
                node_error_message,
                node_outcome.guard_region_failure if reconcile_node_configs else False,
            )
        except Exception as exc:
            logger.error("节点管理同步对账失败: %s", type(exc).__name__)
            result = NodeMgmtSyncReconcileResult(
                "degraded",
                "degraded",
                "RECONCILE_FAILED",
                f"{type(exc).__name__}: 节点管理同步对账失败",
            )
            persist_health = True
        if persist_health:
            cls._persist_health(config, result)
        return result

    @classmethod
    def _reconcile_schedules_if_current(cls, config, *, service) -> bool:
        """短事务串行化配置更新与 Beat 对账；远端节点 RPC 不进入该事务。"""
        with transaction.atomic():
            current = config.__class__.objects.select_for_update().filter(pk=config.pk, version=config.version).first()
            if current is None:
                return False
            cls._reconcile_periodic_task(
                enabled=current.auto_sync_enabled,
                name=service.SYNC_PERIODIC_TASK_NAME,
                task=service.SYNC_TASK,
                interval=current.sync_interval_minutes,
            )
            cls._reconcile_periodic_task(
                enabled=current.auto_collect_enabled,
                name=service.COLLECT_PERIODIC_TASK_NAME,
                task=service.COLLECT_TASK,
                interval=current.collect_interval_minutes,
            )
            return True

    @classmethod
    def _reconcile_node_configs(cls, config, *, service):
        from apps.cmdb.services.collect_service import CollectModelService

        collect_tasks = service._list_region_collect_tasks(active_only=False)
        if not collect_tasks:
            if config.auto_collect_enabled and not config.auto_sync_enabled:
                return NodeConfigReconcileResult("waiting_sync")
            return NodeConfigReconcileResult("unknown")

        has_tracked_failure = False
        has_untracked_failure = False
        has_contention = False
        valid_region_count = 0
        for collect_task in collect_tasks:
            if config.auto_collect_enabled and not config.auto_sync_enabled and collect_task.is_interval:
                continue
            cloud_region_id = cls._parse_cloud_region_id(
                collect_task.system_code,
                prefix=service.SYSTEM_TASK_PREFIX,
            )
            if cloud_region_id is None:
                has_untracked_failure = True
                logger.error("节点采集参数对账跳过无效区域编码")
                continue

            valid_region_count += 1
            state, created = cls._get_or_create_region_state(config, cloud_region_id, collect_task)
            if not created and not state.node_config_status.endswith("_in_progress"):
                NodeMgmtSyncRegionState.objects.filter(pk=state.pk).update(
                    config=config,
                    config_version=config.version,
                    cloud_region_id=cloud_region_id,
                    collect_task=collect_task,
                )
                state.config = config
                state.config_version = config.version
                state.cloud_region_id = cloud_region_id
                state.collect_task = collect_task
            if not CollectModelService.should_sync_node_params(collect_task):
                state.node_config_status = "disabled"
                state.reason_code = ""
                state.error_message = ""
                state.save(
                    update_fields=[
                        "node_config_status",
                        "reason_code",
                        "error_message",
                        "updated_at",
                    ]
                )
                continue

            desired_enabled = config.auto_collect_enabled and collect_task.is_interval
            claim = cls._claim_node_config_state(
                state,
                auto_collect_enabled=desired_enabled,
            )
            if claim.outcome == "skip":
                continue
            if claim.outcome == "contended":
                has_contention = True
                continue
            stage, claim_token = claim.stage, claim.token

            if stage == "delete":
                try:
                    CollectModelService.delete_butch_node_params(collect_task)
                except Exception as exc:
                    if cls._persist_node_config_failure(
                        state,
                        stage="delete",
                        exc=exc,
                        claim_token=claim_token,
                    ):
                        has_tracked_failure = True
                    else:
                        has_contention = True
                    continue

                if not desired_enabled:
                    if not cls._finish_node_config_claim(
                        state,
                        stage="delete",
                        claim_token=claim_token,
                        next_status="disabled",
                    ):
                        has_contention = True
                    continue

                if not cls._finish_node_config_claim(
                    state,
                    stage="delete",
                    claim_token=claim_token,
                    next_status="push_in_progress",
                    keep_claim=True,
                ):
                    has_contention = True
                    continue
                if state.node_config_status != "push_in_progress":
                    has_contention = True
                    continue

            try:
                CollectModelService.push_butch_node_params(collect_task)
            except Exception as exc:
                if cls._persist_node_config_failure(
                    state,
                    stage="push",
                    exc=exc,
                    claim_token=claim_token,
                ):
                    has_tracked_failure = True
                else:
                    has_contention = True
                continue

            if not cls._finish_node_config_claim(
                state,
                stage="push",
                claim_token=claim_token,
                next_status="healthy",
            ):
                has_contention = True

        if has_untracked_failure:
            return NodeConfigReconcileResult(
                "degraded",
                "NODE_CONFIG_RECONCILE_FAILED",
                "节点采集参数对账存在失败区域",
            )
        if has_tracked_failure:
            return NodeConfigReconcileResult(
                "degraded",
                "NODE_CONFIG_RECONCILE_FAILED",
                "节点采集参数对账存在失败区域",
                guard_region_failure=True,
            )
        if has_contention:
            return NodeConfigReconcileResult(
                config.node_config_status or "unknown",
                contended=True,
            )
        if config.auto_collect_enabled and not config.auto_sync_enabled:
            return NodeConfigReconcileResult("waiting_sync")
        if not valid_region_count:
            return NodeConfigReconcileResult("unknown")
        return NodeConfigReconcileResult("healthy" if config.auto_collect_enabled else "disabled")

    @staticmethod
    def _parse_cloud_region_id(system_code, *, prefix):
        if not isinstance(system_code, str) or not system_code.startswith(prefix):
            return None
        raw_region_id = system_code[len(prefix) :]
        if not raw_region_id or not raw_region_id.isascii() or not raw_region_id.isdecimal():
            return None
        return str(int(raw_region_id))

    @classmethod
    def _claim_node_config_state(cls, state, *, auto_collect_enabled):
        current_time = timezone.now()
        current_status = state.node_config_status
        if (auto_collect_enabled and current_status == "healthy") or (not auto_collect_enabled and current_status == "disabled"):
            return NodeConfigClaimResult("skip")
        if current_status.endswith("_in_progress"):
            if state.updated_at > current_time - cls.NODE_CONFIG_CLAIM_TIMEOUT:
                return NodeConfigClaimResult("contended")
            stage = current_status.removesuffix("_in_progress")
        elif auto_collect_enabled and current_status == "push_pending":
            stage = "push"
        else:
            stage = "delete"

        claim_token = f"NODE_CONFIG_CLAIM:{uuid.uuid4().hex}"
        queryset = NodeMgmtSyncRegionState.objects.filter(
            pk=state.pk,
            config_version=state.config_version,
            node_config_status=current_status,
        )
        if current_status.endswith("_in_progress"):
            queryset = queryset.filter(updated_at__lte=current_time - cls.NODE_CONFIG_CLAIM_TIMEOUT)
        updated = queryset.update(
            node_config_status=f"{stage}_in_progress",
            reason_code=claim_token,
            error_message="",
            updated_at=current_time,
        )
        if not updated:
            return NodeConfigClaimResult("contended")
        state.node_config_status = f"{stage}_in_progress"
        state.reason_code = claim_token
        state.error_message = ""
        state.updated_at = current_time
        return NodeConfigClaimResult("acquired", stage, claim_token)

    @staticmethod
    def _finish_node_config_claim(
        state,
        *,
        stage,
        claim_token,
        next_status,
        keep_claim=False,
    ):
        current_time = timezone.now()
        reason_code = claim_token if keep_claim else ""
        claim = NodeMgmtSyncRegionState.objects.filter(
            pk=state.pk,
            node_config_status=f"{stage}_in_progress",
            reason_code=claim_token,
        )
        dirty_updated = claim.filter(
            error_message=NodeMgmtSyncReconciler.NODE_CONFIG_DIRTY_MARKER,
        ).update(
            node_config_status="delete_pending",
            reason_code="",
            error_message="",
            updated_at=current_time,
        )
        if dirty_updated:
            state.node_config_status = "delete_pending"
            state.reason_code = ""
            state.error_message = ""
            state.updated_at = current_time
            return True
        updated = claim.filter(error_message="").update(
            node_config_status=next_status,
            reason_code=reason_code,
            error_message="",
            updated_at=current_time,
        )
        if updated:
            state.node_config_status = next_status
            state.reason_code = reason_code
            state.error_message = ""
            state.updated_at = current_time
        return bool(updated)

    @staticmethod
    def _persist_node_config_failure(state, *, stage, exc, claim_token):
        reason_code = f"NODE_CONFIG_{stage.upper()}_FAILED"
        stage_label = "删除" if stage == "delete" else "推送"
        error_message = f"{type(exc).__name__}: 节点采集参数{stage_label}失败"
        updated_at = timezone.now()
        claim = NodeMgmtSyncRegionState.objects.filter(
            pk=state.pk,
            node_config_status=f"{stage}_in_progress",
            reason_code=claim_token,
        )
        dirty_updated = claim.filter(
            error_message=NodeMgmtSyncReconciler.NODE_CONFIG_DIRTY_MARKER,
        ).update(
            node_config_status="delete_pending",
            reason_code="",
            error_message="",
            updated_at=updated_at,
        )
        if dirty_updated:
            state.node_config_status = "delete_pending"
            state.reason_code = ""
            state.error_message = ""
            state.updated_at = updated_at
            return True
        updated = claim.filter(error_message="").update(
            node_config_status=f"{stage}_pending",
            reason_code=reason_code,
            error_message=error_message,
            updated_at=updated_at,
        )
        if updated:
            state.node_config_status = f"{stage}_pending"
            state.reason_code = reason_code
            state.error_message = error_message
            state.updated_at = updated_at
        logger.error(
            "节点采集参数%s失败: task_id=%s, error_type=%s",
            stage_label,
            state.collect_task_id,
            type(exc).__name__,
        )
        return bool(updated)

    @classmethod
    def _reconcile_periodic_task(cls, *, enabled: bool, name: str, task: str, interval: int) -> None:
        current = CeleryUtils.get_periodic_task(name)
        if not enabled:
            if current is not None:
                cls._delete_periodic_task(name)
            return

        interval_seconds = int(interval) * 60
        if cls._matches(current, task=task, interval_seconds=interval_seconds):
            return
        CeleryUtils.create_or_update_periodic_task(
            name=name,
            interval=interval_seconds,
            task=task,
            enabled=True,
        )

    @staticmethod
    def _matches(current, *, task: str, interval_seconds: int) -> bool:
        if current is None or current.task != task or not current.enabled:
            return False
        if current.interval_id is None or current.crontab_id is not None or current.solar_id is not None or current.clocked_id is not None:
            return False
        return current.interval.every == interval_seconds and current.interval.period == IntervalSchedule.SECONDS

    @staticmethod
    def _delete_periodic_task(name: str) -> None:
        PeriodicTask.objects.filter(name=name).delete()
        logger.info("删除节点管理同步周期任务: %s", name)

    @staticmethod
    def _persist_health(config, result: NodeMgmtSyncReconcileResult) -> None:
        reconciled_at = timezone.now()
        queryset = config.__class__.objects.filter(
            pk=config.pk,
            version=config.version,
        )
        if result.guard_region_failure:
            queryset = queryset.filter(
                region_states__config_version=config.version,
                region_states__node_config_status__in=(
                    "delete_pending",
                    "push_pending",
                ),
                region_states__reason_code__in=(
                    "NODE_CONFIG_DELETE_FAILED",
                    "NODE_CONFIG_PUSH_FAILED",
                ),
            )
        updated = queryset.update(
            schedule_status=result.schedule_status,
            node_config_status=result.node_config_status,
            last_reconciled_at=reconciled_at,
            reconcile_error_code=result.error_code,
            reconcile_error_message=result.error_message[:255],
        )
        if not updated:
            return
        config.schedule_status = result.schedule_status
        config.node_config_status = result.node_config_status
        config.last_reconciled_at = reconciled_at
        config.reconcile_error_code = result.error_code
        config.reconcile_error_message = result.error_message[:255]
