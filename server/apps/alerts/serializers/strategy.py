import re

from rest_framework import serializers
from croniter import croniter

from apps.alerts.constants import (
    AlarmStrategyType,
    HeartbeatActivationMode,
    HeartbeatCheckMode,
    HeartbeatStatus,
)
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.alerts.utils.util import parse_aggregation_window_size

# 允许的聚合维度白名单（防止 SQL 注入）
ALLOWED_DIMENSIONS = frozenset({
    "event_id", "service", "location", "resource_name", "item",
    "external_id", "source", "level", "title", "description",
    "resource_id", "resource_type",
})

# 维度名格式校验（仅允许标识符格式）
DIMENSION_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$')


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

    def save(self, **kwargs):
        instance = super().save(**kwargs)
        # 即时告警策略缓存失效：保证启停 / 编辑后旁路立即生效，避免最长 60s TTL 窗口不一致
        try:
            from apps.alerts.aggregation.processor.instant_dispatcher import (
                InstantStrategyCache,
            )
            InstantStrategyCache.cache_clear()
        except Exception:  # noqa
            pass
        return instance

    def _validate_authorized_team_ids(self, value, field_name):
        try:
            team_ids = normalize_team_ids(value)
        except ValueError as error:
            raise serializers.ValidationError(str(error))

        request = self.context.get("request")
        if request is None:
            return team_ids

        user = getattr(request, "user", None)
        if user and getattr(user, "is_superuser", False):
            return team_ids

        authorized_group_ids = get_authorized_group_ids(request)
        unauthorized_teams = sorted(set(team_ids) - set(authorized_group_ids))
        if unauthorized_teams:
            raise serializers.ValidationError(
                f"You are not authorized to assign {field_name}: {unauthorized_teams}"
            )
        return team_ids

    def validate_team(self, value):
        return self._validate_authorized_team_ids(value, "teams")

    def validate_dispatch_team(self, value):
        return self._validate_authorized_team_ids(value, "dispatch_team")

    def validate(self, attrs):
        strategy_type = attrs.get(
            "strategy_type",
            getattr(self.instance, "strategy_type", AlarmStrategyType.SMART_DENOISE),
        )

        if strategy_type == AlarmStrategyType.MISSING_DETECTION:
            attrs = self._validate_missing_detection(attrs)
        elif strategy_type == AlarmStrategyType.INSTANT:
            attrs = self._validate_instant(attrs)
        else:
            attrs = self._validate_aggregation_strategy(attrs)

        if self.instance:
            attrs["last_execute_time"] = self.instance.last_execute_time
        else:
            attrs["last_execute_time"] = None

        return attrs

    def _validate_aggregation_strategy(self, attrs):
        existing_params = {}
        if self.instance and self.instance.strategy_type != AlarmStrategyType.MISSING_DETECTION:
            existing_params = dict(self.instance.params or {})

        params = dict(existing_params)
        params.update(dict(attrs.get("params") or {}))
        params_errors = {}

        try:
            normalized_window_size, _ = parse_aggregation_window_size(
                params.get("window_size")
            )
            params["window_size"] = normalized_window_size
        except ValueError as error:
            params_errors["window_size"] = str(error)

        group_by = params.get("group_by", [])
        if group_by:
            if not isinstance(group_by, list):
                params_errors["group_by"] = "group_by 必须是列表"
            else:
                for dim in group_by:
                    if not isinstance(dim, str):
                        params_errors["group_by"] = "维度名必须是字符串"
                        break
                    if not DIMENSION_NAME_PATTERN.match(dim):
                        params_errors["group_by"] = f"维度名格式非法: {dim}"
                        break
                    if dim not in ALLOWED_DIMENSIONS:
                        params_errors["group_by"] = f"不支持的聚合维度: {dim}"
                        break

        if params_errors:
            raise serializers.ValidationError({"params": params_errors})

        attrs["params"] = params
        return attrs

    def _validate_instant(self, attrs):
        """即时告警类型校验：

        - 必须配置 match_rules，且不允许等价 ALL 的空规则（PRD 不允许"全部"）
        - params.alert_template.title 与 description 必填
        - 静默清理 params 中的聚合相关字段（window_size / group_by / aggregation_*）
        """
        match_rules = attrs.get(
            "match_rules", getattr(self.instance, "match_rules", []) or []
        )

        if not match_rules or not any(group for group in match_rules):
            raise serializers.ValidationError(
                {"match_rules": "即时告警必须配置筛选条件，且不支持全部（ALL）匹配。"}
            )

        params = dict(attrs.get("params") or {})
        alert_template = dict(params.get("alert_template") or {})
        template_title = (alert_template.get("title") or "").strip()
        template_description = (alert_template.get("description") or "").strip()

        params_errors = {}
        if not template_title:
            params_errors["alert_template.title"] = "告警模板标题不能为空。"
        if not template_description:
            params_errors["alert_template.description"] = "告警模板描述不能为空。"
        if params_errors:
            raise serializers.ValidationError({"params": params_errors})

        # 即时告警不参与聚合，强制清理聚合参数
        attrs["params"] = {
            "alert_template": {
                "title": template_title,
                "description": template_description,
            }
        }
        # 即时告警不自动关闭
        attrs["auto_close"] = False
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
