import math

from rest_framework import serializers

from apps.log.constants.alert_policy import AlertConstants
from apps.log.models.policy import Alert, Event, EventRawData, Policy
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.services.policy_condition import canonical_quantile, highest_enabled_level, normalize_condition
from apps.log.utils.locale_text import serializer_text
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.utils.policy_config import validate_timing_config
from apps.log.utils.user_display import format_user_identifiers

_NUMERIC_COMPARE_OPS = {">", "<", ">=", "<=", "=", "!="}
_FIELD_REQUIRED_FUNCS = frozenset({"sum", "avg", "max", "min", "count_uniq", "quantile"})
_ALWAYS_NUMERIC_FUNCS = frozenset({"count_rate", "count_delta", "count_uniq", "quantile", "ratio", "bytes_rate"})


def _is_finite_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            number = float(text)
        except ValueError:
            return False
        return math.isfinite(number)
    return False


class AssignHandlersSerializer(serializers.Serializer):
    handlers = serializers.ListField(child=serializers.JSONField(), allow_empty=False)

    def validate_handlers(self, value):
        cleaned = []
        for item in value:
            if item in (None, "") or isinstance(item, bool):
                raise serializers.ValidationError(serializer_text(self, "error.handler_invalid"))
            cleaned.append(item)
        if not cleaned:
            raise serializers.ValidationError(serializer_text(self, "error.handler_required"))
        return cleaned


class PolicySerializer(serializers.ModelSerializer):
    schedule = serializers.JSONField(required=True)
    period = serializers.JSONField(required=True)
    organizations = serializers.SerializerMethodField()
    log_groups = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="策略监控的日志分组ID列表",
    )

    class Meta:
        model = Policy
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "last_run_time")
        validators = []

    def get_organizations(self, obj):
        """通过外键关系获取组织列表"""
        organizations = [org.organization for org in obj.policyorganization_set.all()]
        visible_organizations = self.context.get("data_team_ids")
        if visible_organizations is None:
            return organizations
        return [organization for organization in organizations if organization in visible_organizations]

    def _get_collect_type_scope(self):
        if self.instance:
            return self.instance.collect_type_id

        initial_data = getattr(self, "initial_data", None)
        collect_type = initial_data.get("collect_type") if isinstance(initial_data, dict) else None
        if collect_type in [None, "", "null"]:
            return None

        return collect_type

    def validate_name(self, value):
        """验证策略名称唯一性。试算不落库，跳过唯一性。"""
        if self.context.get("dry_run"):
            return value
        collect_type = self._get_collect_type_scope()
        queryset = Policy.objects.filter(name=value)

        if collect_type is None:
            queryset = queryset.filter(collect_type__isnull=True)
        else:
            queryset = queryset.filter(collect_type=collect_type)

        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)

        if queryset.exists():
            raise serializers.ValidationError(serializer_text(self, "error.policy_name_exists"))

        return value

    def validate_log_groups(self, value):
        """验证日志分组的有效性"""
        request = self.context.get("request") if hasattr(self, "context") else None
        if request is not None and value:
            try:
                LogAccessScopeService.resolve_scope(request, value)
            except ValueError as exc:
                raise serializers.ValidationError(str(exc))
        elif value:
            is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(value)
            if not is_valid:
                raise serializers.ValidationError(error_msg)
        return value

    def validate_schedule(self, value):
        try:
            return validate_timing_config(value, "schedule")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_period(self, value):
        try:
            return validate_timing_config(value, "period")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def _current_alert_type(self):
        initial_data = getattr(self, "initial_data", None)
        if isinstance(initial_data, dict) and initial_data.get("alert_type"):
            return initial_data.get("alert_type")
        if self.instance is not None:
            return getattr(self.instance, "alert_type", None)
        return None

    def validate_alert_condition(self, value):
        """聚合条件校验比较方式与新函数。关键字只保留命中条数。已保存的 no_data 忽略。"""
        if not isinstance(value, dict):
            return value
        value = {key: item for key, item in value.items() if key != "no_data"}
        rule = value.get("rule") if isinstance(value.get("rule"), dict) else {}
        if self._current_alert_type() != AlertConstants.TYPE_AGGREGATE:
            stored = dict(value)
            stored["rule"] = self._keyword_rule(rule)
            return stored
        self._validate_trigger_count(rule)
        self._validate_recover_after(rule)

        if "group_by" in value and value.get("group_by") is not None:
            group_by = value.get("group_by")
            if not isinstance(group_by, list) or any(not isinstance(field, str) or not field for field in group_by):
                raise serializers.ValidationError(serializer_text(self, "error.policy_group_by_invalid"))

        if "limit" in value and value.get("limit") is not None:
            limit = value.get("limit")
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= AlertConstants.SAMPLE_LIMIT_MAX:
                raise serializers.ValidationError(serializer_text(self, "error.policy_sample_limit_range"))

        conditions = rule.get("conditions") if isinstance(rule, dict) else None
        if not conditions:
            stored = dict(value)
            stored_rule = dict(rule)
            stored_rule.pop("min_hits", None)
            if "recover_after" in rule:
                stored_rule["recover_after"] = self._checked_recover_after(rule.get("recover_after"))
            stored["rule"] = stored_rule
            return stored
        if not isinstance(conditions, list):
            raise serializers.ValidationError(serializer_text(self, "error.policy_aggregate_func_unsupported"))

        normalized_conditions = []
        for condition in conditions:
            self._validate_aggregate_condition(condition)
            normalized_conditions.append(self._store_aggregate_condition(condition))
        self._validate_and_level_sets(rule, normalized_conditions)
        stored = dict(value)
        stored_rule = dict(rule)
        stored_rule.pop("min_hits", None)
        stored_rule["conditions"] = normalized_conditions
        if "recover_after" in rule:
            stored_rule["recover_after"] = self._checked_recover_after(rule.get("recover_after"))
        stored["rule"] = stored_rule
        return stored

    def _keyword_rule(self, rule):
        source = rule if isinstance(rule, dict) else {}
        cleaned = {key: item for key, item in source.items() if key not in {"trigger_count", "recover_after", "min_hits"}}
        cleaned["min_hits"] = self._checked_min_hits(source.get("min_hits", 1))
        return cleaned

    def _checked_min_hits(self, value):
        if value is None:
            value = 1
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= AlertConstants.MIN_HITS_MAX:
            raise serializers.ValidationError(serializer_text(self, "error.policy_min_hits_range"))
        return value

    def _validate_recover_after(self, rule):
        if not isinstance(rule, dict) or "recover_after" not in rule:
            return
        self._checked_recover_after(rule.get("recover_after"))

    def _checked_recover_after(self, value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= AlertConstants.RECOVER_AFTER_MAX:
            raise serializers.ValidationError(serializer_text(self, "error.policy_recover_after_range"))
        return value

    def _validate_trigger_count(self, rule):
        if not isinstance(rule, dict) or "trigger_count" not in rule or rule.get("trigger_count") is None:
            return
        trigger_count = rule.get("trigger_count")
        if isinstance(trigger_count, bool) or not isinstance(trigger_count, int) or not 1 <= trigger_count <= AlertConstants.TRIGGER_COUNT_MAX:
            raise serializers.ValidationError(serializer_text(self, "error.policy_trigger_count_range"))

    def _validate_aggregate_condition(self, condition):
        if not isinstance(condition, dict):
            raise serializers.ValidationError(serializer_text(self, "error.policy_aggregate_func_unsupported"))
        func = condition.get("func")
        if func not in AlertConstants.AGGREGATE_FUNCS and func != "count_delta":
            raise serializers.ValidationError(serializer_text(self, "error.policy_aggregate_func_unsupported"))
        if func in _FIELD_REQUIRED_FUNCS:
            field = condition.get("field")
            if not isinstance(field, str) or not field.strip():
                raise serializers.ValidationError(serializer_text(self, "error.policy_field_required"))
        compare = condition.get("compare")
        kind = "absolute"
        if compare is not None:
            if not isinstance(compare, dict):
                raise serializers.ValidationError(serializer_text(self, "error.policy_compare_invalid"))
            kind = compare.get("kind") or "absolute"
            if kind not in AlertConstants.COMPARE_KINDS:
                raise serializers.ValidationError(serializer_text(self, "error.policy_compare_invalid"))
            if kind != "absolute":
                target = compare.get("to")
                if target not in AlertConstants.COMPARE_TARGETS:
                    raise serializers.ValidationError(serializer_text(self, "error.policy_compare_invalid"))
                if target in ("offset_hours", "offset_days"):
                    offset = compare.get("offset")
                    limit = AlertConstants.MAX_COMPARE_OFFSET_HOURS if target == "offset_hours" else AlertConstants.MAX_COMPARE_OFFSET_DAYS
                    if isinstance(offset, bool) or not isinstance(offset, int) or not 1 <= offset <= limit:
                        raise serializers.ValidationError(serializer_text(self, "error.policy_compare_invalid"))
                comparable = "count" if func == "count_delta" else func
                if comparable not in AlertConstants.COMPARABLE_FUNCS:
                    raise serializers.ValidationError(serializer_text(self, "error.policy_compare_func_unsupported"))
        if (
            func == "quantile"
            and canonical_quantile((condition.get("params") or {}).get("quantile") if isinstance(condition.get("params"), dict) else None) is None
        ):
            raise serializers.ValidationError(serializer_text(self, "error.policy_quantile_invalid"))
        if func == "ratio":
            self._validate_ratio_filter(condition.get("params"))
        if "thresholds" in condition:
            self._validate_threshold_ladder(condition, func, kind)
            return
        if func in _ALWAYS_NUMERIC_FUNCS or kind != "absolute":
            if condition.get("op") not in _NUMERIC_COMPARE_OPS:
                raise serializers.ValidationError(serializer_text(self, "error.policy_numeric_op_only"))
            if not _is_finite_number(condition.get("value")):
                raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_number"))

    def _validate_threshold_ladder(self, condition, func, kind):
        raw = condition.get("thresholds")
        if not isinstance(raw, list) or not raw:
            raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_required"))
        if len(raw) > 3:
            raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_level_invalid"))
        seen = set()
        steps = []
        for item in raw:
            if not isinstance(item, dict):
                raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_level_invalid"))
            level = item.get("level")
            if level not in AlertConstants.POLICY_LEVELS or level in seen:
                raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_level_invalid"))
            seen.add(level)
            steps.append(item)
        op = condition.get("op")
        numeric_required = func in _ALWAYS_NUMERIC_FUNCS or kind != "absolute" or op in AlertConstants.LADDER_OPS
        if numeric_required and op not in _NUMERIC_COMPARE_OPS:
            raise serializers.ValidationError(serializer_text(self, "error.policy_numeric_op_only"))
        if op not in AlertConstants.LADDER_OPS and len(steps) > 1:
            raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_single"))
        if not numeric_required:
            return
        for item in steps:
            if not _is_finite_number(item.get("value")):
                raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_number"))
        if op in AlertConstants.LADDER_OPS and len(steps) > 1:
            self._validate_threshold_order(op, steps)

    def _validate_threshold_order(self, op, steps):
        ordered = sorted(steps, key=lambda item: AlertConstants.LEVEL_RANK[item["level"]])
        numbers = [float(str(item["value"]).strip()) for item in ordered]
        if op in (">", ">="):
            ordered_ok = all(numbers[index] < numbers[index + 1] for index in range(len(numbers) - 1))
        else:
            ordered_ok = all(numbers[index] > numbers[index + 1] for index in range(len(numbers) - 1))
        if not ordered_ok:
            raise serializers.ValidationError(serializer_text(self, "error.policy_threshold_order"))

    def _store_aggregate_condition(self, condition):
        normalized = normalize_condition(condition)
        raw = condition.get("thresholds")
        if not isinstance(raw, list):
            return normalized
        steps = []
        for item in raw:
            if isinstance(item, dict):
                steps.append({"level": item.get("level"), "value": item.get("value")})
        steps.sort(key=lambda step: AlertConstants.LEVEL_RANK.get(step["level"], 0))
        normalized["thresholds"] = steps
        if steps:
            lightest = min(steps, key=lambda step: AlertConstants.LEVEL_RANK.get(step["level"], 99))
            normalized["value"] = lightest["value"]
        return normalized

    def _submitted_alert_level(self):
        initial_data = getattr(self, "initial_data", None)
        if isinstance(initial_data, dict) and initial_data.get("alert_level"):
            return initial_data.get("alert_level")
        if self.instance is not None:
            return getattr(self.instance, "alert_level", None)
        return None

    def _enabled_level_set(self, condition):
        raw = condition.get("thresholds") if isinstance(condition, dict) else None
        if isinstance(raw, list) and raw:
            return frozenset(item.get("level") for item in raw if isinstance(item, dict) and item.get("level"))
        fallback = self._submitted_alert_level()
        if fallback:
            return frozenset({fallback})
        return frozenset()

    def _validate_and_level_sets(self, rule, conditions):
        mode = rule.get("mode") if isinstance(rule, dict) else None
        if mode is None:
            mode = "and"
        if mode != "and":
            return
        level_sets = [self._enabled_level_set(condition) for condition in conditions]
        if len(set(level_sets)) > 1:
            raise serializers.ValidationError(serializer_text(self, "error.policy_level_set_mismatch"))

    def _derive_aggregate_alert_level(self, attrs):
        alert_type = attrs.get("alert_type") or self._current_alert_type()
        if alert_type != AlertConstants.TYPE_AGGREGATE:
            return
        if "alert_condition" not in attrs and "alert_level" not in attrs:
            return
        condition = attrs.get("alert_condition")
        if not isinstance(condition, dict) and self.instance is not None:
            condition = getattr(self.instance, "alert_condition", None)
        rule = condition.get("rule") if isinstance(condition, dict) else None
        conditions = rule.get("conditions") if isinstance(rule, dict) else None
        fallback = attrs.get("alert_level")
        if not fallback and self.instance is not None:
            fallback = getattr(self.instance, "alert_level", None)
        derived = highest_enabled_level(conditions if isinstance(conditions, list) else [], fallback)
        if derived:
            attrs["alert_level"] = derived

    def _validate_ratio_filter(self, params):
        if not isinstance(params, dict):
            raise serializers.ValidationError(serializer_text(self, "error.policy_ratio_filter_invalid"))
        raw_filter = params.get("filter")
        if not isinstance(raw_filter, str):
            raise serializers.ValidationError(serializer_text(self, "error.policy_ratio_filter_invalid"))
        text = raw_filter.strip()
        if not text or len(text) > AlertConstants.RATIO_FILTER_MAX_LEN or "|" in raw_filter:
            raise serializers.ValidationError(serializer_text(self, "error.policy_ratio_filter_invalid"))

    def _policy_organization_ids(self, attrs):
        if "policy_organizations" in self.context:
            return self.context.get("policy_organizations") or []
        if self.instance is not None:
            return [rel.organization for rel in self.instance.policyorganization_set.all()]
        return []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._derive_aggregate_alert_level(attrs)
        handlers_provided = "handlers" in attrs
        organizations_provided = "policy_organizations" in self.context
        if not handlers_provided and not organizations_provided:
            return attrs
        from apps.log.services.alert_handlers import AlertHandlerInvalid, normalize_policy_handlers

        handlers = attrs["handlers"] if handlers_provided else list(getattr(self.instance, "handlers", None) or [])
        try:
            resolved = normalize_policy_handlers(handlers, self._policy_organization_ids(attrs))
        except AlertHandlerInvalid as exc:
            raise serializers.ValidationError({"handlers": str(exc)}) from exc
        if handlers_provided:
            attrs["handlers"] = resolved
        return attrs


class AlertSerializer(serializers.ModelSerializer):
    policy_name = serializers.SerializerMethodField()
    collect_type_name = serializers.SerializerMethodField()

    # 告警类型返回
    alert_type = serializers.SerializerMethodField()
    alert_name = serializers.SerializerMethodField()

    # 新增字段 - 改为使用SerializerMethodField
    organizations = serializers.SerializerMethodField()
    notice_users = serializers.SerializerMethodField()
    alert_condition = serializers.SerializerMethodField()
    show_fields = serializers.SerializerMethodField()
    period = serializers.SerializerMethodField()
    handlers_display = serializers.SerializerMethodField()

    def get_organizations(self, obj):
        organizations = list(obj.organizations or [])
        if not organizations and obj.policy_id:
            organizations = [org.organization for org in obj.policy.policyorganization_set.all()]
        visible_organizations = self.context.get("data_team_ids")
        if visible_organizations is None:
            return organizations
        return [organization for organization in organizations if organization in visible_organizations]

    def get_collect_type_name(self, obj):
        if not obj.collect_type:
            return None
        return obj.collect_type.name

    def get_policy_name(self, obj):
        return obj.policy.name if obj.policy_id else ""

    def get_alert_type(self, obj):
        return obj.policy.alert_type if obj.policy_id else ""

    def get_notice_users(self, obj):
        return obj.policy.notice_users if obj.policy_id else []

    def get_alert_condition(self, obj):
        return obj.policy.alert_condition if obj.policy_id else {}

    def get_show_fields(self, obj):
        return obj.policy.show_fields if obj.policy_id else []

    def get_period(self, obj):
        return obj.policy.period if obj.policy_id else {}

    def get_alert_name(self, obj):
        if obj.content:
            return obj.content
        return obj.policy.alert_name if obj.policy_id else ""

    def get_handlers_display(self, obj):
        return format_user_identifiers(obj.handlers or [])

    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "notice", "handlers")


class EventSerializer(serializers.ModelSerializer):
    policy_name = serializers.SerializerMethodField()
    alert_id = serializers.CharField(source="alert.id", read_only=True)

    def get_policy_name(self, obj):
        return obj.policy.name if obj.policy_id else ""

    class Meta:
        model = Event
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")


class EventRawDataSerializer(serializers.ModelSerializer):
    event_id = serializers.CharField(source="event.id", read_only=True)
    data = serializers.JSONField(read_only=True)

    class Meta:
        model = EventRawData
        fields = "__all__"
