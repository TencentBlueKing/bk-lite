import ipaddress
import re

from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import NetworkWhiteList

# 等于关闭全部 SSRF 防护的超网，禁止入库
_FORBIDDEN_SUPERNETS = {"0.0.0.0/0", "::/0"}

# domain 字段禁用的字符(防止 userinfo/CIDR 格式/空白等绕过；* 仅允许 *.suffix 形态)
_DOMAIN_FORBIDDEN_CHARS = ("@", "/", " ", "\t", "\n", "\r")

# 通配后缀：*.example.com，后缀至少两段 label（禁止 *.com / *）
_WILDCARD_DOMAIN_RE = re.compile(r"^\*\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$")


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
            raise serializers.ValidationError(self._loader().get("error.network_required"))
        try:
            net = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            raise serializers.ValidationError(self._loader().get("error.invalid_network").format(network=raw))
        normalized = str(net)
        if normalized in _FORBIDDEN_SUPERNETS:
            raise serializers.ValidationError(self._loader().get("error.forbidden_network_supernet"))
        return normalized

    def validate_domain_name(self, value):
        raw = (value or "").strip().lower()
        if not raw:
            raise serializers.ValidationError(self._loader().get("error.domain_name_required"))
        if any(ch in raw for ch in _DOMAIN_FORBIDDEN_CHARS):
            raise serializers.ValidationError(self._loader().get("error.invalid_domain_name_characters").format(domain=raw))
        if raw.startswith("."):
            raise serializers.ValidationError(self._loader().get("error.domain_name_leading_dot"))

        if "*" in raw:
            # 仅允许前缀通配 *.example.com（SwitchyOmega 同类写法）
            if not _WILDCARD_DOMAIN_RE.match(raw):
                raise serializers.ValidationError(self._loader().get("error.invalid_domain_name_wildcard").format(domain=raw))
            return raw

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
                raise serializers.ValidationError(self._loader().get("error.network_whitelist_type_immutable"))

        effective_network = attrs.get("network", instance.network if instance is not None else "")
        effective_domain = attrs.get("domain_name", instance.domain_name if instance is not None else "")
        if bool(effective_network) == bool(effective_domain):
            raise serializers.ValidationError(self._loader().get("error.network_or_domain_required"))

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
                raise serializers.ValidationError(self._loader().get("error.network_or_domain_exists"))
        return attrs

    def _loader(self):
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", "en") or "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)
