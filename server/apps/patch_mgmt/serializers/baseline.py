"""基线管理序列化器"""

from rest_framework import serializers

from apps.core.utils.serializers import TeamSerializer
from apps.patch_mgmt.constants import ComplianceStatus, GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    HostBaselineBinding,
    PatchBaseline,
)


class BaselineRequirementSerializer(serializers.ModelSerializer):
    """基线补丁要求序列化器"""

    patch_title = serializers.CharField(source="patch.title", read_only=True)
    patch_severity = serializers.CharField(source="patch.severity", read_only=True)
    patch_severity_display = serializers.CharField(source="patch.get_severity_display", read_only=True)
    patch_os_type = serializers.CharField(source="patch.os_type", read_only=True)
    patch_kb_number = serializers.SerializerMethodField()
    patch_pkg_name = serializers.SerializerMethodField()
    patch_pkg_version = serializers.SerializerMethodField()
    patch_version = serializers.SerializerMethodField()
    patch_arch = serializers.SerializerMethodField()
    patch_condition = serializers.SerializerMethodField()

    class Meta:
        model = BaselineRequirement
        fields = [
            "id",
            "baseline",
            "patch",
            "condition",
            "patch_title",
            "patch_severity",
            "patch_severity_display",
            "patch_os_type",
            "patch_kb_number",
            "patch_pkg_name",
            "patch_pkg_version",
            "patch_version",
            "patch_arch",
            "patch_condition",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def _get_detail(self, obj, attr):
        patch = obj.patch
        if patch.os_type == "windows":
            try:
                return getattr(patch.windows_detail, attr, None)
            except Exception:
                return None
        else:
            try:
                return getattr(patch.linux_detail, attr, None)
            except Exception:
                return None

    def get_patch_kb_number(self, obj):
        return self._get_detail(obj, "kb_number")

    def get_patch_pkg_name(self, obj):
        return self._get_detail(obj, "pkg_name")

    def get_patch_pkg_version(self, obj):
        return self._get_detail(obj, "pkg_version")

    def get_patch_version(self, obj):
        detail = self._get_detail(obj, "os_version_range")
        if not detail:
            detail = self._get_detail(obj, "distro_name")
        return detail or ""

    def get_patch_arch(self, obj):
        archs = self._get_detail(obj, "architectures")
        return ", ".join(archs) if archs else ""

    def get_patch_condition(self, obj):
        if obj.condition:
            return obj.condition
        patch = obj.patch
        if patch.os_type == "windows":
            kb = self.get_patch_kb_number(obj)
            return f"装 {kb} 或有效替代 KB" if kb else ""
        else:
            pkg = self.get_patch_pkg_name(obj)
            ver = self.get_patch_pkg_version(obj)
            return f"包版本 ≥ {ver}" if pkg and ver else ""


class PatchBaselineListSerializer(TeamSerializer):
    """基线列表序列化器"""

    os_type_display = serializers.CharField(source="get_os_type_display", read_only=True)
    requirement_count = serializers.SerializerMethodField()
    bound_host_count = serializers.SerializerMethodField()
    compliance_distribution = serializers.SerializerMethodField()
    archs = serializers.SerializerMethodField()
    is_assessing = serializers.SerializerMethodField()
    can_assess = serializers.SerializerMethodField()
    assess_disabled_reason = serializers.SerializerMethodField()

    class Meta:
        model = PatchBaseline
        fields = [
            "id",
            "name",
            "os_type",
            "os_type_display",
            "description",
            "archs",
            "requirement_count",
            "bound_host_count",
            "compliance_distribution",
            "is_assessing",
            "can_assess",
            "assess_disabled_reason",
            "team",
            "team_name",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        """同 team 下名称唯一。"""
        if not value:
            return value
        request = self.context.get("request")
        team_id = None
        if request:
            from apps.core.utils.team_utils import get_current_team
            team_id = get_current_team(request)
        qs = PatchBaseline.objects.filter(name=value)
        if team_id:
            qs = qs.filter(team__contains=[int(team_id)])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("同名基线已存在")
        return value

    def create(self, validated_data):
        if not validated_data.get("team"):
            request = self.context.get("request")
            if request:
                from apps.core.utils.team_utils import get_current_team

                current_team = get_current_team(request)
                if current_team:
                    validated_data["team"] = [int(current_team)]
        return super().create(validated_data)

    def get_requirement_count(self, obj):
        return obj.requirements.count()

    def get_bound_host_count(self, obj):
        return obj.host_bindings.count()

    def get_compliance_distribution(self, obj):
        """按已绑定主机的合规状态聚合分布（含评估中）。"""
        bindings = list(obj.host_bindings.all())
        if not bindings:
            return []

        target_ids = [b.target_id for b in bindings]
        active_target_ids = set(
            GovernanceTask.objects.filter(
                host_results__target_id__in=target_ids,
                task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
                status__in=GovernanceTaskStatus.ACTIVE_STATES,
            )
            .values_list("host_results__target_id", flat=True)
            .distinct()
        )

        status_meta = {
            ComplianceStatus.COMPLIANT: ("合规", "success", "compliant"),
            ComplianceStatus.NON_COMPLIANT: ("不合规", "error", "non_compliant"),
            ComplianceStatus.PENDING: ("待评估", "default", "pending"),
            ComplianceStatus.EVALUATING: ("评估中", "processing", "evaluating"),
            ComplianceStatus.FAILED: ("评估失败", "default", "failed"),
        }
        counts = {key: 0 for key in status_meta}
        for binding in bindings:
            key = (
                ComplianceStatus.EVALUATING
                if binding.target_id in active_target_ids
                else binding.compliance_status
            )
            if key in counts:
                counts[key] += 1

        return [
            {"label": label, "count": counts[key], "color": color, "filter": filter_key}
            for key, (label, color, filter_key) in status_meta.items()
            if counts[key] > 0
        ]

    def get_archs(self, obj):
        from apps.patch_mgmt.models import WindowsPatchDetail, LinuxPatchDetail

        archs = set()
        for req in obj.requirements.select_related("patch"):
            patch = req.patch
            if patch.os_type == "windows":
                try:
                    for arch in patch.windows_detail.architectures or []:
                        archs.add(arch)
                except WindowsPatchDetail.DoesNotExist:
                    pass
            else:
                try:
                    for arch in patch.linux_detail.architectures or []:
                        archs.add(arch)
                except LinuxPatchDetail.DoesNotExist:
                    pass
        return sorted(archs)

    def get_is_assessing(self, obj):
        return GovernanceTask.objects.filter(
            task_type=GovernanceTaskType.ASSESS,
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
            risk_snapshot__contains=[{"baseline_id": obj.id}],
        ).exists()

    def get_can_assess(self, obj):
        return (
            obj.requirements.exists()
            and obj.host_bindings.exists()
            and not self.get_is_assessing(obj)
        )

    def get_assess_disabled_reason(self, obj):
        if not obj.requirements.exists():
            return "基线没有补丁要求"
        if not obj.host_bindings.exists():
            return "基线没有绑定主机"
        if self.get_is_assessing(obj):
            return "基线正在评估中"
        return ""


class PatchBaselineDetailSerializer(PatchBaselineListSerializer):
    """基线详情序列化器（含要求清单）"""

    requirements = BaselineRequirementSerializer(many=True, read_only=True)

    class Meta(PatchBaselineListSerializer.Meta):
        fields = PatchBaselineListSerializer.Meta.fields + ["requirements"]


class HostBaselineBindingSerializer(serializers.ModelSerializer):
    """主机基线绑定序列化器"""

    target_name = serializers.CharField(source="target.name", read_only=True)
    target_ip = serializers.CharField(source="target.ip", read_only=True)
    baseline_name = serializers.CharField(source="baseline.name", read_only=True)

    class Meta:
        model = HostBaselineBinding
        fields = [
            "id",
            "target",
            "target_name",
            "target_ip",
            "baseline",
            "baseline_name",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]
