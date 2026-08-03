from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportRenderSnapshot,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardChromiumRenderer,
    DashboardRenderError,
    DashboardRenderRequest,
)
from apps.operation_analysis.services.render_token_service import (
    DashboardReportRenderTokenService,
)

logger = logging.getLogger(__name__)


class DashboardReportRenderService:
    @staticmethod
    def _artifact_root() -> Path:
        configured = os.getenv("DASHBOARD_REPORT_ARTIFACT_ROOT")
        if configured:
            return Path(configured).expanduser().resolve()
        if not settings.DEBUG:
            raise DashboardRenderError(
                "生产环境必须配置共享 DASHBOARD_REPORT_ARTIFACT_ROOT"
            )
        return (
            Path(tempfile.gettempdir())
            / "bk-lite-dashboard-report-artifacts"
        ).resolve()

    @staticmethod
    def _web_base_url() -> str:
        value = os.getenv("DASHBOARD_REPORT_WEB_BASE_URL", "").rstrip("/")
        if not value:
            raise DashboardRenderError(
                "DASHBOARD_REPORT_WEB_BASE_URL 未配置"
            )
        return value

    @staticmethod
    def _retention_seconds() -> int:
        raw_value = os.getenv(
            "DASHBOARD_REPORT_ARTIFACT_RETENTION_SECONDS",
            "86400",
        )
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise DashboardRenderError("PDF 临时保留期配置无效") from exc
        if value <= 0:
            raise DashboardRenderError("PDF 临时保留期配置无效")
        return value

    @staticmethod
    def _filename(
        dashboard_name: str,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> str:
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", dashboard_name).strip()
        base = safe_name or "dashboard"
        if (
            execution.trigger_type
            == DashboardReportExecution.TriggerType.SCHEDULED
            or snapshot.trigger_type
            == DashboardReportExecution.TriggerType.SCHEDULED
        ):
            local = (snapshot.scheduled_local_time or "").strip()
            if local:
                compact = re.sub(r"[^\d]", "", local)[:12]
                if len(compact) >= 12:
                    time_part = f"{compact[:8]}_{compact[8:12]}"
                else:
                    time_part = compact or "scheduled"
            else:
                time_part = "scheduled"
            return f"{base}_{time_part}.pdf"
        return f"{base}_手动测试.pdf"

    @classmethod
    def resolve_artifact_path(
        cls,
        artifact: DashboardReportPdfArtifact,
    ) -> Path:
        if artifact.expires_at <= timezone.now():
            raise DashboardRenderError("PDF 临时产物已过期")
        root = cls._artifact_root()
        path = (root / artifact.storage_reference).resolve()
        if root not in path.parents:
            raise DashboardRenderError("PDF 临时存储引用无效")
        return path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def render(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
        render_snapshot: DashboardReportRenderSnapshot,
    ) -> DashboardReportPdfArtifact:
        existing = cls._reusable_artifact(execution)
        if existing is not None:
            return existing

        if (
            snapshot.execution_id != execution.id
            or render_snapshot.execution_id != execution.id
        ):
            raise DashboardRenderError(
                "Render Snapshot 与 Execution 不匹配",
                error_code="render_snapshot_corrupt",
            )

        artifact_root = cls._artifact_root()
        artifact_root.mkdir(parents=True, exist_ok=True)
        storage_reference = f"execution-{execution.id}/report.pdf"
        final_path = artifact_root / storage_reference
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = artifact_root / (
            f".execution-{execution.id}-{uuid4().hex}.tmp.pdf"
        )
        render_url = (
            f"{cls._web_base_url()}/ops-analysis/render/execution/"
            f"{execution.id}"
        )
        viewport = {}
        if isinstance(render_snapshot.view_sets, dict):
            viewport = render_snapshot.view_sets.get("viewport") or {}
        request = DashboardRenderRequest(
            execution_id=execution.id,
            render_url=render_url,
            output_path=temporary_path,
            render_token=DashboardReportRenderTokenService.issue(
                execution,
                attempt_no=execution.attempt_count or 1,
            ).plaintext,
            resource_type=(
                execution.resource_type
                or render_snapshot.resource_type
                or "dashboard"
            ),
            viewport_width=(
                int(viewport["width"])
                if viewport.get("width") is not None
                else None
            ),
            viewport_height=(
                int(viewport["height"])
                if viewport.get("height") is not None
                else None
            ),
        )

        try:
            DashboardChromiumRenderer().render(request)
            size_bytes = temporary_path.stat().st_size
            sha256 = cls._sha256(temporary_path)
            os.replace(temporary_path, final_path)
            with transaction.atomic():
                return DashboardReportPdfArtifact.objects.create(
                    execution=execution,
                    storage_reference=storage_reference,
                    filename=cls._filename(
                        render_snapshot.dashboard_name,
                        execution,
                        snapshot,
                    ),
                    size_bytes=size_bytes,
                    sha256=sha256,
                    expires_at=timezone.now()
                    + timedelta(seconds=cls._retention_seconds()),
                )
        except Exception:
            temporary_path.unlink(missing_ok=True)
            if not DashboardReportPdfArtifact.objects.filter(
                execution=execution
            ).exists():
                final_path.unlink(missing_ok=True)
            raise

    @classmethod
    def _reusable_artifact(
        cls,
        execution: DashboardReportExecution,
    ) -> DashboardReportPdfArtifact | None:
        """仅复用未过期且文件可读的 Artifact；不可用则清除后重渲。"""
        try:
            artifact = execution.pdf_artifact
        except DashboardReportPdfArtifact.DoesNotExist:
            return None
        if artifact.expires_at <= timezone.now():
            cls._discard_artifact(artifact)
            return None
        try:
            cls.resolve_artifact_path(artifact)
        except Exception:
            cls._discard_artifact(artifact)
            return None
        return artifact

    @classmethod
    def _discard_artifact(
        cls,
        artifact: DashboardReportPdfArtifact,
    ) -> None:
        try:
            path = cls._artifact_root() / artifact.storage_reference
            path.unlink(missing_ok=True)
        except Exception:
            logger.warning(
                "清理不可用 PDF 产物失败: artifact_id=%s",
                artifact.id,
                exc_info=True,
            )
        artifact.delete()