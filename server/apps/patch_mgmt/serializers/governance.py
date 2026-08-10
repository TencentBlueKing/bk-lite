"""治理任务序列化器"""

from rest_framework import serializers

from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    HostComplianceSnapshot,
)
from apps.patch_mgmt.serializers.permission import PatchPermissionSerializer
from apps.patch_mgmt.utils.i18n import serializer_message


class GovernanceTaskHostSerializer(serializers.ModelSerializer):
    """治理任务主机结果序列化器"""

    requirements = serializers.SerializerMethodField()
    stage = serializers.SerializerMethodField()
    stage_color = serializers.SerializerMethodField()
    error_code = serializers.SerializerMethodField()
    failed_stage = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    timeout_reason = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()

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

    @staticmethod
    def _state(obj):
        from apps.patch_mgmt.services.governance_convergence import project_host_state

        return project_host_state(obj)

    def get_stage(self, obj):
        return self._state(obj).stage

    def get_stage_color(self, obj):
        return self._state(obj).stage_color

    def get_error_code(self, obj):
        return self._state(obj).error_code

    def get_failed_stage(self, obj):
        return self._state(obj).failed_stage

    def get_reason(self, obj):
        return self._state(obj).reason

    def get_timeout_reason(self, obj):
        return self._state(obj).timeout_reason

    def get_can_retry(self, obj):
        return self._state(obj).can_retry

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
                "status": latest_snapshots.get(req.id).status if latest_snapshots.get(req.id) else None,
                "reason": latest_snapshots.get(req.id).reason if latest_snapshots.get(req.id) else "",
                "evidence": latest_snapshots.get(req.id).evidence if latest_snapshots.get(req.id) else {},
            }
            for req in qs
        ]


class GovernanceTaskListSerializer(PatchPermissionSerializer):
    """治理任务列表序列化器"""

    name = serializers.CharField(required=False, allow_blank=True)
    task_type_display = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    host_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()
    record_status = serializers.SerializerMethodField()
    record_status_display = serializers.SerializerMethodField()
    record_status_color = serializers.SerializerMethodField()
    source_record_name = serializers.SerializerMethodField()
    target_list = serializers.SerializerMethodField()
    patch_list = serializers.SerializerMethodField()
    permission_key = ""

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
            "permission",
            "created_by",
            "created_at",
            "parent_task",
            "source_record",
            "source_record_name",
            "source_risk_item_id",
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

    def to_representation(self, instance):
        visible_target_ids = self.context.get("visible_target_ids")
        if visible_target_ids is not None:
            instance._visible_target_ids = visible_target_ids
            for cache_name in (
                "_execution_record_hosts",
                "_execution_record_risk_summaries",
            ):
                instance.__dict__.pop(cache_name, None)
        return super().to_representation(instance)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("name"):
            task_type = attrs.get("task_type", "unknown")
            task_type_name = serializer_message(self, f"status.task_type.{task_type}", task_type)
            attrs["name"] = serializer_message(self, "message.governance_task_name", "Governance Task · {type}", type=task_type_name)
        return attrs

    def get_host_count(self, obj):
        return len(self._visible_hosts(obj))

    @staticmethod
    def _visible_hosts(obj):
        hosts = getattr(obj, "_visible_host_results", None)
        if hosts is not None:
            return list(hosts)
        return list(obj.host_results.select_related("task").all())

    @staticmethod
    def _visible_target_ids(obj) -> set[int]:
        configured = getattr(obj, "_visible_target_ids", None)
        if configured is not None:
            return {int(value) for value in configured}
        return {host.target_id for host in GovernanceTaskListSerializer._visible_hosts(obj)}

    def get_target_list(self, obj):
        visible = self._visible_target_ids(obj)
        return [int(value) for value in (obj.target_list or []) if int(value) in visible]

    def get_patch_list(self, obj):
        visible = self._visible_target_ids(obj)
        return list(
            dict.fromkeys(
                int(item.get("patch_id"))
                for item in (obj.risk_snapshot or [])
                if int(item.get("host_id") or 0) in visible and item.get("patch_id")
            )
        )

    def get_task_type_display(self, obj):
        return serializer_message(
            self,
            f"status.task_type.{obj.task_type}",
            obj.get_task_type_display(),
        )

    def get_status(self, obj):
        from apps.patch_mgmt.services.governance_convergence import project_task_status

        return project_task_status(obj)

    def get_status_display(self, obj):
        status = self.get_status(obj)
        return dict(GovernanceTaskStatus.CHOICES).get(status, status)

    def get_progress(self, obj):
        hosts = self._visible_hosts(obj)
        total = len(hosts)
        if total == 0:
            return "0 / 0"
        completed_stages = ["completed", "failed", "cancelled", "reboot_scheduled", "reboot_failed"]
        if obj.task_type != GovernanceTaskType.REBOOT:
            completed_stages.append("pending_reboot")
        done = sum(host.stage in completed_stages for host in hosts)
        return f"{done} / {total}"

    def get_can_cancel(self, obj):
        return (
            obj.status in GovernanceTaskStatus.ACTIVE_STATES
            and any(host.stage == "waiting" for host in self._visible_hosts(obj))
        )

    def get_can_retry(self, obj):
        from apps.patch_mgmt.services.execution_record_service import (
            build_risk_item_summaries,
        )

        return any(item["can_retry"] for item in build_risk_item_summaries(obj))

    def get_source_record_name(self, obj):
        return obj.source_record.name if obj.source_record_id else ""

    def get_permission(self, obj):
        visible = self._visible_target_ids(obj)
        permissions = ["View"] if visible else []
        configured_operable = self.context.get("operable_target_ids")
        if configured_operable is not None:
            if visible.intersection({int(value) for value in configured_operable}):
                permissions.append("Operate")
            return permissions
        request = self.context.get("request")
        if request is None:
            return permissions
        from apps.patch_mgmt.services.target_access import target_access_scope

        try:
            operable = set(
                target_access_scope(request)
                .queryset("Operate")
                .filter(pk__in=visible)
                .values_list("pk", flat=True)
            )
        except Exception:  # noqa: BLE001 - 权限依赖故障时 fail closed
            operable = set()
        if operable:
            permissions.append("Operate")
        return permissions

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

    host_results = serializers.SerializerMethodField()
    risk_items = serializers.SerializerMethodField()

    def get_risk_items(self, obj):
        from apps.patch_mgmt.services.execution_record_service import build_risk_item_summaries

        return build_risk_item_summaries(obj)

    def get_host_results(self, obj):
        return GovernanceTaskHostSerializer(
            self._visible_hosts(obj), many=True, context=self.context
        ).data

    class Meta(GovernanceTaskListSerializer.Meta):
        fields = GovernanceTaskListSerializer.Meta.fields + [
            "host_results",
            "risk_snapshot",
            "risk_items",
            "target_list",
            "patch_list",
        ]
