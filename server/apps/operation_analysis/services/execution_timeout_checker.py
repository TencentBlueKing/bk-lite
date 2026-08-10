from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.resource_state import (
    observe_resource_state,
)

logger = logging.getLogger(__name__)

# 三次 Chromium 渲染每次最多 120 秒；额外一分钟留给 Snapshot、PDF 与投递。
# 显式环境配置仍可按部署规模覆盖该默认值。
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 420
DEFAULT_EXECUTION_TIMEOUT_GRACE_SECONDS = 30
DEFAULT_CLAIM_TIMEOUT_SECONDS = 60


def execution_timeout_seconds() -> int:
    raw = os.getenv(
        "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS",
        str(DEFAULT_EXECUTION_TIMEOUT_SECONDS),
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_EXECUTION_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_EXECUTION_TIMEOUT_SECONDS


def execution_timeout_grace_seconds() -> int:
    raw = os.getenv(
        "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS",
        str(DEFAULT_EXECUTION_TIMEOUT_GRACE_SECONDS),
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_EXECUTION_TIMEOUT_GRACE_SECONDS
    return value if value >= 0 else DEFAULT_EXECUTION_TIMEOUT_GRACE_SECONDS


def claim_timeout_seconds() -> int:
    raw = os.getenv(
        "DASHBOARD_REPORT_CLAIM_TIMEOUT_SECONDS",
        str(DEFAULT_CLAIM_TIMEOUT_SECONDS),
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CLAIM_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_CLAIM_TIMEOUT_SECONDS


@dataclass(frozen=True)
class TimeoutSweepStats:
    scanned: int = 0
    failed: int = 0
    succeeded: int = 0
    unknown: int = 0
    skipped: int = 0


class ExecutionTimeoutChecker:
    """orphan / 超时 running 的最终收敛；不重 claim、不重发、不补漏期。"""

    @classmethod
    def is_past_deadline(
        cls,
        execution: DashboardReportExecution,
        *,
        now=None,
    ) -> bool:
        now = now or timezone.now()
        anchor = execution.started_at or execution.created_at
        if anchor is None:
            return False
        timeout = (
            claim_timeout_seconds()
            if execution.attempt_count == 0
            else execution_timeout_seconds()
        )
        budget = timeout + execution_timeout_grace_seconds()
        return anchor <= now - timedelta(seconds=budget)

    @classmethod
    def converge_one(
        cls,
        execution: DashboardReportExecution,
    ) -> str:
        """对单个 Execution 做 timeout / 投递事实对齐。"""
        execution.refresh_from_db()
        resource = observe_resource_state(execution)

        # 投递事实优先于 timeout failed：CAS 前先按 outcome 对齐
        if resource.delivery_outcome == "delivered":
            DashboardReportExecutionService.reconcile_delivery_fact(
                execution,
                source="timeout_checker",
            )
            execution.refresh_from_db()
            return (
                "succeeded"
                if execution.status
                == DashboardReportExecution.Status.SUCCEEDED
                else "skipped"
            )
        if resource.delivery_outcome == "smtp_unknown":
            DashboardReportExecutionService.reconcile_delivery_fact(
                execution,
                source="timeout_checker",
            )
            execution.refresh_from_db()
            return (
                "unknown"
                if execution.status
                == DashboardReportExecution.Status.UNKNOWN
                else "skipped"
            )

        if execution.status != DashboardReportExecution.Status.RUNNING:
            return "skipped"

        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.FAILED,
            failure_stage="schedule",
            error_code="execution_timeout",
            error_message="Execution 总超时",
        )
        try:
            from apps.operation_analysis.services.render_token_service import (
                DashboardReportRenderTokenService,
            )

            DashboardReportRenderTokenService.revoke_current(execution)
        except Exception:
            logger.warning(
                "timeout 收敛后废止 Render Token 失败: execution_id=%s",
                execution.id,
                exc_info=True,
            )
        return "failed"

    @classmethod
    def sweep(cls) -> TimeoutSweepStats:
        now = timezone.now()
        grace = execution_timeout_grace_seconds()
        execution_cutoff = now - timedelta(
            seconds=execution_timeout_seconds() + grace
        )
        claim_cutoff = now - timedelta(
            seconds=claim_timeout_seconds() + grace
        )
        # running 超时候选 + 投递事实与 status 不一致的修复候选
        candidates = list(
            DashboardReportExecution.objects.filter(
                Q(
                    status=DashboardReportExecution.Status.RUNNING,
                )
                & (
                    Q(
                        attempt_count=0,
                        started_at__lte=claim_cutoff,
                    )
                    | Q(
                        attempt_count=0,
                        started_at__isnull=True,
                        created_at__lte=claim_cutoff,
                    )
                    | Q(
                        attempt_count__gt=0,
                        started_at__lte=execution_cutoff,
                    )
                    | Q(
                        attempt_count__gt=0,
                        started_at__isnull=True,
                        created_at__lte=execution_cutoff,
                    )
                )
                | Q(
                    delivery_outcome=(
                        DashboardReportExecution.DeliveryOutcome.DELIVERED
                    ),
                    status__in={
                        DashboardReportExecution.Status.RUNNING,
                        DashboardReportExecution.Status.FAILED,
                        DashboardReportExecution.Status.UNKNOWN,
                    },
                )
                | Q(
                    delivery_outcome=(
                        DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN
                    ),
                    status__in={
                        DashboardReportExecution.Status.RUNNING,
                        DashboardReportExecution.Status.FAILED,
                    },
                )
            )
            .select_related(
                "snapshot",
                "render_snapshot",
                "pdf_artifact",
            )
            .order_by("id")[:200]
        )
        stats = TimeoutSweepStats(scanned=len(candidates))
        counters = {
            "failed": 0,
            "succeeded": 0,
            "unknown": 0,
            "skipped": 0,
        }
        for execution in candidates:
            try:
                action = cls.converge_one(execution)
            except Exception:
                logger.exception(
                    "Execution timeout 收敛失败: execution_id=%s",
                    execution.id,
                )
                counters["skipped"] += 1
                continue
            counters[action] = counters.get(action, 0) + 1
        return TimeoutSweepStats(
            scanned=stats.scanned,
            failed=counters["failed"],
            succeeded=counters["succeeded"],
            unknown=counters["unknown"],
            skipped=counters["skipped"],
        )
