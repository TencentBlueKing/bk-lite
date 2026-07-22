# -- coding: utf-8 --
from rest_framework import serializers
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids


class ActionRuleSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = ActionRule
        fields = "__all__"


class ActionExecutionSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True, default=None)
    alert_title = serializers.CharField(source="alert.title", read_only=True, default=None)

    class Meta:
        model = ActionExecution
        fields = "__all__"
