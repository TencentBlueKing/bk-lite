import logging
import re
import smtplib

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderError,
)
from apps.operation_analysis.services.delivery_channel_service import (
    DashboardReportChannelError,
    DashboardReportDeliveryChannelService,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)

logger = logging.getLogger(__name__)


class DashboardReportDeliveryError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = ""):
        self.error_code = error_code
        super().__init__(message)


def classify_smtp_failure_message(message: str) -> str:
    """将 SMTP 适配器返回文案映射为稳定 error_code。

    仅明确 transient 返回可重试码；未知返回空串 → Classifier terminal_failed。
    """
    lower = (message or "").lower()
    if any(
        token in lower
        for token in (
            "result unknown",
            "status unknown",
            "uncertain",
            "smtp_result_unknown",
        )
    ):
        return "smtp_result_unknown"
    if any(
        token in lower
        for token in ("timed out", "timeout", "time out")
    ):
        return "smtp_timeout"
    if any(
        token in lower
        for token in (
            "connection refused",
            "connection reset",
            "connection aborted",
            "disconnected",
            "network is unreachable",
            "name or service not known",
            "smtpconnect",
            "serverdisconnected",
        )
    ):
        return "smtp_connection_failed"
    if any(
        token in lower
        for token in (
            "authentication",
            "auth failed",
            "mailbox unavailable",
            "user unknown",
            "recipient rejected",
            "relay access denied",
        )
    ) or re.search(r"\b(550|551|552|553|554)\b", lower):
        return "smtp_permanent"
    if re.search(r"\b(421|450|451|452)\b", lower) or any(
        token in lower
        for token in (
            "temporary",
            "try again later",
            "greylist",
            "smtp_transient",
        )
    ):
        return "smtp_transient"
    # 未明确分类：不 retry
    return ""


class DashboardReportDeliveryService:
    @classmethod
    def deliver(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> None:
        if (
            execution.delivery_outcome
            == DashboardReportExecution.DeliveryOutcome.DELIVERED
            or execution.delivered_at is not None
        ):
            DashboardReportExecutionService.mark_delivery_outcome(
                execution,
                DashboardReportExecution.DeliveryOutcome.DELIVERED,
            )
            DashboardReportExecutionService.reconcile_delivery_fact(
                execution,
                source="delivery_worker",
            )
            return

        artifact = cls._resolve_artifact(execution)
        try:
            resolved_channel = DashboardReportDeliveryChannelService.resolve(
                execution, snapshot
            )
        except DashboardReportChannelError as exc:
            raise DashboardReportDeliveryError(
                str(exc), error_code=exc.error_code
            ) from exc
        try:
            pdf_path = DashboardReportRenderService.resolve_artifact_path(
                artifact
            )
        except DashboardRenderError as exc:
            # 产物不可用 → 交给 Classifier 走 render resume
            raise DashboardReportDeliveryError(
                str(exc),
                error_code="pdf_generate_failed",
            ) from exc
        title = cls._build_title(snapshot, execution)
        html = cls._build_html(snapshot, execution)

        from apps.system_mgmt.utils.channel_utils import send_email_to_user

        channel_config = resolved_channel.config
        try:
            result = send_email_to_user(
                channel_config,
                html,
                [snapshot.recipient_email],
                title,
                [
                    {
                        "filename": artifact.filename,
                        "data": pdf_path.read_bytes(),
                    }
                ],
            )
        except (
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError,
            ConnectionError,
            TimeoutError,
            OSError,
        ) as exc:
            raise DashboardReportDeliveryError(
                "SMTP 连接失败",
                error_code="smtp_connection_failed",
            ) from exc
        except smtplib.SMTPAuthenticationError as exc:
            raise DashboardReportDeliveryError(
                "SMTP 认证失败",
                error_code="smtp_permanent",
            ) from exc
        except smtplib.SMTPException as exc:
            raise DashboardReportDeliveryError(
                "SMTP 发送失败",
                error_code=classify_smtp_failure_message(str(exc)),
            ) from exc

        if result is None or not isinstance(result, dict):
            DashboardReportExecutionService.mark_delivery_outcome(
                execution,
                DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
            )
            raise DashboardReportDeliveryError(
                "SMTP 提交结果未知",
                error_code="smtp_result_unknown",
            )
        if result.get("result"):
            DashboardReportExecutionService.mark_delivery_outcome(
                execution,
                DashboardReportExecution.DeliveryOutcome.DELIVERED,
            )
            DashboardReportExecutionService.reconcile_delivery_fact(
                execution,
                source="delivery_worker",
            )
            return

        message = result.get("message") or "邮件发送失败"
        code = classify_smtp_failure_message(str(message))
        if code == "smtp_result_unknown":
            DashboardReportExecutionService.mark_delivery_outcome(
                execution,
                DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
            )
        raise DashboardReportDeliveryError(
            message,
            error_code=code,
        )

    @staticmethod
    def _resolve_artifact(
        execution: DashboardReportExecution,
    ) -> DashboardReportPdfArtifact:
        try:
            return execution.pdf_artifact
        except DashboardReportPdfArtifact.DoesNotExist as exc:
            raise DashboardReportDeliveryError(
                "PDF 产物不存在",
                error_code="pdf_generate_failed",
            ) from exc

    @staticmethod
    def _is_scheduled(
        snapshot: DashboardReportExecutionSnapshot,
        execution: DashboardReportExecution,
    ) -> bool:
        return (
            execution.trigger_type
            == DashboardReportExecution.TriggerType.SCHEDULED
            or snapshot.trigger_type
            == DashboardReportExecution.TriggerType.SCHEDULED
        )

    @classmethod
    def _plan_time_display(
        cls,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> str:
        local = (snapshot.scheduled_local_time or "").strip()
        tz = (snapshot.schedule_timezone or "").strip()
        if local and tz:
            return f"{local} ({tz})"
        return local or tz

    @classmethod
    def _build_title(
        cls,
        snapshot: DashboardReportExecutionSnapshot,
        execution: DashboardReportExecution,
    ) -> str:
        name = snapshot.subscription_name or "报告"
        if cls._is_scheduled(snapshot, execution):
            plan = snapshot.scheduled_local_time or cls._plan_time_display(
                snapshot
            )
            return f"[BK-Lite] {name} - {plan}"
        return f"[BK-Lite] {name} - 手动测试"

    @classmethod
    def _build_html(
        cls,
        snapshot: DashboardReportExecutionSnapshot,
        execution: DashboardReportExecution,
    ) -> str:
        render_snapshot = getattr(execution, "render_snapshot", None)
        canvas_name = (
            render_snapshot.dashboard_name
            if render_snapshot
            else str(
                snapshot.resource_id
                if snapshot.resource_id is not None
                else snapshot.dashboard_id
            )
        )
        canvas_label = (
            getattr(render_snapshot, "resource_display_label", None)
            if render_snapshot
            else None
        ) or getattr(snapshot, "resource_display_label", None) or "仪表盘"
        safe_name = re.sub(r"[<>&]", "", canvas_name)
        safe_sub = re.sub(r"[<>&]", "", snapshot.subscription_name or "")
        parts = [
            f"<p>{canvas_label}：{safe_name}</p>",
            f"<p>订阅名称：{safe_sub}</p>",
        ]
        if cls._is_scheduled(snapshot, execution):
            plan = cls._plan_time_display(snapshot)
            parts.append(f"<p>报告计划时间：{plan}</p>")
        else:
            parts.append("<p>本次为手动测试发送，无计划周期。</p>")
        parts.append("<p>由 BK-Lite 自动生成，请查阅附件。</p>")
        return "".join(parts)
