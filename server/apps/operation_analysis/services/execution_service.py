import logging
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.report_display_time import (
    resolve_creator_timezone,
)
from apps.operation_analysis.services.subscription_service import (
    DashboardSubscriptionService,
)

logger = logging.getLogger(__name__)

IN_FLIGHT_STATUSES = (
    DashboardReportExecution.Status.PENDING,
    DashboardReportExecution.Status.RUNNING,
)


class DashboardReportExecutionService:
    SNAPSHOT_FAILURE_MESSAGE = "Execution Input Snapshot 创建失败"
    IN_FLIGHT_MESSAGE = "订阅已有进行中的报告执行，请稍后再试"

    @classmethod
    @transaction.atomic
    def claim_execution(cls, execution_id: int) -> bool:
        now = timezone.now()
        claimed_count = DashboardReportExecution.objects.filter(
            pk=execution_id,
            status=DashboardReportExecution.Status.PENDING,
        ).update(
            status=DashboardReportExecution.Status.RUNNING,
            started_at=now,
            updated_at=now,
        )
        return claimed_count == 1

    @classmethod
    def transition(
        cls,
        execution: DashboardReportExecution,
        target_status: str,
        *,
        failure_stage: str = "",
        error_message: str = "",
    ) -> DashboardReportExecution:
        if (
            execution.status == DashboardReportExecution.Status.PENDING
            and target_status == DashboardReportExecution.Status.RUNNING
        ):
            raise ValidationError(
                {"status": "pending → running 必须通过 claim_execution"}
            )

        allowed = DashboardReportExecution.ALLOWED_TRANSITIONS.get(
            execution.status,
            set(),
        )
        if target_status not in allowed:
            raise ValidationError(
                {
                    "status": (
                        f"不允许从 {execution.status} 转换到 {target_status}"
                    )
                }
            )

        now = timezone.now()
        execution.status = target_status
        update_fields = ["status", "updated_at"]
        if target_status in {
            DashboardReportExecution.Status.SUCCEEDED,
            DashboardReportExecution.Status.FAILED,
            DashboardReportExecution.Status.UNKNOWN,
        }:
            execution.finished_at = now
            update_fields.append("finished_at")
        if target_status == DashboardReportExecution.Status.FAILED:
            execution.failure_stage = failure_stage
            execution.error_message = error_message
            update_fields.extend(["failure_stage", "error_message"])
        execution.save(update_fields=update_fields)
        return execution

    @staticmethod
    def _snapshot_filter_values(
        subscription: DashboardReportSubscription,
    ) -> dict:
        filter_values = (subscription.config or {}).get("filter_values", {})
        if not isinstance(filter_values, dict):
            raise ValidationError("filter_values 必须是对象")
        return deepcopy(filter_values)

    @staticmethod
    def _normalize_request_id(request_id: str | None) -> str:
        if not isinstance(request_id, str):
            raise DRFValidationError({"request_id": "request_id 必填"})
        normalized = request_id.strip()
        if not normalized:
            raise DRFValidationError({"request_id": "request_id 必填"})
        if len(normalized) > 64:
            raise DRFValidationError(
                {"request_id": "request_id 长度不能超过 64"}
            )
        return normalized

    @classmethod
    def _create_snapshot(
        cls,
        execution: DashboardReportExecution,
        subscription: DashboardReportSubscription,
        *,
        creator_timezone: str,
    ) -> DashboardReportExecutionSnapshot:
        return DashboardReportExecutionSnapshot.objects.create(
            execution=execution,
            dashboard_id=subscription.dashboard_id,
            creator_id=subscription.creator,
            creator_timezone=creator_timezone,
            subscription_id=subscription.id,
            subscription_name=subscription.name,
            recipient_email=subscription.recipient_email,
            trigger_type=execution.trigger_type,
            email_channel_id=subscription.email_channel_id,
            filter_values=cls._snapshot_filter_values(subscription),
        )

    @classmethod
    def _find_by_request_id(
        cls,
        *,
        subscription_id: int,
        request_id: str,
    ) -> DashboardReportExecution | None:
        return DashboardReportExecution.objects.filter(
            subscription_id=subscription_id,
            request_id=request_id,
            trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        ).first()

    @classmethod
    @transaction.atomic
    def execute_manual(
        cls,
        request,
        subscription: DashboardReportSubscription,
        *,
        request_id: str | None = None,
    ) -> tuple[DashboardReportExecution, bool]:
        if subscription.creator != request.user.username:
            raise PermissionDenied("只能执行自己的报告订阅")
        if subscription.dashboard is None:
            raise PermissionDenied("源仪表盘已不存在，不能执行该订阅")

        DashboardSubscriptionService.require_dashboard_view(
            request,
            subscription.dashboard,
        )
        normalized_request_id = cls._normalize_request_id(
            request_id
            if request_id is not None
            else request.data.get("request_id")
        )

        locked_subscription = (
            DashboardReportSubscription.objects.select_for_update().get(
                pk=subscription.pk
            )
        )
        existing = cls._find_by_request_id(
            subscription_id=locked_subscription.id,
            request_id=normalized_request_id,
        )
        if existing is not None:
            return existing, False

        if DashboardReportExecution.objects.filter(
            subscription_id=locked_subscription.id,
            status__in=IN_FLIGHT_STATUSES,
        ).exists():
            raise DRFValidationError(
                {"detail": cls.IN_FLIGHT_MESSAGE}
            )

        creator_timezone = resolve_creator_timezone(
            locked_subscription.creator,
            domain=getattr(request.user, "domain", None),
        )
        try:
            execution = DashboardReportExecution.objects.create(
                subscription=locked_subscription,
                dashboard=locked_subscription.dashboard,
                creator=locked_subscription.creator,
                trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
                request_id=normalized_request_id,
            )
        except IntegrityError:
            existing = cls._find_by_request_id(
                subscription_id=locked_subscription.id,
                request_id=normalized_request_id,
            )
            if existing is not None:
                return existing, False
            raise

        try:
            with transaction.atomic():
                cls._create_snapshot(
                    execution,
                    locked_subscription,
                    creator_timezone=creator_timezone,
                )
        except Exception:
            logger.exception(
                "创建 Execution Input Snapshot 失败: execution_id=%s",
                execution.id,
            )
            cls.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage="snapshot",
                error_message=cls.SNAPSHOT_FAILURE_MESSAGE,
            )
        if execution.status == DashboardReportExecution.Status.PENDING:
            transaction.on_commit(
                lambda: cls._dispatch_render(execution.id)
            )
        return execution, True

    @staticmethod
    def _dispatch_render(execution_id: int) -> None:
        from apps.operation_analysis.tasks.tasks import (
            render_dashboard_report_task,
        )

        try:
            render_dashboard_report_task.delay(execution_id)
        except Exception:
            logger.exception(
                "投递 Dashboard Render Task 失败: execution_id=%s",
                execution_id,
            )
            execution = DashboardReportExecution.objects.filter(
                pk=execution_id,
                status=DashboardReportExecution.Status.PENDING,
            ).first()
            if execution is not None:
                DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.FAILED,
                    failure_stage="render",
                    error_message="报告渲染任务投递失败",
                )
