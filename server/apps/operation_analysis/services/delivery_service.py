import logging
import re

from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderError,
)
from apps.operation_analysis.services.report_display_time import (
    format_report_local_time,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)
from apps.system_mgmt.models import Channel

logger = logging.getLogger(__name__)


class DashboardReportDeliveryError(RuntimeError):
    pass


class DashboardReportDeliveryService:
    @classmethod
    def deliver(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> None:
        if execution.delivered_at is not None:
            return

        artifact = cls._resolve_artifact(execution)
        channel = cls._resolve_channel(snapshot)
        try:
            pdf_path = DashboardReportRenderService.resolve_artifact_path(
                artifact
            )
        except DashboardRenderError as exc:
            raise DashboardReportDeliveryError(str(exc)) from exc
        title = cls._build_title(snapshot, execution)
        html = cls._build_html(snapshot, execution)

        from apps.system_mgmt.utils.channel_utils import send_email_to_user

        channel_config = dict(channel.config or {})
        Channel.decrypt_field("smtp_pwd", channel_config)
        result = send_email_to_user(
            channel_config,
            html,
            [snapshot.recipient_email],
            title,
            [{"filename": artifact.filename, "data": pdf_path.read_bytes()}],
        )
        if not result or not result.get("result"):
            message = (result or {}).get("message", "邮件发送失败")
            raise DashboardReportDeliveryError(message)

        execution.delivered_at = timezone.now()
        execution.save(update_fields=["delivered_at", "updated_at"])

    @staticmethod
    def _resolve_artifact(
        execution: DashboardReportExecution,
    ) -> DashboardReportPdfArtifact:
        try:
            return execution.pdf_artifact
        except DashboardReportPdfArtifact.DoesNotExist as exc:
            raise DashboardReportDeliveryError(
                "PDF 产物不存在"
            ) from exc

    @staticmethod
    def _resolve_channel(
        snapshot: DashboardReportExecutionSnapshot,
    ) -> Channel:
        if snapshot.email_channel_id is None:
            raise DashboardReportDeliveryError("邮件通道未配置")
        channel = Channel.objects.filter(
            id=snapshot.email_channel_id,
            channel_type="email",
        ).first()
        if channel is None:
            raise DashboardReportDeliveryError(
                "邮件通道不存在或类型不是 email"
            )
        return channel

    @staticmethod
    def _build_title(
        snapshot: DashboardReportExecutionSnapshot,
        execution: DashboardReportExecution,
    ) -> str:
        time_str = format_report_local_time(
            execution.created_at,
            snapshot.creator_timezone,
            "%Y-%m-%d %H:%M",
        )
        name = snapshot.subscription_name or "报告"
        return f"[BK-Lite] {name} - {time_str}"

    @staticmethod
    def _build_html(
        snapshot: DashboardReportExecutionSnapshot,
        execution: DashboardReportExecution,
    ) -> str:
        time_str = format_report_local_time(
            execution.created_at,
            snapshot.creator_timezone,
            "%Y-%m-%d %H:%M:%S",
        )
        render_snapshot = getattr(execution, "render_snapshot", None)
        dashboard_name = (
            render_snapshot.dashboard_name
            if render_snapshot
            else str(snapshot.dashboard_id)
        )
        safe_name = re.sub(r"[<>&]", "", dashboard_name)
        safe_sub = re.sub(r"[<>&]", "", snapshot.subscription_name or "")
        return (
            f"<p>仪表盘：{safe_name}</p>"
            f"<p>订阅名称：{safe_sub}</p>"
            f"<p>报告生成时间：{time_str}</p>"
            "<p>由 BK-Lite 自动生成，请查阅附件。</p>"
        )
