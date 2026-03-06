"""目标管理序列化器"""

from rest_framework import serializers

from apps.job_mgmt.constants import CredentialSource, OSType, SSHCredentialType, TargetSource
from apps.job_mgmt.models import Target


class TargetSerializer(serializers.ModelSerializer):
    """目标序列化器"""

    source_display = serializers.CharField(source="get_source_display", read_only=True)
    os_type_display = serializers.CharField(source="get_os_type_display", read_only=True)
    driver_display = serializers.CharField(source="get_driver_display", read_only=True)
    credential_source_display = serializers.CharField(source="get_credential_source_display", read_only=True)
    ssh_credential_type_display = serializers.CharField(source="get_ssh_credential_type_display", read_only=True)
    ssh_key_file_name = serializers.CharField(read_only=True)
    winrm_scheme_display = serializers.CharField(source="get_winrm_scheme_display", read_only=True)

    class Meta:
        model = Target
        fields = [
            "id",
            "name",
            "ip",
            "os_type",
            "os_type_display",
            "cloud_region_id",
            "driver",
            "driver_display",
            "node_id",
            "source",
            "source_display",
            "source_id",
            "credential_source",
            "credential_source_display",
            "credential_id",
            "ssh_port",
            "ssh_user",
            "ssh_credential_type",
            "ssh_credential_type_display",
            "ssh_key_file",
            "ssh_key_file_name",
            "winrm_port",
            "winrm_scheme",
            "winrm_scheme_display",
            "winrm_user",
            "winrm_cert_validation",
            "team",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_by", "updated_at"]


class TargetCreateSerializer(serializers.ModelSerializer):
    """目标创建序列化器（手动新增）"""

    class Meta:
        model = Target
        fields = [
            "name",
            "ip",
            "os_type",
            "cloud_region_id",
            "driver",
            "credential_source",
            "credential_id",
            "ssh_port",
            "ssh_user",
            "ssh_credential_type",
            "ssh_password",
            "ssh_key_file",
            "winrm_port",
            "winrm_scheme",
            "winrm_user",
            "winrm_password",
            "winrm_cert_validation",
            "team",
        ]

    def validate(self, attrs):
        """验证手动新增目标"""
        os_type = attrs.get("os_type", OSType.LINUX)
        credential_source = attrs.get("credential_source", CredentialSource.MANUAL)

        if credential_source == CredentialSource.MANUAL:
            if os_type == OSType.LINUX:
                # Linux: SSH 凭据验证
                if not attrs.get("ssh_user"):
                    raise serializers.ValidationError({"ssh_user": "Linux目标必须提供SSH用户名"})

                ssh_credential_type = attrs.get("ssh_credential_type", SSHCredentialType.PASSWORD)

                if ssh_credential_type == SSHCredentialType.PASSWORD:
                    if not attrs.get("ssh_password"):
                        raise serializers.ValidationError({"ssh_password": "密码认证方式必须提供SSH密码"})
                else:
                    if not attrs.get("ssh_key_file"):
                        raise serializers.ValidationError({"ssh_key_file": "密钥认证方式必须上传SSH密钥文件"})
            else:
                # Windows: WinRM 凭据验证
                if not attrs.get("winrm_user"):
                    raise serializers.ValidationError({"winrm_user": "Windows目标必须提供WinRM用户名"})
                if not attrs.get("winrm_password"):
                    raise serializers.ValidationError({"winrm_password": "Windows目标必须提供WinRM密码"})

        elif credential_source == CredentialSource.CREDENTIAL:
            if not attrs.get("credential_id"):
                raise serializers.ValidationError({"credential_id": "凭据管理方式必须选择凭据"})

        # 云区域必填
        if not attrs.get("cloud_region_id"):
            raise serializers.ValidationError({"cloud_region_id": "云区域必填"})

        return attrs

    def create(self, validated_data):
        """创建时设置来源为手动"""
        validated_data["source"] = TargetSource.MANUAL
        return super().create(validated_data)


class TargetUpdateSerializer(serializers.ModelSerializer):
    """目标更新序列化器"""

    class Meta:
        model = Target
        fields = [
            "name",
            "os_type",
            "cloud_region_id",
            "driver",
            "credential_source",
            "credential_id",
            "ssh_port",
            "ssh_user",
            "ssh_credential_type",
            "ssh_password",
            "ssh_key_file",
            "winrm_port",
            "winrm_scheme",
            "winrm_user",
            "winrm_password",
            "winrm_cert_validation",
            "team",
        ]

    def validate(self, attrs):
        """验证更新逻辑"""
        instance = self.instance

        # 同步来源的目标，只能修改部分字段
        if instance and instance.source == TargetSource.SYNC:
            allowed_fields = {"name", "driver", "team"}
            for field in attrs.keys():
                if field not in allowed_fields:
                    raise serializers.ValidationError({field: "同步来源的目标不能修改此字段"})

        return attrs


class TargetBatchDeleteSerializer(serializers.Serializer):
    """批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class TargetTestConnectionSerializer(serializers.Serializer):
    """测试连接序列化器"""

    ip = serializers.IPAddressField(required=True)
    os_type = serializers.CharField(required=False, default="linux")
    cloud_region_id = serializers.CharField(required=True)
    driver = serializers.CharField(required=False, default="ansible")
    credential_source = serializers.CharField(required=False, default="manual")
    credential_id = serializers.CharField(required=False, allow_blank=True, default="")
    # SSH (Linux)
    ssh_port = serializers.IntegerField(required=False, default=22)
    ssh_user = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_credential_type = serializers.CharField(required=False, default="password")
    ssh_password = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_file = serializers.FileField(required=False, allow_null=True)
    # WinRM (Windows)
    winrm_port = serializers.IntegerField(required=False, default=5986)
    winrm_scheme = serializers.CharField(required=False, default="https")
    winrm_user = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_password = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_cert_validation = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        """验证测试连接参数"""
        os_type = attrs.get("os_type", OSType.LINUX)
        credential_source = attrs.get("credential_source", CredentialSource.MANUAL)

        if credential_source == CredentialSource.MANUAL:
            if os_type == OSType.LINUX:
                # Linux: SSH 凭据验证
                if not attrs.get("ssh_user"):
                    raise serializers.ValidationError({"ssh_user": "Linux目标必须提供SSH用户名"})

                ssh_credential_type = attrs.get("ssh_credential_type", SSHCredentialType.PASSWORD)

                if ssh_credential_type == SSHCredentialType.PASSWORD:
                    if not attrs.get("ssh_password"):
                        raise serializers.ValidationError({"ssh_password": "密码认证方式必须提供SSH密码"})
                else:
                    if not attrs.get("ssh_key_file"):
                        raise serializers.ValidationError({"ssh_key_file": "密钥认证方式必须提供SSH密钥文件"})
            else:
                # Windows: WinRM 凭据验证
                if not attrs.get("winrm_user"):
                    raise serializers.ValidationError({"winrm_user": "Windows目标必须提供WinRM用户名"})
                if not attrs.get("winrm_password"):
                    raise serializers.ValidationError({"winrm_password": "Windows目标必须提供WinRM密码"})

        elif credential_source == CredentialSource.CREDENTIAL:
            if not attrs.get("credential_id"):
                raise serializers.ValidationError({"credential_id": "凭据管理方式必须选择凭据"})

        return attrs
