# -- coding: utf-8 --
from rest_framework import serializers
from apps.alerts.models.action import ActionRule, ActionExecution


class ActionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionRule
        fields = "__all__"


class ActionExecutionSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True, default=None)
    alert_title = serializers.CharField(source="alert.title", read_only=True, default=None)

    class Meta:
        model = ActionExecution
        fields = "__all__"
