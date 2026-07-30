from __future__ import annotations

import hashlib
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
from apps.operation_analysis.services.report_display_time import (
    format_report_local_time,
)
from apps.operation_analysis.services.render_token_service import (
    DashboardReportRenderTokenService,
)


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
        creator_timezone: str,
    ) -> str:
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", dashboard_name).strip()
        time_str = format_report_local_time(
            execution.created_at,
            creator_timezone,
            "%Y%m%d_%H%M%S",
        )
        return f"{safe_name or 'dashboard'}_{time_str}.pdf"

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
        try:
            return execution.pdf_artifact
        except DashboardReportPdfArtifact.DoesNotExist:
            pass

        if (
            snapshot.execution_id != execution.id
            or render_snapshot.execution_id != execution.id
        ):
            raise DashboardRenderError("Render Snapshot 与 Execution 不匹配")

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
        request = DashboardRenderRequest(
            execution_id=execution.id,
            render_url=render_url,
            output_path=temporary_path,
            render_token=DashboardReportRenderTokenService.issue(
                execution
            ).plaintext,
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
                        snapshot.creator_timezone,
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
