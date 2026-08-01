import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

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
from apps.operation_analysis.services.schedule_calculator import (
    ScheduleSpec,
    catch_up_scheduled_time,
    next_run_strictly_after_now,
)
from apps.operation_analysis.services.subscription_service import (
    DashboardSubscriptionService,
)

logger = logging.getLogger(__name__)

IN_FLIGHT_STATUSES = (
    DashboardReportExecution.Status.PENDING,
    DashboardReportExecution.Status.RUNNING,
)


@dataclass(frozen=True)
class CreateScheduledResult:
    """DueSubscriptionScanner 专用创建结果。"""

    execution: DashboardReportExecution | None
    created: bool
    skipped_in_flight: bool = False
    already_exists: bool = False


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

    TERMINAL_STATUSES = frozenset(
        {
            DashboardReportExecution.Status.SUCCEEDED,
            DashboardReportExecution.Status.FAILED,
            DashboardReportExecution.Status.UNKNOWN,
        }
    )

    @classmethod
    def transition(
        cls,
        execution: DashboardReportExecution,
        target_status: str,
        *,
        failure_stage: str = "",
        error_code: str = "",
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
        if (
            execution.status == DashboardReportExecution.Status.RUNNING
            and target_status in cls.TERMINAL_STATUSES
        ):
            return cls._cas_running_to_terminal(
                execution,
                target_status,
                now=now,
                failure_stage=failure_stage,
                error_code=error_code,
                error_message=error_message,
            )

        execution.status = target_status
        update_fields = ["status", "updated_at"]
        if target_status in cls.TERMINAL_STATUSES:
            execution.finished_at = now
            update_fields.append("finished_at")
        if target_status == DashboardReportExecution.Status.FAILED:
            execution.failure_stage = failure_stage
            execution.error_code = error_code
            execution.error_message = error_message
            update_fields.extend(
                ["failure_stage", "error_code", "error_message"]
            )
        elif target_status == DashboardReportExecution.Status.UNKNOWN:
            execution.failure_stage = failure_stage
            execution.error_code = error_code or "smtp_result_unknown"
            execution.error_message = error_message
            update_fields.extend(
                ["failure_stage", "error_code", "error_message"]
            )
        execution.save(update_fields=update_fields)
        return execution

    @classmethod
    def _cas_running_to_terminal(
        cls,
        execution: DashboardReportExecution,
        target_status: str,
        *,
        now,
        failure_stage: str = "",
        error_code: str = "",
        error_message: str = "",
    ) -> DashboardReportExecution:
        """仅当 status 仍为 running 时写入终态；冲突则 no-op 并 refresh。"""
        updates = {
            "status": target_status,
            "finished_at": now,
            "updated_at": now,
        }
        if target_status == DashboardReportExecution.Status.FAILED:
            updates["failure_stage"] = failure_stage
            updates["error_code"] = error_code
            updates["error_message"] = error_message
        elif target_status == DashboardReportExecution.Status.UNKNOWN:
            updates["failure_stage"] = failure_stage
            updates["error_code"] = error_code or "smtp_result_unknown"
            updates["error_message"] = error_message

        updated = DashboardReportExecution.objects.filter(
            pk=execution.pk,
            status=DashboardReportExecution.Status.RUNNING,
        ).update(**updates)
        execution.refresh_from_db()
        if updated != 1:
            logger.info(
                "Execution 终态 CAS 未生效（可能已被并发收敛）: "
                "execution_id=%s target=%s current=%s",
                execution.id,
                target_status,
                execution.status,
            )
        return execution

    @classmethod
    def begin_attempt(
        cls,
        execution: DashboardReportExecution,
    ) -> int:
        """Attempt 开始时递增 attempt_count，返回新序号。"""
        from django.db.models import F

        DashboardReportExecution.objects.filter(pk=execution.pk).update(
            attempt_count=F("attempt_count") + 1,
            updated_at=timezone.now(),
        )
        execution.refresh_from_db(fields=["attempt_count", "updated_at"])
        return execution.attempt_count

    @classmethod
    def mark_delivery_outcome(
        cls,
        execution: DashboardReportExecution,
        outcome: str,
    ) -> DashboardReportExecution:
        """写入 durable 投递事实；不经 status 状态机，不复用 error_code。"""
        now = timezone.now()
        allowed = {
            DashboardReportExecution.DeliveryOutcome.DELIVERED,
            DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
        }
        if outcome not in allowed:
            raise ValidationError(
                {"delivery_outcome": f"不允许标记为 {outcome}"}
            )

        updates = {
            "delivery_outcome": outcome,
            "updated_at": now,
        }
        if outcome == DashboardReportExecution.DeliveryOutcome.DELIVERED:
            updates["delivered_at"] = now

        # 已 delivered 不可降级为 smtp_unknown
        filter_q = DashboardReportExecution.objects.filter(pk=execution.pk)
        if outcome == DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN:
            filter_q = filter_q.exclude(
                delivery_outcome=(
                    DashboardReportExecution.DeliveryOutcome.DELIVERED
                )
            )
        filter_q.update(**updates)
        execution.refresh_from_db()
        return execution

    @classmethod
    def reconcile_delivery_fact(
        cls,
        execution: DashboardReportExecution,
        *,
        source: str,
    ) -> DashboardReportExecution:
        """以持久化 Delivery Fact 仲裁 timeout/SMTP 竞态。

        不变量：
        - running 可按 Delivery Fact 收敛到终态；
        - 仅 execution_timeout / smtp_unknown 竞态允许受控终态修正；
        - permission/snapshot/render 等业务失败不得复活。
        """
        execution.refresh_from_db()
        now = timezone.now()
        outcome = execution.delivery_outcome
        if (
            outcome == DashboardReportExecution.DeliveryOutcome.DELIVERED
            or execution.delivered_at is not None
        ):
            original_status = execution.status
            allowed = original_status == DashboardReportExecution.Status.RUNNING
            allowed = allowed or (
                original_status == DashboardReportExecution.Status.FAILED
                and execution.error_code == "execution_timeout"
            )
            allowed = allowed or (
                original_status == DashboardReportExecution.Status.UNKNOWN
                and execution.error_code == "smtp_result_unknown"
            )
            if not allowed:
                return execution
            updates = dict(
                status=DashboardReportExecution.Status.SUCCEEDED,
                finished_at=now,
                updated_at=now,
                failure_stage="",
                error_code="",
                error_message="",
                delivery_outcome=(
                    DashboardReportExecution.DeliveryOutcome.DELIVERED
                ),
            )
            if original_status in cls.TERMINAL_STATUSES:
                updates.update(
                    reconciled_from_status=original_status,
                    reconciliation_reason="delivery_confirmed_after_terminal",
                    reconciliation_source=source,
                    reconciled_at=now,
                )
            updated = DashboardReportExecution.objects.filter(
                pk=execution.pk,
                status=original_status,
                delivery_outcome=DashboardReportExecution.DeliveryOutcome.DELIVERED,
            ).update(**updates)
            execution.refresh_from_db()
            if updated:
                logger.info(
                    "按 delivery_outcome=delivered 对齐 status=succeeded: "
                    "execution_id=%s",
                    execution.id,
                )
            return execution

        if (
            outcome
            == DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN
        ):
            original_status = execution.status
            allowed = original_status == DashboardReportExecution.Status.RUNNING
            allowed = allowed or (
                original_status == DashboardReportExecution.Status.FAILED
                and execution.error_code == "execution_timeout"
            )
            if not allowed:
                return execution
            updates = dict(
                status=DashboardReportExecution.Status.UNKNOWN,
                finished_at=now,
                updated_at=now,
                failure_stage="email",
                error_code="smtp_result_unknown",
                error_message="SMTP 提交结果未知",
                delivery_outcome=(
                    DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN
                ),
            )
            if original_status in cls.TERMINAL_STATUSES:
                updates.update(
                    reconciled_from_status=original_status,
                    reconciliation_reason="smtp_unknown_after_terminal",
                    reconciliation_source=source,
                    reconciled_at=now,
                )
            updated = DashboardReportExecution.objects.filter(
                pk=execution.pk,
                status=original_status,
                delivery_outcome=DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
            ).update(**updates)
            execution.refresh_from_db()
            if updated:
                logger.info(
                    "按 delivery_outcome=smtp_unknown 对齐 status=unknown: "
                    "execution_id=%s",
                    execution.id,
                )
            return execution

        return execution

    @staticmethod
    def _snapshot_filter_payload(
        subscription: DashboardReportSubscription,
        execution: DashboardReportExecution,
    ) -> tuple[dict, dict]:
        from apps.operation_analysis.services.filter_snapshot import (
            FilterSnapshotError,
        )
        from apps.operation_analysis.services.filter_snapshot_resolver import (
            resolve_filter_snapshot,
        )

        if (
            execution.trigger_type
            == DashboardReportExecution.TriggerType.SCHEDULED
            and execution.scheduled_time_utc is not None
        ):
            reference_at = execution.scheduled_time_utc
        else:
            reference_at = timezone.now()

        try:
            return resolve_filter_snapshot(
                subscription.config,
                reference_at=reference_at,
                timezone_name=subscription.timezone,
            )
        except FilterSnapshotError as exc:
            raise ValidationError(str(exc)) from exc

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
    def _schedule_snapshot_fields(
        cls,
        execution: DashboardReportExecution,
        subscription: DashboardReportSubscription,
    ) -> dict:
        if (
            execution.trigger_type
            != DashboardReportExecution.TriggerType.SCHEDULED
        ):
            return {
                "scheduled_time_utc": None,
                "schedule_timezone": "",
                "scheduled_local_time": "",
                "subscription_version": subscription.version,
            }
        from zoneinfo import ZoneInfo

        scheduled = execution.scheduled_time_utc
        tz_name = subscription.timezone or ""
        local_display = ""
        if scheduled is not None and tz_name:
            local = scheduled.astimezone(ZoneInfo(tz_name))
            local_display = local.strftime("%Y-%m-%d %H:%M")
        return {
            "scheduled_time_utc": scheduled,
            "schedule_timezone": tz_name,
            "scheduled_local_time": local_display,
            "subscription_version": subscription.version,
        }

    @classmethod
    def _create_snapshot(
        cls,
        execution: DashboardReportExecution,
        subscription: DashboardReportSubscription,
        *,
        creator_timezone: str,
    ) -> DashboardReportExecutionSnapshot:
        schedule_fields = cls._schedule_snapshot_fields(
            execution, subscription
        )
        filter_semantics, filter_values = cls._snapshot_filter_payload(
            subscription, execution
        )
        return DashboardReportExecutionSnapshot.objects.create(
            execution=execution,
            dashboard_id=subscription.dashboard_id,
            creator_id=subscription.creator,
            creator_domain=subscription.creator_domain,
            creator_timezone=creator_timezone,
            subscription_id=subscription.id,
            subscription_name=subscription.name,
            recipient_email=subscription.recipient_email,
            trigger_type=execution.trigger_type,
            email_channel_id=subscription.email_channel_id,
            execution_team_id=subscription.team_id,
            subscription_revision=subscription.revision,
            filter_values=filter_values,
            filter_semantics=filter_semantics,
            **schedule_fields,
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
    def _find_scheduled(
        cls,
        *,
        subscription_id: int,
        scheduled_time_utc: datetime,
    ) -> DashboardReportExecution | None:
        return DashboardReportExecution.objects.filter(
            subscription_id=subscription_id,
            scheduled_time_utc=scheduled_time_utc,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        ).first()

    @classmethod
    def _subscription_schedule_spec(
        cls,
        subscription: DashboardReportSubscription,
    ) -> ScheduleSpec:
        return ScheduleSpec(
            schedule_type=subscription.schedule_type,
            hour=subscription.schedule_hour,
            minute=subscription.schedule_minute,
            weekday=subscription.schedule_weekday,
            day_of_month=subscription.schedule_day_of_month,
        )

    @classmethod
    def _advance_subscription_next_run(
        cls,
        subscription: DashboardReportSubscription,
        *,
        scheduled_time_utc: datetime,
        now: datetime,
    ) -> None:
        spec = cls._subscription_schedule_spec(subscription)
        advanced = next_run_strictly_after_now(
            spec,
            subscription.timezone,
            after_scheduled_time_utc=scheduled_time_utc,
            now=now,
        )
        subscription.next_run_at = advanced.utc
        subscription.save(update_fields=["next_run_at", "updated_at"])

    @classmethod
    @transaction.atomic
    def execute_manual(
        cls,
        request,
        subscription: DashboardReportSubscription,
        *,
        request_id: str | None = None,
    ) -> tuple[DashboardReportExecution, bool]:
        if (
            subscription.creator != request.user.username
            or subscription.creator_domain != request.user.domain
        ):
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
            domain=locked_subscription.creator_domain,
        )
        try:
            execution = DashboardReportExecution.objects.create(
                subscription=locked_subscription,
                dashboard=locked_subscription.dashboard,
                creator=locked_subscription.creator,
                creator_domain=locked_subscription.creator_domain,
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
        except ValidationError as exc:
            logger.exception(
                "创建 Execution Input Snapshot 失败: execution_id=%s",
                execution.id,
            )
            message = str(exc)
            if hasattr(exc, "message_dict"):
                message = "; ".join(
                    f"{k}: {v}" for k, v in exc.message_dict.items()
                )
            elif getattr(exc, "messages", None):
                message = "; ".join(str(m) for m in exc.messages)
            cls.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage="snapshot",
                error_code="filter_invalid",
                error_message=message or cls.SNAPSHOT_FAILURE_MESSAGE,
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

    @classmethod
    @transaction.atomic
    def create_scheduled(
        cls,
        subscription_id: int,
        *,
        now: datetime | None = None,
    ) -> CreateScheduledResult:
        """创建 scheduled Execution（含 missed-run 最近一期补偿）。

        仅供 DueSubscriptionScanner 调用；不是通用 Execution 创建入口。
        禁止 Retry / 补偿 / 其他模块直接复用本方法作为通用工厂。
        最终 scheduled_time_utc 仅由锁内 catch_up_scheduled_time 决定。
        """
        moment = now or timezone.now()
        locked_subscription = (
            DashboardReportSubscription.all_objects.select_for_update().get(
                pk=subscription_id
            )
        )
        if locked_subscription.deleted_at is not None:
            return CreateScheduledResult(
                execution=None, created=False
            )
        if (
            locked_subscription.status
            != DashboardReportSubscription.Status.ACTIVE
            or locked_subscription.schedule_type is None
            or locked_subscription.next_run_at is None
            or locked_subscription.dashboard_id is None
        ):
            return CreateScheduledResult(
                execution=None, created=False
            )

        # 并发下可能已被推进到未来：不再 due，直接 skip（不推进）
        if locked_subscription.next_run_at > moment:
            return CreateScheduledResult(
                execution=None, created=False
            )

        spec = cls._subscription_schedule_spec(locked_subscription)
        scheduled_time_utc = catch_up_scheduled_time(
            spec,
            locked_subscription.timezone,
            stored_next_run_at=locked_subscription.next_run_at,
            now=moment,
        )

        existing = cls._find_scheduled(
            subscription_id=locked_subscription.id,
            scheduled_time_utc=scheduled_time_utc,
        )
        if existing is not None:
            return CreateScheduledResult(
                execution=existing,
                created=False,
                already_exists=True,
            )

        if DashboardReportExecution.objects.filter(
            subscription_id=locked_subscription.id,
            status__in=IN_FLIGHT_STATUSES,
        ).exists():
            return CreateScheduledResult(
                execution=None,
                created=False,
                skipped_in_flight=True,
            )

        creator_timezone = resolve_creator_timezone(
            locked_subscription.creator,
            domain=locked_subscription.creator_domain,
        )
        try:
            execution = DashboardReportExecution.objects.create(
                subscription=locked_subscription,
                dashboard=locked_subscription.dashboard,
                creator=locked_subscription.creator,
                creator_domain=locked_subscription.creator_domain,
                trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
                scheduled_time_utc=scheduled_time_utc,
            )
        except IntegrityError:
            existing = cls._find_scheduled(
                subscription_id=locked_subscription.id,
                scheduled_time_utc=scheduled_time_utc,
            )
            if existing is not None:
                return CreateScheduledResult(
                    execution=existing,
                    created=False,
                    already_exists=True,
                )
            raise

        try:
            with transaction.atomic():
                cls._create_snapshot(
                    execution,
                    locked_subscription,
                    creator_timezone=creator_timezone,
                )
        except ValidationError as exc:
            logger.exception(
                "创建 scheduled Execution Snapshot 失败: execution_id=%s",
                execution.id,
            )
            message = str(exc)
            if getattr(exc, "messages", None):
                message = "; ".join(str(m) for m in exc.messages)
            cls.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage="snapshot",
                error_code="filter_invalid",
                error_message=message or cls.SNAPSHOT_FAILURE_MESSAGE,
            )
            cls._advance_subscription_next_run(
                locked_subscription,
                scheduled_time_utc=scheduled_time_utc,
                now=moment,
            )
            return CreateScheduledResult(
                execution=execution, created=True
            )
        except Exception:
            logger.exception(
                "创建 scheduled Execution Snapshot 失败: execution_id=%s",
                execution.id,
            )
            cls.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage="snapshot",
                error_message=cls.SNAPSHOT_FAILURE_MESSAGE,
            )
            cls._advance_subscription_next_run(
                locked_subscription,
                scheduled_time_utc=scheduled_time_utc,
                now=moment,
            )
            return CreateScheduledResult(
                execution=execution, created=True
            )

        cls._advance_subscription_next_run(
            locked_subscription,
            scheduled_time_utc=scheduled_time_utc,
            now=moment,
        )

        if execution.status == DashboardReportExecution.Status.PENDING:
            transaction.on_commit(
                lambda: cls._dispatch_render(execution.id)
            )
        return CreateScheduledResult(
            execution=execution, created=True
        )

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
