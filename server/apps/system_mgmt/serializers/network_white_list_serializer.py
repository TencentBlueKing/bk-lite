import ipaddress

from rest_framework import serializers

from apps.system_mgmt.models import NetworkWhiteList

# 等于关闭全部 SSRF 防护的超网，禁止入库
_FORBIDDEN_SUPERNETS = {"0.0.0.0/0", "::/0"}


class NetworkWhiteListSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkWhiteList
        fields = "__all__"
        read_only_fields = (
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "created_at",
            "updated_at",
        )

    def validate_network(self, value):
        raw = (value or "").strip()
        if not raw:
            raise serializers.ValidationError("网段不能为空")
        try:
            net = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            raise serializers.ValidationError(f"非法的 CIDR/IP: {raw}")
        normalized = str(net)
        if normalized in _FORBIDDEN_SUPERNETS:
            raise serializers.ValidationError("禁止添加 0.0.0.0/0 或 ::/0（等于关闭全部防护）")
        return normalized
