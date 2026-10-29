from rest_framework import serializers

from apps.cmdb.models.collect_model import ProcessFingerprint
from apps.cmdb.services.process_fingerprint import FINGERPRINT_TARGET_TYPES
from apps.core.utils.serializers import UsernameSerializer


class ProcessFingerprintSerializer(UsernameSerializer):
    class Meta:
        model = ProcessFingerprint
        fields = "__all__"
        extra_kwargs = {
            "built_in": {"read_only": True},
            "enabled": {"required": False},
            "linux_process": {"required": False, "allow_blank": True},
            "windows_image": {"required": False, "allow_blank": True},
        }

    def validate_target_type(self, value):
        target_type = str(value or "").strip()
        if not target_type:
            raise serializers.ValidationError("类型不能为空")
        if target_type not in FINGERPRINT_TARGET_TYPES:
            raise serializers.ValidationError("该类型不支持网段进程指纹")
        return target_type

    def validate(self, attrs):
        linux_process = str(attrs.get("linux_process") or getattr(self.instance, "linux_process", "") or "").strip()
        windows_image = str(attrs.get("windows_image") or getattr(self.instance, "windows_image", "") or "").strip()
        if "linux_process" in attrs:
            attrs["linux_process"] = linux_process
        if "windows_image" in attrs:
            attrs["windows_image"] = windows_image
        if not linux_process and not windows_image:
            raise serializers.ValidationError("Linux 进程或 Windows 映像至少填一项")
        return attrs

    def create(self, validated_data):
        validated_data["built_in"] = False
        return super().create(validated_data)
