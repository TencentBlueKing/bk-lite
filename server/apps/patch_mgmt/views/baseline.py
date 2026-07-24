"""基线管理视图"""

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.constants import ComplianceStatus, GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
    Patch,
    PatchBaseline,
    PatchTarget,
)
from apps.patch_mgmt.serializers.baseline import (
    BaselineRequirementSerializer,
    HostBaselineBindingSerializer,
    PatchBaselineDetailSerializer,
    PatchBaselineListSerializer,
)
from apps.patch_mgmt.utils.data_permissions import require_authorized_ids


class PatchBaselineViewSet(AuthViewSet):
    """补丁基线视图集"""

    queryset = PatchBaseline.objects.all()
    serializer_class = PatchBaselineListSerializer
    search_fields = ["name"]
    ORGANIZATION_FIELD = "team"
    permission_key = "patch_baseline"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PatchBaselineDetailSerializer
        return PatchBaselineListSerializer

    @HasPermission("patch_baseline-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("patch_baseline-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("patch_baseline-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("patch_baseline-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("patch_baseline-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._assert_not_locked(instance)
        if instance.host_bindings.exists():
            raise DRFValidationError("该基线已绑定主机，需先解绑才能删除")
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    @HasPermission("patch_baseline-View")
    def requirements(self, request, pk=None):
        """查询补丁要求清单。"""
        baseline = self.get_object()
        reqs = baseline.requirements.select_related(
            "patch__windows_detail", "patch__linux_detail"
        )
        serializer = BaselineRequirementSerializer(reqs, many=True)
        return Response(serializer.data)

    @requirements.mapping.post
    @HasPermission("patch_baseline-Edit")
    def add_requirements(self, request, pk=None):
        """添加补丁要求。"""
        baseline = self.get_object()
        patch_ids = request.data.get("patch_ids", [])
        require_authorized_ids(self, request, Patch.objects.all(), patch_ids, "patch")
        condition = request.data.get("condition", "")
        created = []
        for pid in patch_ids:
            _, created_flag = BaselineRequirement.objects.get_or_create(
                baseline=baseline,
                patch_id=pid,
                defaults={"condition": condition},
            )
            if created_flag:
                created.append(pid)
        if created:
            self._invalidate_active_assessments(baseline)
            self._reset_bindings_to_pending(baseline)
        return Response({"created": created, "count": len(created)})

    @requirements.mapping.delete
    @HasPermission("patch_baseline-Edit")
    def delete_requirements(self, request, pk=None):
        """移除补丁要求。"""
        baseline = self.get_object()
        req_ids = request.data.get("requirement_ids", [])
        deleted_count, _ = BaselineRequirement.objects.filter(
            id__in=req_ids, baseline=baseline
        ).delete()
        if deleted_count:
            self._invalidate_active_assessments(baseline)
            self._reset_bindings_to_pending(baseline)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    @HasPermission("patch_baseline-Edit")
    def bind_hosts(self, request, pk=None):
        """绑定主机到基线"""
        baseline = self.get_object()
        target_ids = sorted(
            {
                int(target_id)
                for target_id in request.data.get("target_ids", [])
                if target_id
            }
        )
        if not target_ids:
            raise DRFValidationError("请至少选择一台主机")
        require_authorized_ids(
            self,
            request, PatchTarget.objects.all(), target_ids, "patch_target"
        )
        current_target_ids = set(
            baseline.host_bindings.values_list("target_id", flat=True)
        )
        if current_target_ids == set(target_ids):
            return Response({"bound": len(target_ids), "changed": False})

        previous_baselines = list(
            PatchBaseline.objects.filter(
                host_bindings__target_id__in=target_ids
            ).exclude(pk=baseline.pk).distinct()
        )
        self._invalidate_active_assessments(baseline)
        for previous_baseline in previous_baselines:
            self._invalidate_active_assessments(previous_baseline)
            self._reset_bindings_to_pending(previous_baseline)
        with transaction.atomic():
            baseline.host_bindings.exclude(target_id__in=target_ids).delete()
            for tid in target_ids:
                binding, created = HostBaselineBinding.objects.update_or_create(
                    target_id=tid,
                    defaults={
                        "baseline": baseline,
                        "created_by": (
                            request.user.username
                            if hasattr(request.user, "username")
                            else ""
                        ),
                        "compliance_status": ComplianceStatus.PENDING,
                        "missing_count": 0,
                        "last_evaluated_at": None,
                    },
                )
                if not created:
                    HostComplianceSnapshot.objects.filter(binding=binding).delete()
        return Response({"bound": len(target_ids), "changed": True})

    @staticmethod
    def _invalidate_active_assessments(baseline: PatchBaseline) -> None:
        """需求或绑定变化时取消未开始评估；运行结果由快照签名防止回写。"""
        tasks = GovernanceTask.objects.filter(
            task_type=GovernanceTaskType.ASSESS,
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
            risk_snapshot__contains=[{"baseline_id": baseline.id}],
        )
        now = timezone.now()
        for task in tasks:
            GovernanceTaskHost.objects.filter(task=task, stage="waiting").update(
                stage="cancelled",
                stage_color="default",
                reason="基线要求或绑定关系已变化，本次评估已失效",
                can_retry=False,
            )
            task.status = GovernanceTaskStatus.CANCELLED
            task.finished_at = now
            task.save(update_fields=["status", "finished_at", "updated_at"])

    @action(detail=True, methods=["get"])
    @HasPermission("patch_baseline-View")
    def hosts(self, request, pk=None):
        """已绑定主机列表"""
        baseline = self.get_object()
        bindings = baseline.host_bindings.select_related("target", "baseline")
        serializer = HostBaselineBindingSerializer(bindings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    @HasPermission("patch_baseline-Edit")
    def assess(self, request, pk=None):
        """对基线当前绑定的全部主机创建一次并行评估任务。"""
        from apps.patch_mgmt.services.governance_service import (
            HostBusyError,
            create_assess_task,
        )

        baseline = self.get_object()
        requirements = list(baseline.requirements.order_by("id"))
        if not requirements:
            return Response(
                {"code": "no_requirements", "detail": "基线没有补丁要求，无法评估"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bindings = list(
            baseline.host_bindings.select_related("target").order_by("id")
        )
        if not bindings:
            return Response(
                {"code": "no_hosts", "detail": "基线没有绑定主机，无法评估"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_ids = [binding.target_id for binding in bindings]
        require_authorized_ids(
            self,
            request, PatchTarget.objects.all(), target_ids, "patch_target"
        )
        busy_target_ids = list(
            GovernanceTask.objects.filter(
                host_results__target_id__in=target_ids,
                task_type__in=(
                    GovernanceTaskType.ASSESS,
                    GovernanceTaskType.INSTALL,
                    GovernanceTaskType.REBOOT,
                    GovernanceTaskType.VERIFY,
                ),
                status__in=GovernanceTaskStatus.ACTIVE_STATES,
            )
            .values_list("host_results__target_id", flat=True)
            .distinct()
        )
        if busy_target_ids:
            return Response(
                {
                    "code": "host_busy",
                    "detail": "部分主机正在执行补丁任务，本次评估未创建",
                    "target_ids": busy_target_ids,
                },
                status=status.HTTP_409_CONFLICT,
            )

        snapshot = [{
            "baseline_id": baseline.id,
            "baseline_name": baseline.name,
            "baseline_updated_at": baseline.updated_at.isoformat(),
            "requirements_signature": "|".join(
                f"{requirement.id}:{requirement.patch_id}:{requirement.updated_at.isoformat()}"
                for requirement in requirements
            ),
            "bindings_signature": "|".join(
                f"{binding.id}:{binding.target_id}" for binding in bindings
            ),
            "requirement_ids": [requirement.id for requirement in requirements],
            "patch_ids": [requirement.patch_id for requirement in requirements],
            "targets": [
                {
                    "binding_id": binding.id,
                    "target_id": binding.target_id,
                    "target_name": binding.target.name,
                }
                for binding in bindings
            ],
        }]
        try:
            task = create_assess_task(
                request,
                target_ids,
                {
                    "execution_mode": "now",
                    "name": f"评估 · {baseline.name} · {len(target_ids)}台",
                    "risk_snapshot": snapshot,
                },
            )
        except HostBusyError as exc:
            return Response(
                {
                    "code": "host_busy",
                    "detail": str(exc),
                    "target_ids": exc.target_ids,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except (RuntimeError, ValueError) as exc:
            return Response(
                {"code": "dispatch_failed", "detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        HostBaselineBinding.objects.filter(pk__in=[binding.id for binding in bindings]).update(
            compliance_status=ComplianceStatus.EVALUATING,
            missing_count=0,
        )
        return Response(
            {"task_id": task.id, "name": task.name, "host_count": len(target_ids)},
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _assert_not_locked(baseline: PatchBaseline):
        """有进行中治理任务时禁止修改"""
        active_count = GovernanceTask.objects.filter(
            risk_snapshot__contains=[{"baseline_id": baseline.id}],
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).count()
        if active_count > 0:
            raise DRFValidationError(
                f"该基线有 {active_count} 个进行中治理任务，完成后可操作"
            )

    @staticmethod
    def _reset_bindings_to_pending(baseline: PatchBaseline) -> int:
        """将基线下所有已绑定主机重置为待评估，清除旧快照。返回重置数量。"""
        bindings = HostBaselineBinding.objects.filter(baseline=baseline)
        count = bindings.update(
            compliance_status=ComplianceStatus.PENDING,
            missing_count=0,
            last_evaluated_at=None,
        )
        if count:
            binding_ids = list(bindings.values_list("id", flat=True))
            HostComplianceSnapshot.objects.filter(binding_id__in=binding_ids).delete()
        return count
