# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.action import ActionExecution, ActionRule
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.alerts.utils.rule_catalog import validate_rules_for_serializer


class ActionRuleSerializer(serializers.ModelSerializer):
    def validate_match_rules(self, value):
        return validate_rules_for_serializer(value, "action")

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

    def validate_action_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("action_config 必须是对象")
        bindings = value.get("param_bindings") or []
        if not isinstance(bindings, list):
            raise serializers.ValidationError("param_bindings 必须是列表")
        cleaned = []
        for index, binding in enumerate(bindings):
            if not isinstance(binding, dict) or not binding.get("name"):
                raise serializers.ValidationError(f"param_bindings[{index}] 缺少 name")
            source = binding.get("from") or "field"
            if source not in {"const", "field"}:
                raise serializers.ValidationError(f"参数[{binding['name']}] from 只能是 const 或 field")
            field_value = binding.get("value")
            if source == "field" and not str(field_value or "").strip():
                raise serializers.ValidationError(f"参数[{binding['name']}] 变量传递必须选择告警字段")
            item = {
                "name": binding["name"],
                "from": source,
                "value": "" if field_value is None else field_value,
            }
            if source == "const" and binding.get("allow_adjust") is True:
                item["allow_adjust"] = True
            cleaned.append(item)
        value = dict(value)
        value["param_bindings"] = cleaned
        return value

    class Meta:
        model = ActionRule
        fields = "__all__"


class ActionExecutionSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True, default=None)
    alert_title = serializers.CharField(source="alert.title", read_only=True, default=None)

    class Meta:
        model = ActionExecution
        fields = "__all__"
