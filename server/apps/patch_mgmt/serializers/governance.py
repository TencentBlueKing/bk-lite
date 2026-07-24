"""治理任务序列化器"""

from rest_framework import serializers

from apps.core.utils.serializers import TeamSerializer
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
)


class GovernanceTaskHostSerializer(serializers.ModelSerializer):
    """治理任务主机结果序列化器"""

    requirements = serializers.SerializerMethodField()

    class Meta:
        model = GovernanceTaskHost
        fields = [
            "id",
            "task",
            "target_id",
            "target_name",
            "target_ip",
            "stage",
            "stage_color",
            "started_at",
            "stage_started_at",
            "stage_deadline_at",
            "last_heartbeat_at",
            "reconcile_deadline_at",
            "reconcile_attempts",
            "boot_marker_before",
            "timeout_reason",
            "exit_code",
            "failed_stage",
            "error_code",
            "reason",
            "suggestion",
            "can_retry",
            "created_at",
            "requirements",
        ]
        read_only_fields = ["id", "created_at"]

    def get_requirements(self, obj: GovernanceTaskHost) -> list[dict]:
        """返回该主机对应的基线要求及最新合规快照。"""
        binding = HostBaselineBinding.objects.filter(
            target_id=obj.target_id,
        ).select_related("baseline").first()
        if not binding:
            return []

        qs = BaselineRequirement.objects.filter(baseline=binding.baseline).select_related("patch")
        task = obj.task
        if task and task.task_type == GovernanceTaskType.INSTALL and task.patch_list:
            qs = qs.filter(patch_id__in=task.patch_list)

        # 取每个要求最新的快照（assess 成功时会全量替换）
        latest_snapshots = {}
        for snap in HostComplianceSnapshot.objects.filter(
            binding=binding,
        ).select_related("requirement").order_by("-evaluated_at"):
            if snap.requirement_id not in latest_snapshots:
                latest_snapshots[snap.requirement_id] = snap

        return [
            {
                "baseline_name": binding.baseline.name,
                "patch_id": req.patch_id,
                "patch_title": req.patch.title,
                "condition": req.condition,
                "satisfied": latest_snapshots.get(req.id).satisfied if latest_snapshots.get(req.id) else None,
                "reason": latest_snapshots.get(req.id).reason if latest_snapshots.get(req.id) else "",
                "evidence": latest_snapshots.get(req.id).evidence if latest_snapshots.get(req.id) else {},
            }
            for req in qs
        ]


class GovernanceTaskListSerializer(TeamSerializer):
    """治理任务列表序列化器"""

    name = serializers.CharField(required=False, allow_blank=True)
    task_type_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    host_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()
    record_status = serializers.SerializerMethodField()
    record_status_display = serializers.SerializerMethodField()
    record_status_color = serializers.SerializerMethodField()

    class Meta:
        model = GovernanceTask
        fields = [
            "id",
            "name",
            "task_type",
            "task_type_display",
            "execution_mode",
            "execution_window_start",
            "execution_window_end",
            "auto_reboot",
            "reboot_policy",
            "status",
            "status_display",
            "target_list",
            "patch_list",
            "host_count",
            "progress",
            "can_cancel",
            "can_retry",
            "record_status",
            "record_status_display",
            "record_status_color",
            "started_at",
            "finished_at",
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
            "team",
            "team_name",
            "created_by",
            "created_at",
            "parent_task",
            "chain_started_at",
            "chain_deadline_at",
            "overdue_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "started_at",
            "finished_at",
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("name"):
            task_type = attrs.get("task_type", "unknown")
            attrs["name"] = f"治理任务 · {dict(GovernanceTaskType.CHOICES).get(task_type, task_type)}"
        return attrs

    def get_host_count(self, obj):
        return obj.host_results.count()

    def get_task_type_display(self, obj):
        if obj.task_type == GovernanceTaskType.INSTALL:
            return "治理"
        return obj.get_task_type_display()

    def get_progress(self, obj):
        total = obj.host_results.count()
        if total == 0:
            return "0 / 0"
        completed_stages = ["completed", "failed", "cancelled", "reboot_scheduled", "reboot_failed"]
        if obj.task_type != GovernanceTaskType.REBOOT:
            completed_stages.append("pending_reboot")
        done = obj.host_results.filter(stage__in=completed_stages).count()
        return f"{done} / {total}"

    def get_can_cancel(self, obj):
        return (
            obj.status in GovernanceTaskStatus.ACTIVE_STATES
            and obj.host_results.filter(stage="waiting").exists()
        )

    def get_can_retry(self, obj):
        from apps.patch_mgmt.services.execution_record_service import (
            _task_chain,
            build_risk_item_summaries,
        )

        has_retryable_attempt = GovernanceTaskHost.objects.filter(
            task__in=_task_chain(obj), can_retry=True
        ).exists()
        return has_retryable_attempt or any(
            item["status"] == "unmet" for item in build_risk_item_summaries(obj)
        )

    @staticmethod
    def _record_status(obj):
        from apps.patch_mgmt.services.execution_record_service import build_record_status

        return build_record_status(obj)

    def get_record_status(self, obj):
        return self._record_status(obj)[0]

    def get_record_status_display(self, obj):
        return self._record_status(obj)[1]

    def get_record_status_color(self, obj):
        return self._record_status(obj)[2]


class GovernanceTaskDetailSerializer(GovernanceTaskListSerializer):
    """治理任务详情序列化器（含主机结果）"""

    host_results = GovernanceTaskHostSerializer(many=True, read_only=True)
    risk_items = serializers.SerializerMethodField()

    def get_risk_items(self, obj):
        from apps.patch_mgmt.services.execution_record_service import build_risk_item_summaries

        return build_risk_item_summaries(obj)

    class Meta(GovernanceTaskListSerializer.Meta):
        fields = GovernanceTaskListSerializer.Meta.fields + [
            "host_results",
            "risk_snapshot",
            "risk_items",
            "target_list",
            "patch_list",
        ]
