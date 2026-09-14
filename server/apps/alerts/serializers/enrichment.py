# -- coding: utf-8 --
import re

from rest_framework import serializers

from apps.alerts.models.enrichment import EnrichmentRule
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.alerts.utils.rule_catalog import validate_rules_for_serializer


class EnrichmentRuleModelSerializer(serializers.ModelSerializer):
    """告警丰富规则序列化器。"""

    is_builtin = serializers.BooleanField(read_only=True)
    EVENT_FIELDS = {
        "title",
        "source_id",
        "source_name",
        "level",
        "resource_type",
        "resource_id",
        "content",
        "service",
        "location",
        "resource_name",
        "item",
    }
    MATCH_OPERATORS = {"eq", "ne", "contains", "not_contains", "re", "in", "not_in"}
    NAMESPACE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

    def validate_input_binding(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("入参绑定必须是对象 {provider_param: event_field}")
        if not value:
            raise serializers.ValidationError("入参绑定不能为空")
        invalid_fields = sorted({field for field in value.values() if field not in self.EVENT_FIELDS})
        if invalid_fields:
            raise serializers.ValidationError(f"不支持的事件字段: {', '.join(invalid_fields)}")
        return value

    def validate_output_projection(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("出参投影必须是列表 [{source, as}]")
        if not value:
            raise serializers.ValidationError("出参投影不能为空，需显式选择可写入告警的字段")
        aliases = set()
        for item in value:
            if not isinstance(item, dict) or not str(item.get("source") or "").strip():
                raise serializers.ValidationError("每项投影须含 source 字段")
            alias = str(item.get("as") or item["source"]).strip()
            if not self.NAMESPACE_PATTERN.fullmatch(alias):
                raise serializers.ValidationError(f"投影字段名不合法: {alias}")
            if alias in aliases:
                raise serializers.ValidationError(f"投影字段名重复: {alias}")
            aliases.add(alias)
        return value

    def validate_match_rules(self, value):
        return validate_rules_for_serializer(value, "enrichment")

    def validate_namespace(self, value):
        value = str(value or "").strip()
        if not self.NAMESPACE_PATTERN.fullmatch(value):
            raise serializers.ValidationError("命名空间须以字母开头，且只能包含字母、数字和下划线")
        return value

    def validate_provider_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Provider 配置必须是对象")
        if "query_timeout_seconds" in value:
            try:
                timeout = int(value["query_timeout_seconds"])
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("query_timeout_seconds 必须是整数") from exc
            if not 1 <= timeout <= 10:
                raise serializers.ValidationError("query_timeout_seconds 必须在 1 到 10 秒之间")
        return value

    def validate_team(self, value):
        request = self.context.get("request")
        try:
            normalized = normalize_team_ids(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        authorized = set(get_authorized_group_ids(request)) if request else set()
        if not normalized or not set(normalized).issubset(authorized):
            raise serializers.ValidationError("team 必须位于当前授权团队范围内")
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current = self.instance
        provider_type = attrs.get("provider_type", getattr(current, "provider_type", "cmdb"))
        binding = attrs.get("input_binding", getattr(current, "input_binding", {}))
        if provider_type != "cmdb":
            raise serializers.ValidationError({"provider_type": "暂不支持的数据源类型"})
        if "model_id" not in binding or not ({"inst_uuid", "inst_name"} & set(binding)):
            raise serializers.ValidationError({"input_binding": "CMDB 绑定必须包含 model_id，以及 inst_uuid 或 inst_name"})

        namespace = attrs.get("namespace", getattr(current, "namespace", ""))
        is_active = attrs.get("is_active", getattr(current, "is_active", True))
        team = attrs.get("team", getattr(current, "team", []))
        if namespace and is_active:
            queryset = EnrichmentRule.objects.filter(namespace=namespace, is_active=True)
            if current and current.pk:
                queryset = queryset.exclude(pk=current.pk)
            requested_team = set(team or [])
            for other in queryset.only("id", "team"):
                other_team = set(other.team or [])
                if not requested_team or not other_team or requested_team & other_team:
                    raise serializers.ValidationError({"namespace": "当前团队已有启用规则使用该命名空间，请使用唯一命名空间"})
        return attrs

    class Meta:
        model = EnrichmentRule
        fields = [
            "id",
            "name",
            "is_active",
            "match_rules",
            "provider_type",
            "input_binding",
            "provider_config",
            "output_projection",
            "on_multiple",
            "namespace",
            "team",
            "preset_key",
            "is_builtin",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["id", "preset_key", "is_builtin", "created_at", "updated_at", "created_by", "updated_by"]
