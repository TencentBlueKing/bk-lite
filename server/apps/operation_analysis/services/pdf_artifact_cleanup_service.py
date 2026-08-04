"""PDF artifact 短期清理（A7 / D4）。

安全谓词（全部满足才删）：
1. artifact.expires_at <= now
2. 所属 Execution status ∈ {succeeded, failed, unknown}
明确不删 pending / running（即使 expires_at 已过）。

动作：删磁盘文件 + 删 DB 行（与 RenderService._discard_artifact 一致）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportPdfArtifact,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_CLEANUP_BATCH_SIZE = 200

TERMINAL_STATUSES = (
    DashboardReportExecution.Status.SUCCEEDED,
    DashboardReportExecution.Status.FAILED,
    DashboardReportExecution.Status.UNKNOWN,
)


@dataclass(frozen=True)
class PdfArtifactCleanupStats:
    scanned: int = 0
    deleted: int = 0
    file_missing: int = 0
    errors: int = 0


class PdfArtifactCleanupService:
    @classmethod
    def eligible_queryset(cls, *, now: datetime | None = None):
        moment = now or timezone.now()
        return (
            DashboardReportPdfArtifact.objects.filter(
                expires_at__lte=moment,
                execution__status__in=TERMINAL_STATUSES,
            )
            .exclude(
                execution__status__in=(
                    DashboardReportExecution.Status.PENDING,
                    DashboardReportExecution.Status.RUNNING,
                )
            )
            .select_related("execution")
            .order_by("expires_at", "id")
        )

    @classmethod
    def cleanup(
        cls,
        *,
        now: datetime | None = None,
        limit: int = DEFAULT_ARTIFACT_CLEANUP_BATCH_SIZE,
    ) -> PdfArtifactCleanupStats:
        moment = now or timezone.now()
        artifacts = list(cls.eligible_queryset(now=moment)[:limit])
        deleted = 0
        file_missing = 0
        errors = 0

        for artifact in artifacts:
            try:
                result = cls._cleanup_one(artifact)
                if result == "deleted":
                    deleted += 1
                elif result == "file_missing":
                    deleted += 1
                    file_missing += 1
            except Exception:
                errors += 1
                logger.exception(
                    "PDF artifact cleanup failed: artifact_id=%s "
                    "execution_id=%s",
                    artifact.id,
                    artifact.execution_id,
                )

        stats = PdfArtifactCleanupStats(
            scanned=len(artifacts),
            deleted=deleted,
            file_missing=file_missing,
            errors=errors,
        )
        if stats.scanned:
            logger.info(
                "PdfArtifactCleanup finished: scanned=%s deleted=%s "
                "file_missing=%s errors=%s",
                stats.scanned,
                stats.deleted,
                stats.file_missing,
                stats.errors,
            )
        return stats

    @classmethod
    def _cleanup_one(cls, artifact: DashboardReportPdfArtifact) -> str:
        """删文件（缺文件幂等）后删 DB 行。返回 deleted | file_missing。"""
        root = DashboardReportRenderService._artifact_root()
        path = (root / artifact.storage_reference).resolve()
        file_was_missing = False

        if root not in path.parents and path != root:
            logger.warning(
                "跳过非法 storage_reference: artifact_id=%s ref=%s",
                artifact.id,
                artifact.storage_reference,
            )
        else:
            try:
                if path.is_file():
                    path.unlink()
                else:
                    file_was_missing = True
                # 尽量去掉空的 execution-{id}/ 目录
                parent = path.parent
                if parent != root and parent.is_dir():
                    try:
                        parent.rmdir()
                    except OSError:
                        pass
            except Exception:
                logger.warning(
                    "删除 PDF 文件失败（继续删 DB 行）: artifact_id=%s path=%s",
                    artifact.id,
                    path,
                    exc_info=True,
                )

        artifact.delete()
        return "file_missing" if file_was_missing else "deleted"
