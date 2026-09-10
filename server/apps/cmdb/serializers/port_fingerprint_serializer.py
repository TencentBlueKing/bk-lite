from rest_framework import serializers

from apps.cmdb.models.collect_model import PortFingerprint
from apps.core.utils.serializers import UsernameSerializer


class PortFingerprintSerializer(UsernameSerializer):
    class Meta:
        model = PortFingerprint
        fields = "__all__"
        extra_kwargs = {
            "protocol": {"required": False},
            "built_in": {"read_only": True},
        }

    def validate_port(self, value):
        port = int(value)
        if port < 1 or port > 65535:
            raise serializers.ValidationError("端口必须在 1-65535")
        return port

    def validate_target_type(self, value):
        target_type = str(value or "").strip()
        if not target_type:
            raise serializers.ValidationError("类型不能为空")
        return target_type

    def validate_protocol(self, value):
        protocol = str(value or PortFingerprint.PROTOCOL_TCP).strip().lower() or PortFingerprint.PROTOCOL_TCP
        if protocol != PortFingerprint.PROTOCOL_TCP:
            raise serializers.ValidationError("本轮只支持 TCP")
        return protocol

    def create(self, validated_data):
        validated_data["built_in"] = False
        validated_data.setdefault("protocol", PortFingerprint.PROTOCOL_TCP)
        return super().create(validated_data)
