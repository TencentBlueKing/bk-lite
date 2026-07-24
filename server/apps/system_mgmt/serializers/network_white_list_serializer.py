import ipaddress

from rest_framework import serializers

from apps.system_mgmt.models import NetworkWhiteList

# 等于关闭全部 SSRF 防护的超网，禁止入库
_FORBIDDEN_SUPERNETS = {"0.0.0.0/0", "::/0"}

# domain 字段禁用的字符(防止 userinfo/CIDR 格式/通配/前导点等绕过)
_DOMAIN_FORBIDDEN_CHARS = ("@", "/", "*", " ", "\t", "\n", "\r")


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
            "is_build_in",
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

    def validate_domain_name(self, value):
        raw = (value or "").strip().lower()
        if not raw:
            raise serializers.ValidationError("域名不能为空")
        if any(ch in raw for ch in _DOMAIN_FORBIDDEN_CHARS):
            raise serializers.ValidationError(f"域名包含非法字符: {raw!r}")
        if raw.startswith("."):
            raise serializers.ValidationError("域名不能以前导点开头")
        return raw

    def validate(self, attrs):
        """network 与 domain_name 二选一(只在 attrs 同时显式提供时校验互斥)

        partial update 时 attrs 可能为空(只更新 remark/enabled);不强制要求重填主字段。
        """
        network_provided = "network" in attrs
        domain_provided = "domain_name" in attrs
        instance = getattr(self, "instance", None)

        if instance is not None:
            changes_network_to_domain = bool(instance.network) and domain_provided and bool(attrs.get("domain_name"))
            changes_domain_to_network = bool(instance.domain_name) and network_provided and bool(attrs.get("network"))
            if changes_network_to_domain or changes_domain_to_network:
                raise serializers.ValidationError("白名单条目类型不可变更")

        effective_network = attrs.get("network", instance.network if instance is not None else "")
        effective_domain = attrs.get("domain_name", instance.domain_name if instance is not None else "")
        if bool(effective_network) == bool(effective_domain):
            raise serializers.ValidationError("network 与 domain_name 必须且只能填写其中一个")

        # 唯一性检查:仅在显式填了某个主字段时校验
        if attrs.get("network") or attrs.get("domain_name"):
            qs = NetworkWhiteList.objects.all()
            if network_provided and attrs.get("network"):
                qs = qs.filter(network=attrs["network"])
            if domain_provided and attrs.get("domain_name"):
                qs = qs.filter(domain_name=attrs["domain_name"])
            if instance is not None:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError("网段或域名已存在")
        return attrs
