"""补丁管理目标序列化器"""

import re
from pathlib import PurePosixPath

from rest_framework import serializers

from apps.core.mixinx import EncryptMixin
from apps.core.utils.serializers import TeamSerializer
from apps.patch_mgmt.models import GovernanceTask, GovernanceTaskHost, PatchTarget


class PatchTargetConnectivitySerializer(serializers.Serializer):
    """校验尚未保存的目标连接参数，不产生数据库记录。"""

    ip = serializers.IPAddressField()
    os_type = serializers.ChoiceField(choices=("linux", "windows"))
    ssh_port = serializers.IntegerField(required=False, default=22, min_value=1, max_value=65535)
    ssh_user = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_credential_type = serializers.ChoiceField(
        choices=("password", "key"), required=False, default="password"
    )
    ssh_password = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_passphrase = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_file = serializers.FileField(required=False, allow_null=True)
    winrm_port = serializers.IntegerField(required=False, default=5986, min_value=1, max_value=65535)
    winrm_scheme = serializers.ChoiceField(choices=("http", "https"), required=False, default="https")
    winrm_transport = serializers.ChoiceField(
        choices=("basic", "ntlm", "kerberos", "credssp"), required=False, default="ntlm"
    )
    winrm_user = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_password = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_cert_validation = serializers.BooleanField(required=False, default=True)


class PatchTargetSerializer(TeamSerializer):
    """补丁管理目标序列化器"""

    os_type_display = serializers.CharField(source="get_os_type_display", read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    connectivity_status_display = serializers.CharField(
        source="get_connectivity_status_display", read_only=True
    )
    ssh_credential_type_display = serializers.CharField(
        source="get_ssh_credential_type_display", read_only=True
    )
    winrm_scheme_display = serializers.CharField(source="get_winrm_scheme_display", read_only=True)
    ssh_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    ssh_key_passphrase = serializers.CharField(write_only=True, required=False, allow_blank=True)
    winrm_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # use_url=False：仅返回对象名称，避免触发未配置的默认文件存储 .url
    ssh_key_file = serializers.FileField(
        write_only=True,
        required=False,
        allow_null=True,
        use_url=False,
    )
    has_ssh_password = serializers.SerializerMethodField()
    has_winrm_password = serializers.SerializerMethodField()
    has_ssh_key = serializers.SerializerMethodField()
    ssh_key_file_name = serializers.SerializerMethodField()

    # 运行时聚合字段（列表/详情均返回，便于前端目标管理页展示）
    baseline_name = serializers.SerializerMethodField()
    baseline_id = serializers.SerializerMethodField()
    compliance_status = serializers.SerializerMethodField()
    compliance_failure_reason = serializers.SerializerMethodField()
    missing_count = serializers.SerializerMethodField()
    last_evaluated_at = serializers.SerializerMethodField()
    last_detected_at = serializers.SerializerMethodField()
    has_active_task = serializers.SerializerMethodField()
    has_pending_reboot = serializers.SerializerMethodField()
    arch = serializers.SerializerMethodField()

    def validate_name(self, value):
        """同 team 下名称唯一。"""
        if not value:
            return value
        request = self.context.get("request")
        team_id = None
        if request:
            from apps.core.utils.team_utils import get_current_team
            team_id = get_current_team(request)
        qs = PatchTarget.objects.filter(name=value)
        if team_id:
            qs = qs.filter(team__contains=[int(team_id)])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("同名目标主机已存在")
        return value

    def create(self, validated_data):
        # 节点纳入等场景前端可能未传 team，默认写入当前组织，避免列表被团队过滤掉
        if not validated_data.get("team"):
            request = self.context.get("request")
            if request:
                from apps.core.utils.team_utils import get_current_team

                current_team = get_current_team(request)
                if current_team:
                    validated_data["team"] = [int(current_team)]
        EncryptMixin.encrypt_field("ssh_password", validated_data)
        EncryptMixin.encrypt_field("ssh_key_passphrase", validated_data)
        EncryptMixin.encrypt_field("winrm_password", validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # 编辑时若凭据字段留空，保留原值，避免清空已保存的凭据
        for field in ("ssh_password", "ssh_key_passphrase", "winrm_password"):
            value = validated_data.get(field)
            if field in validated_data and not value:
                validated_data.pop(field)
            else:
                EncryptMixin.encrypt_field(field, validated_data)

        next_credential_type = validated_data.get(
            "ssh_credential_type", instance.ssh_credential_type
        )
        if next_credential_type == "password" and validated_data.get("ssh_password"):
            # 凭据切换成功后只保留当前凭据，避免旧私钥继续有效。
            if instance.ssh_key_file:
                instance.ssh_key_file.delete(save=False)
            validated_data["ssh_key_file"] = None
            validated_data["ssh_key_passphrase"] = ""
        elif next_credential_type == "key" and validated_data.get("ssh_key_file"):
            # 新私钥替换密码凭据；私钥口令本身仍按上面的规则加密。
            validated_data["ssh_password"] = ""
        return super().update(instance, validated_data)

    def get_baseline_name(self, obj):
        binding = getattr(obj, "baseline_binding", None)
        if binding is None:
            return None
        return getattr(binding.baseline, "name", None)

    def get_baseline_id(self, obj):
        binding = getattr(obj, "baseline_binding", None)
        if binding is None:
            return None
        return binding.baseline_id

    def get_compliance_status(self, obj):
        from apps.patch_mgmt.services.risk_service import compute_host_compliance_status

        try:
            return compute_host_compliance_status(obj)
        except Exception:  # noqa: BLE001
            return "unconfigured" if getattr(obj, "baseline_binding", None) is None else "pending"

    def get_missing_count(self, obj):
        binding = getattr(obj, "baseline_binding", None)
        if not binding:
            return 0
        if binding.missing_count:
            return binding.missing_count
        # 兜底：实时数一次
        return binding.baseline.requirements.count() if binding.baseline_id else 0

    def get_compliance_failure_reason(self, obj):
        binding = getattr(obj, "baseline_binding", None)
        if not binding or binding.compliance_status != "failed":
            return ""
        host = GovernanceTaskHost.objects.filter(
            target_id=obj.id,
            task__task_type__in=("assess", "verify"),
            stage__in=("failed", "pending_confirmation"),
        ).order_by("-created_at").first()
        reason = (host.reason or host.timeout_reason or "评估执行失败") if host else "评估执行失败"
        return re.sub(
            r"(?i)(password|passwd|pwd|token|secret)\s*[:=]\s*\S+",
            r"\1=***",
            reason,
        )[:500]

    def get_last_evaluated_at(self, obj):
        binding = getattr(obj, "baseline_binding", None)
        return binding.last_evaluated_at if binding else None

    def get_last_detected_at(self, obj):
        return obj.last_checked_at

    def get_has_active_task(self, obj):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        return GovernanceTask.objects.filter(
            target_list__contains=[obj.id],
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).exists()

    def get_has_pending_reboot(self, obj):
        from apps.patch_mgmt.constants import GovernanceTaskStatus

        return GovernanceTask.objects.filter(
            task_type="reboot",
            target_list__contains=[obj.id],
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).exists() or GovernanceTaskHost.objects.filter(
            target_id=obj.id,
            stage__in=("pending_reboot", "reboot_scheduled", "rebooting"),
        ).exists()

    def get_arch(self, obj):
        return obj.arch or ""

    def get_has_ssh_password(self, obj):
        return bool(obj.ssh_password)

    def get_has_winrm_password(self, obj):
        return bool(obj.winrm_password)

    def get_has_ssh_key(self, obj):
        return bool(obj.ssh_key_file)

    def get_ssh_key_file_name(self, obj):
        if not obj.ssh_key_file:
            return ""
        return PurePosixPath(obj.ssh_key_file.name).name

    class Meta:
        model = PatchTarget
        fields = [
            "id",
            "name",
            "ip",
            "os_type",
            "os_type_display",
            "source_type",
            "source_type_display",
            "node_id",
            "cloud_region_id",
            "ssh_port",
            "ssh_user",
            "ssh_credential_type",
            "ssh_credential_type_display",
            "ssh_password",
            "has_ssh_password",
            "ssh_key_passphrase",
            "ssh_key_file",
            "has_ssh_key",
            "ssh_key_file_name",
            "winrm_port",
            "winrm_scheme",
            "winrm_scheme_display",
            "winrm_transport",
            "winrm_user",
            "winrm_password",
            "has_winrm_password",
            "winrm_cert_validation",
            "connectivity_status",
            "connectivity_status_display",
            "baseline_name",
            "baseline_id",
            "compliance_status",
            "compliance_failure_reason",
            "missing_count",
            "last_evaluated_at",
            "last_detected_at",
            "has_active_task",
            "has_pending_reboot",
            "arch",
            "team",
            "team_name",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "connectivity_status",
            "baseline_name",
            "compliance_status",
            "compliance_failure_reason",
            "missing_count",
            "last_evaluated_at",
            "last_detected_at",
            "has_active_task",
            "has_pending_reboot",
            "arch",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
