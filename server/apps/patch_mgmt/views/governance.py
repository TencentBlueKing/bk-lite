"""治理任务视图"""

from django.db import transaction
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.exceptions import PatchBusinessError
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, PatchTarget
from apps.patch_mgmt.serializers.governance import (
    GovernanceTaskDetailSerializer,
    GovernanceTaskListSerializer,
)
from apps.patch_mgmt.services.governance_service import (
    HostBusyError,
    create_assess_task,
    create_reboot_task,
    create_retry_task,
)
from apps.patch_mgmt.utils.data_permissions import require_authorized_ids
from apps.patch_mgmt.utils.i18n import patch_message, render_business_error
from apps.patch_mgmt.utils.operation_log import log_governance_task_cancelled


class GovernanceTaskViewSet(AuthViewSet):
    """治理任务视图集（统一执行记录）"""

    queryset = GovernanceTask.objects.all()
    serializer_class = GovernanceTaskListSerializer
    search_fields = ["name"]
    ORGANIZATION_FIELD = "team"
    permission_key = "patch_governance"

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def get_queryset(self):
        """执行记录只暴露用户直接创建的治理与重启根任务。"""
        queryset = super().get_queryset().select_related("source_record")
        if self.action == "host_log":
            return queryset
        queryset = queryset.filter(
            parent_task__isnull=True,
            task_type__in=[GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT],
        )
        requested_type = getattr(self, "request", None) and self.request.query_params.get(
            "task_type"
        )
        if requested_type in (GovernanceTaskType.INSTALL, GovernanceTaskType.REBOOT):
            queryset = queryset.filter(task_type=requested_type)
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GovernanceTaskDetailSerializer
        return GovernanceTaskListSerializer

    @HasPermission("patch_governance-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("patch_governance-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("patch_governance-Add")
    def create(self, request, *args, **kwargs):
        """创建治理任务。

        评估/重启任务统一走 governance_service，确保创建主机占位并触发异步执行；
        其他类型保持默认 ModelSerializer 行为。
        """
        data = request.data
        task_type = data.get("task_type")
        target_list = data.get("target_list") or []
        require_authorized_ids(
            self,
            request, PatchTarget.objects.all(), target_list, "patch_target"
        )

        if task_type == GovernanceTaskType.VERIFY:
            return Response(
                {
                    "code": "manual_verify_not_supported",
                    "detail": patch_message(
                        request,
                        "error.manual_verify_not_supported",
                        "Verification is created automatically after reboot",
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if task_type in ("assess", "reboot"):
            try:
                if task_type == "assess":
                    task = create_assess_task(request, target_list, data)
                else:
                    task = create_reboot_task(request, target_list, data)
            except HostBusyError as exc:
                return Response(
                    {"code": exc.code, "detail": render_business_error(request, exc), "target_ids": exc.target_ids},
                    status=status.HTTP_409_CONFLICT,
                )
            except PatchBusinessError as exc:
                return Response({"code": exc.code, "detail": render_business_error(request, exc)}, status=status.HTTP_400_BAD_REQUEST)

            # service 已写 team，此处仅作防御性兜底
            if not task.team:
                current_team = self._parse_current_team_cookie(request)
                if current_team:
                    task.team = [current_team]
                    task.save(update_fields=["team", "updated_at"])

            serializer = self.get_serializer(task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @HasPermission("patch_governance-Edit")
    def cancel(self, request, pk=None):
        """取消尚未开始执行的主机，不中断已经下发的操作。"""
        scoped_task = self.get_object()
        require_authorized_ids(
            self, request, GovernanceTask.objects.all(), [scoped_task.id],
            "patch_governance"
        )
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {
                    "code": "cancel_reason_required",
                    "detail": patch_message(request, "error.cancel_reason_required", "Cancellation reason is required"),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            task = GovernanceTask.objects.select_for_update().get(pk=scoped_task.pk)
            if task.status not in GovernanceTaskStatus.ACTIVE_STATES:
                return Response(
                    {
                        "code": "task_finished_not_cancellable",
                        "detail": patch_message(request, "error.task_finished_not_cancellable", "The task has finished and cannot be cancelled"),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            waiting_hosts = GovernanceTaskHost.objects.filter(task=task, stage="waiting")
            cancelled_count = waiting_hosts.update(
                stage="cancelled",
                stage_color="default",
                reason=reason,
                can_retry=False,
            )
            if cancelled_count == 0:
                return Response(
                    {
                        "code": "no_waiting_hosts_to_cancel",
                        "detail": patch_message(request, "error.no_waiting_hosts_to_cancel", "There are no waiting targets to cancel; current executions will continue"),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()
            all_cancelled = not task.host_results.exclude(stage="cancelled").exists()
            task.status = (
                GovernanceTaskStatus.CANCELLED if all_cancelled else GovernanceTaskStatus.RUNNING
            )
            task.cancelled_by = getattr(request.user, "username", "") or ""
            task.cancelled_at = now
            task.cancel_reason = reason
            update_fields = [
                "status",
                "cancelled_by",
                "cancelled_at",
                "cancel_reason",
                "updated_at",
            ]
            if all_cancelled:
                task.finished_at = now
                update_fields.append("finished_at")
            task.save(update_fields=update_fields)

        log_governance_task_cancelled(request, task.name, reason)
        return Response(
            {
                "detail": patch_message(request, "message.hosts_cancelled", "Cancelled {count} waiting targets", count=cancelled_count),
                "cancelled_count": cancelled_count,
            }
        )

    @action(detail=True, methods=["post"], url_path="retry-host")
    @HasPermission("patch_governance-Edit")
    def retry_host(self, request, pk=None):
        """重试选中的风险项，创建独立根执行记录。"""
        task = self.get_object()
        require_authorized_ids(
            self, request, GovernanceTask.objects.all(), [task.id],
            "patch_governance"
        )
        risk_item_id = str(request.data.get("risk_item_id") or "")
        if not risk_item_id:
            return Response({"detail": patch_message(request, "error.risk_item_id_required", "risk_item_id is required")}, status=status.HTTP_400_BAD_REQUEST)
        snapshot = next(
            (
                item
                for item in (task.risk_snapshot or [])
                if str(item.get("id")) == risk_item_id
            ),
            None,
        )
        if snapshot is None:
            return Response({"detail": patch_message(request, "error.risk_item_not_found", "Risk item not found")}, status=status.HTTP_404_NOT_FOUND)
        target_id = int(snapshot.get("host_id") or 0)
        require_authorized_ids(
            self,
            request, PatchTarget.objects.all(), [target_id], "patch_target"
        )
        try:
            new_task = create_retry_task(request, task, risk_item_id)
        except PatchBusinessError as exc:
            return Response({"code": exc.code, "detail": render_business_error(request, exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "task_id": new_task.id,
                "source_record_id": task.id,
                "message": patch_message(request, "message.retry_started", "A new retry execution record has been created"),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="risk-item-detail")
    @HasPermission("patch_governance-View")
    def risk_item_detail(self, request, pk=None):
        """按需返回当前选中风险项的步骤尝试和日志。"""
        from apps.patch_mgmt.services.execution_record_service import build_risk_item_detail

        risk_item_id = request.query_params.get("risk_item_id")
        if not risk_item_id:
            return Response({"detail": patch_message(request, "error.risk_item_id_required", "risk_item_id is required")}, status=status.HTTP_400_BAD_REQUEST)
        task = self.get_object()
        require_authorized_ids(
            self, request, GovernanceTask.objects.all(), [task.id],
            "patch_governance", operation="View"
        )
        detail = build_risk_item_detail(task, risk_item_id)
        if detail is None:
            return Response({"detail": patch_message(request, "error.risk_item_not_found", "Risk item not found")}, status=status.HTTP_404_NOT_FOUND)
        return Response(detail)
