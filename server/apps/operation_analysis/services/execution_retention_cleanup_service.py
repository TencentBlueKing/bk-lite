"""Execution / Snapshot 保留期清理（A8 / D4）。

可删谓词：
  status ∈ {succeeded, failed, unknown}
  AND coalesce(finished_at, created_at) <= now - retention_days

禁止删除 pending / running。
不删除 Subscription 及生命周期审计字段。

动作：分批删除 Execution；CASCADE 清理 Snapshot / Token / Artifact 行；
尽量删除磁盘目录 execution-{id}/。
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)

logger = logging.getLogger(__name__)

DEFAULT_EXECUTION_RETENTION_DAYS = 180
DEFAULT_EXECUTION_CLEANUP_BATCH_SIZE = 200

TERMINAL_STATUSES = (
    DashboardReportExecution.Status.SUCCEEDED,
    DashboardReportExecution.Status.FAILED,
    DashboardReportExecution.Status.UNKNOWN,
)


def execution_retention_days() -> int:
    raw = os.getenv(
        "DASHBOARD_REPORT_EXECUTION_RETENTION_DAYS",
        str(DEFAULT_EXECUTION_RETENTION_DAYS),
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_EXECUTION_RETENTION_DAYS
    return value if value > 0 else DEFAULT_EXECUTION_RETENTION_DAYS


@dataclass(frozen=True)
class ExecutionRetentionCleanupStats:
    scanned: int = 0
    deleted: int = 0
    errors: int = 0
    retention_days: int = DEFAULT_EXECUTION_RETENTION_DAYS


class ExecutionRetentionCleanupService:
    @classmethod
    def cutoff(
        cls,
        *,
        now: datetime | None = None,
        retention_days: int | None = None,
    ) -> datetime:
        moment = now or timezone.now()
        days = (
            retention_days
            if retention_days is not None
            else execution_retention_days()
        )
        return moment - timedelta(days=days)

    @classmethod
    def eligible_queryset(
        cls,
        *,
        now: datetime | None = None,
        retention_days: int | None = None,
    ):
        cutoff = cls.cutoff(now=now, retention_days=retention_days)
        return (
            DashboardReportExecution.objects.filter(
                status__in=TERMINAL_STATUSES,
            )
            .annotate(
                retention_anchor=Coalesce("finished_at", "created_at"),
            )
            .filter(retention_anchor__lte=cutoff)
            .order_by("retention_anchor", "id")
        )

    @classmethod
    def cleanup(
        cls,
        *,
        now: datetime | None = None,
        retention_days: int | None = None,
        limit: int = DEFAULT_EXECUTION_CLEANUP_BATCH_SIZE,
    ) -> ExecutionRetentionCleanupStats:
        days = (
            retention_days
            if retention_days is not None
            else execution_retention_days()
        )
        executions = list(
            cls.eligible_queryset(now=now, retention_days=days)[:limit]
        )
        deleted = 0
        errors = 0

        for execution in executions:
            try:
                cls._cleanup_one(execution)
                deleted += 1
            except Exception:
                errors += 1
                logger.exception(
                    "Execution retention cleanup failed: execution_id=%s",
                    execution.id,
                )

        stats = ExecutionRetentionCleanupStats(
            scanned=len(executions),
            deleted=deleted,
            errors=errors,
            retention_days=days,
        )
        if stats.scanned:
            logger.info(
                "ExecutionRetentionCleanup finished: scanned=%s deleted=%s "
                "errors=%s retention_days=%s",
                stats.scanned,
                stats.deleted,
                stats.errors,
                stats.retention_days,
            )
        return stats

    @classmethod
    def _cleanup_one(cls, execution: DashboardReportExecution) -> None:
        execution_id = execution.id
        cls._remove_artifact_dir(execution_id)
        execution.delete()

    @classmethod
    def _remove_artifact_dir(cls, execution_id: int) -> None:
        try:
            root = DashboardReportRenderService._artifact_root()
            directory = (root / f"execution-{execution_id}").resolve()
            if root not in directory.parents and directory != root:
                logger.warning(
                    "跳过非法 artifact 目录: execution_id=%s",
                    execution_id,
                )
                return
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
            elif directory.is_file():
                directory.unlink(missing_ok=True)
        except Exception:
            logger.warning(
                "删除 Execution artifact 目录失败: execution_id=%s",
                execution_id,
                exc_info=True,
            )
