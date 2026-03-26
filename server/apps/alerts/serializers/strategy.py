from rest_framework import serializers
from croniter import croniter

from apps.alerts.constants import (
    AlarmStrategyType,
    HeartbeatActivationMode,
    HeartbeatCheckMode,
    HeartbeatStatus,
)
from apps.alerts.models.alert_operator import AlarmStrategy


class AlarmStrategySerializer(serializers.ModelSerializer):
    """聚合规则序列化器"""

    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    last_execute_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = AlarmStrategy
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "last_execute_time"]
        extra_kwargs = {}

    def validate(self, attrs):
        strategy_type = attrs.get(
            "strategy_type",
            getattr(self.instance, "strategy_type", AlarmStrategyType.SMART_DENOISE),
        )

        if strategy_type == AlarmStrategyType.MISSING_DETECTION:
            attrs = self._validate_missing_detection(attrs)

        if self.instance:
            attrs["last_execute_time"] = self.instance.last_execute_time
        else:
            attrs["last_execute_time"] = None

        return attrs

    def _validate_missing_detection(self, attrs):
        match_rules = attrs.get(
            "match_rules", getattr(self.instance, "match_rules", [])
        )
        params = dict(attrs.get("params") or {})
        params_errors = {}

        if not match_rules:
            raise serializers.ValidationError(
                {"match_rules": "缺失检查必须配置监听目标，且不支持全部（ALL）监听。"}
            )

        check_mode = params.get("check_mode")
        cron_expr = (params.get("cron_expr") or "").strip()
        grace_period = params.get("grace_period")
        activation_mode = (
                params.get("activation_mode") or HeartbeatActivationMode.FIRST_HEARTBEAT
        )
        auto_recovery = params.get("auto_recovery")
        if auto_recovery is None:
            auto_recovery = True

        alert_template = dict(params.get("alert_template") or {})
        template_title = (alert_template.get("title") or "").strip()
        template_level = alert_template.get("level")
        template_description = (alert_template.get("description") or "").strip()

        if check_mode != HeartbeatCheckMode.CRON:
            params_errors["check_mode"] = "缺失检查仅支持 cron 模式。"

        if not isinstance(grace_period, int) or grace_period <= 0:
            params_errors["grace_period"] = "宽限期必须为大于 0 的整数分钟。"

        if activation_mode not in {
            HeartbeatActivationMode.FIRST_HEARTBEAT,
            HeartbeatActivationMode.IMMEDIATE,
        }:
            params_errors["activation_mode"] = (
                "激活方式必须为 first_heartbeat 或 immediate。"
            )

        if not cron_expr:
            params_errors["cron_expr"] = "Cron 表达式不能为空。"
        elif not croniter.is_valid(cron_expr):
            params_errors["cron_expr"] = "Cron 表达式格式非法。"

        if params.get("interval_value") not in (None, ""):
            params_errors["interval_value"] = "缺失检查不再支持固定间隔数值。"
        if params.get("interval_unit") not in (None, ""):
            params_errors["interval_unit"] = "缺失检查不再支持固定间隔单位。"

        if not template_title:
            params_errors["alert_template.title"] = "告警名称不能为空。"
        if template_level in (None, ""):
            params_errors["alert_template.level"] = "告警级别不能为空。"
        if not template_description:
            params_errors["alert_template.description"] = "告警摘要/详情不能为空。"

        if params_errors:
            raise serializers.ValidationError({"params": params_errors})

        existing_runtime = {}
        if (
                self.instance
                and self.instance.strategy_type == AlarmStrategyType.MISSING_DETECTION
        ):
            existing_runtime = dict(self.instance.params or {})

        attrs["params"] = {
            "check_mode": HeartbeatCheckMode.CRON,
            "cron_expr": cron_expr,
            "grace_period": grace_period,
            "activation_mode": activation_mode,
            "auto_recovery": bool(auto_recovery),
            "heartbeat_status": existing_runtime.get(
                "heartbeat_status", HeartbeatStatus.WAITING
            ),
            "last_heartbeat_time": existing_runtime.get("last_heartbeat_time"),
            "last_heartbeat_context": existing_runtime.get("last_heartbeat_context"),
            "alert_template": {
                "title": template_title,
                "level": template_level,
                "description": template_description,
            },
        }
        return attrs
