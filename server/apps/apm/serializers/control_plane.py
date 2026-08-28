from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework import serializers

from apps.apm.models import ApmApplication, ApmDeploymentEvent, ApmPolicy, ApmPolicyTargetState, ApmService, ApmServiceInstance, ApmSlo
from apps.apm.services.identity import normalize_identity
from apps.apm.services.query import MAX_METRIC_WINDOW
from apps.apm.services.status import catalog_status


class OrganizationAssignmentSerializer(serializers.Serializer):
    organization_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_organization_ids(self, value):
        return sorted(set(value))


class ApplicationMutationSerializer(OrganizationAssignmentSerializer):
    application_id = serializers.RegexField(
        regex=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        max_length=128,
        required=False,
        error_messages={"invalid": "应用 ID 仅支持字母、数字、点、下划线和连字符，且必须以字母或数字开头。"},
    )
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(max_length=512, required=False, allow_blank=True)

    def validate_application_id(self, value):
        if not self.context.get("creating"):
            return value
        if ApmApplication.objects.filter(application_id=value).exists():
            raise serializers.ValidationError("该应用 ID 已存在。")
        return value

    def validate(self, attrs):
        if self.context.get("creating") and not attrs.get("application_id"):
            raise serializers.ValidationError({"application_id": "该字段必填。"})
        if not self.context.get("creating"):
            attrs.pop("application_id", None)
        return attrs


class IngestSnippetSerializer(serializers.Serializer):
    application_id = serializers.CharField(max_length=128)
    cloud_region_id = serializers.IntegerField(min_value=1)
    language = serializers.ChoiceField(choices=("python", "nodejs", "java", "go"))
    runtime = serializers.ChoiceField(choices=("kubernetes", "docker", "host", "other"))
    endpoint = serializers.CharField(max_length=512, required=False, write_only=True)
    service_name = serializers.CharField(max_length=256)
    service_version = serializers.CharField(max_length=256, required=False, allow_blank=True)
    environment = serializers.CharField(max_length=256, allow_blank=True)

    def validate_endpoint(self, _value):
        raise serializers.ValidationError("OTLP 端点必须由服务器根据云区域配置解析，客户端不得提交。")


class CatalogListQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, required=False)
    application = serializers.CharField(max_length=128, required=False, allow_blank=True)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=("active", "silent", "archived"), required=False)
    include_archived = serializers.BooleanField(required=False, default=False)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    keyword = serializers.CharField(max_length=256, required=False, allow_blank=True)

    def validate(self, attrs):
        started_at = attrs.get("started_at")
        ended_at = attrs.get("ended_at")
        if started_at is not None and ended_at is not None and started_at >= ended_at:
            raise serializers.ValidationError("started_at 必须早于 ended_at。")
        return attrs


class InstanceCatalogListQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, required=False)
    application = serializers.CharField(max_length=128, required=False, allow_blank=True)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=("active", "silent"), required=False)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    keyword = serializers.CharField(max_length=256, required=False, allow_blank=True)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的实例查询参数: {', '.join(unsupported)}")
        started_at = attrs.get("started_at")
        ended_at = attrs.get("ended_at")
        if started_at is not None and ended_at is not None and started_at >= ended_at:
            raise serializers.ValidationError("started_at 必须早于 ended_at。")
        return attrs


class ApmApplicationSerializer(serializers.ModelSerializer):
    organization_ids = serializers.SerializerMethodField()
    service_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ApmApplication
        fields = (
            "id",
            "application_id",
            "name",
            "description",
            "is_builtin",
            "service_count",
            "organization_ids",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )

    def get_organization_ids(self, obj):
        return list(obj.organization_links.order_by("organization").values_list("organization", flat=True))


class ApmServiceSerializer(serializers.ModelSerializer):
    application_id = serializers.CharField(source="application.application_id", read_only=True)
    application_name = serializers.CharField(source="application.name", read_only=True)
    organization_ids = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    environment_views = serializers.SerializerMethodField()

    class Meta:
        model = ApmService
        fields = (
            "id",
            "application_id",
            "application_name",
            "namespace",
            "name",
            "language",
            "first_seen_at",
            "last_seen_at",
            "archived_at",
            "archive_reason",
            "status",
            "environment_views",
            "organization_ids",
        )

    def get_organization_ids(self, obj):
        return list(obj.organization_links.order_by("organization").values_list("organization", flat=True))

    def get_status(self, obj):
        return catalog_status(last_seen_at=obj.last_seen_at, archived_at=obj.archived_at)

    def get_environment_views(self, obj):
        observed_at = timezone.now()
        views: dict[str, dict] = {}
        for instance in obj.instances.all():
            environment = instance.environment or ""
            current = views.get(environment)
            if current is None or instance.last_seen_at > current["last_seen_at"]:
                views[environment] = {
                    "environment": environment,
                    "last_seen_at": instance.last_seen_at,
                    "status": catalog_status(
                        last_seen_at=instance.last_seen_at,
                        observed_at=observed_at,
                    ),
                }
            elif current["status"] != "active":
                current["status"] = catalog_status(
                    last_seen_at=instance.last_seen_at,
                    observed_at=observed_at,
                )
        return [views[key] for key in sorted(views)]


class ApmServiceInstanceSerializer(serializers.ModelSerializer):
    service_namespace = serializers.CharField(source="service.namespace", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    application_id = serializers.CharField(source="service.application.application_id", read_only=True)
    application_name = serializers.CharField(source="service.application.name", read_only=True)
    organization_ids = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = ApmServiceInstance
        fields = (
            "id",
            "service_namespace",
            "service_name",
            "application_id",
            "application_name",
            "instance_id",
            "environment",
            "version",
            "permission_mode",
            "first_seen_at",
            "last_seen_at",
            "status",
            "organization_ids",
        )

    def get_organization_ids(self, obj):
        return list(obj.organization_links.order_by("organization").values_list("organization", flat=True))

    def get_status(self, obj):
        return catalog_status(last_seen_at=obj.last_seen_at)


class ApmSloSerializer(serializers.ModelSerializer):
    service_id = serializers.UUIDField(required=False)
    service_namespace = serializers.CharField(source="service.namespace", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = ApmSlo
        fields = (
            "id",
            "name",
            "service_id",
            "service_namespace",
            "service_name",
            "environment",
            "endpoint",
            "sli_type",
            "objective",
            "latency_threshold_ms",
            "evaluation_window",
            "is_enabled",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        extra_kwargs = {
            "name": {"max_length": 128},
            "environment": {"allow_blank": False},
            "endpoint": {"allow_blank": True},
            "objective": {"min_value": Decimal("0.001"), "max_value": Decimal("100")},
            "latency_threshold_ms": {"min_value": 1, "required": False, "allow_null": True},
        }

    def validate(self, attrs):
        if self.instance is None and "service_id" not in attrs:
            raise serializers.ValidationError({"service_id": "该字段必填。"})
        sli_type = attrs.get("sli_type", getattr(self.instance, "sli_type", None))
        threshold = attrs.get(
            "latency_threshold_ms",
            getattr(self.instance, "latency_threshold_ms", None),
        )
        if sli_type == ApmSlo.SliType.AVAILABILITY:
            attrs["latency_threshold_ms"] = None
        elif not threshold:
            raise serializers.ValidationError({"latency_threshold_ms": "时延 SLO 必须配置正数阈值。"})
        return attrs


class ServiceMetricQuerySerializer(serializers.Serializer):
    environment = serializers.CharField(max_length=256, allow_blank=True)
    endpoint = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的 RED 查询参数: {', '.join(unsupported)}")
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > MAX_METRIC_WINDOW:
            raise serializers.ValidationError("RED 查询时间窗不能超过 7 天")
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        return attrs


class TraceSearchSerializer(serializers.Serializer):
    service_namespace = serializers.CharField(max_length=256, required=False, allow_blank=True)
    service_name = serializers.CharField(max_length=256, required=False, allow_blank=False)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=True)
    instance_id = serializers.CharField(max_length=512, required=False)
    span_name = serializers.CharField(max_length=512, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=("ok", "error"), required=False)
    min_duration_ms = serializers.FloatField(required=False, min_value=0)
    max_duration_ms = serializers.FloatField(required=False, min_value=0)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    cursor = serializers.CharField(max_length=512, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的 Trace 查询参数: {', '.join(unsupported)}")
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        min_duration = attrs.get("min_duration_ms")
        max_duration = attrs.get("max_duration_ms")
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            raise serializers.ValidationError("min_duration_ms 不能大于 max_duration_ms")
        if attrs.get("span_name") == "":
            attrs.pop("span_name", None)
        return attrs


class SpanSearchSerializer(serializers.Serializer):
    service_namespace = serializers.CharField(max_length=256, required=False, allow_blank=True)
    service_name = serializers.CharField(max_length=256, required=False, allow_blank=False)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=True)
    instance_id = serializers.CharField(max_length=512, required=False)
    span_name = serializers.CharField(max_length=512, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=("ok", "error"), required=False)
    kind = serializers.ChoiceField(
        choices=("internal", "server", "client", "producer", "consumer"),
        required=False,
    )
    min_duration_ms = serializers.FloatField(required=False, min_value=0)
    max_duration_ms = serializers.FloatField(required=False, min_value=0)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    cursor = serializers.CharField(max_length=512, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的 Span 查询参数: {', '.join(unsupported)}")
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        min_duration = attrs.get("min_duration_ms")
        max_duration = attrs.get("max_duration_ms")
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            raise serializers.ValidationError("min_duration_ms 不能大于 max_duration_ms")
        if attrs.get("span_name") == "":
            attrs.pop("span_name", None)
        return attrs


class IssueSearchSerializer(serializers.Serializer):
    service_namespace = serializers.CharField(max_length=256, required=False, allow_blank=True)
    service_name = serializers.CharField(max_length=256, required=False, allow_blank=False)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=True)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    cursor = serializers.CharField(max_length=512, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的 Issue 查询参数: {', '.join(unsupported)}")
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > timedelta(days=7):
            raise serializers.ValidationError("Issue 查询时间窗不能超过 7 天")
        attrs.update(started_at=started_at, ended_at=ended_at)
        return attrs


class ApmPolicyNotificationTargetSerializer(serializers.Serializer):
    channel_id = serializers.IntegerField(min_value=1)
    channel_name = serializers.CharField(read_only=True)
    channel_type = serializers.CharField(read_only=True)
    delivery_mode = serializers.ChoiceField(choices=("message", "alert_event_copy"), read_only=True)
    recipient_mode = serializers.ChoiceField(choices=("none", "system_user", "free_text"), read_only=True)
    recipients = serializers.ListField(
        child=serializers.CharField(max_length=150),
        allow_empty=True,
        max_length=100,
    )


class ApmPolicyThresholdSerializer(serializers.Serializer):
    severity = serializers.ChoiceField(choices=ApmPolicy.Severity.choices)
    comparator = serializers.ChoiceField(choices=ApmPolicy.Comparator.choices)
    value = serializers.DecimalField(max_digits=20, decimal_places=6)


class ApmPolicySerializer(serializers.ModelSerializer):
    service_id = serializers.UUIDField(required=False)
    service_namespace = serializers.CharField(source="service.namespace", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    notification_targets = ApmPolicyNotificationTargetSerializer(many=True, required=False)
    thresholds = ApmPolicyThresholdSerializer(many=True, required=False, min_length=1, max_length=3)
    endpoints = serializers.ListField(
        child=serializers.CharField(max_length=512, allow_blank=False),
        required=False,
        allow_empty=True,
        max_length=100,
    )
    versions = serializers.ListField(
        child=serializers.CharField(max_length=256, allow_blank=False),
        required=False,
        allow_empty=True,
        max_length=100,
    )
    state = serializers.SerializerMethodField()

    class Meta:
        model = ApmPolicy
        fields = (
            "id",
            "name",
            "service_id",
            "service_namespace",
            "service_name",
            "environment",
            "alert_name",
            "endpoints",
            "version_mode",
            "versions",
            "metric_type",
            "evaluation_interval",
            "metric_window",
            "aggregation",
            "thresholds",
            "trigger_after",
            "recover_after",
            "no_data_after",
            "no_data_severity",
            "no_data_alert_name",
            "notification_targets",
            "is_enabled",
            "state",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        extra_kwargs = {
            "environment": {"allow_blank": False},
            "evaluation_interval": {"min_value": 1, "max_value": 60},
            "metric_window": {"min_value": 1, "max_value": 1440},
            "trigger_after": {"min_value": 1, "max_value": 60},
            "recover_after": {"min_value": 1, "max_value": 60},
            "no_data_after": {"min_value": 1, "max_value": 60, "allow_null": True},
        }

    def to_internal_value(self, data):
        unknown_fields = sorted(set(data) - set(self.fields))
        if unknown_fields:
            raise serializers.ValidationError({field: "APM 策略不支持该字段。" for field in unknown_fields})
        return super().to_internal_value(data)

    def get_state(self, obj):
        states = list(obj.target_states.all())
        active = next((state for state in states if state.status == ApmPolicyTargetState.Status.ACTIVE), None)
        last_succeeded_at = max((state.last_succeeded_at for state in states if state.last_succeeded_at), default=None)
        last_failed_at = max((state.last_failed_at for state in states if state.last_failed_at), default=None)
        return {
            "status": "active" if active else "normal",
            "consecutive_hits": active.consecutive_hits if active else 0,
            "consecutive_recoveries": active.consecutive_recoveries if active else 0,
            "last_succeeded_at": last_succeeded_at,
            "last_failed_at": last_failed_at,
        }

    def validate(self, attrs):
        if self.instance is None and "service_id" not in attrs:
            raise serializers.ValidationError({"service_id": "该字段必填。"})
        environment = attrs.get("environment", getattr(self.instance, "environment", ""))
        if not str(environment).strip():
            raise serializers.ValidationError({"environment": "环境必填。"})
        attrs["environment"] = str(environment).strip()

        metric_type = attrs.get("metric_type", getattr(self.instance, "metric_type", None))
        thresholds = attrs.get("thresholds")
        if thresholds is None:
            thresholds = list(getattr(self.instance, "thresholds", []) or [])
        if not thresholds:
            raise serializers.ValidationError({"thresholds": "至少配置一条告警阈值。"})
        normalized_thresholds = self._validate_thresholds(thresholds, metric_type)
        attrs["thresholds"] = normalized_thresholds

        endpoints = attrs.get("endpoints", list(getattr(self.instance, "endpoints", []) or []))
        attrs["endpoints"] = list(dict.fromkeys(item.strip() for item in endpoints))
        versions = attrs.get("versions", list(getattr(self.instance, "versions", []) or []))
        attrs["versions"] = list(dict.fromkeys(item.strip() for item in versions))
        version_mode = attrs.get("version_mode", getattr(self.instance, "version_mode", ApmPolicy.VersionMode.ALL))
        if version_mode == ApmPolicy.VersionMode.SPECIFIC and not attrs["versions"]:
            raise serializers.ValidationError({"versions": "指定版本模式必须至少选择一个版本。"})
        if version_mode != ApmPolicy.VersionMode.SPECIFIC and attrs["versions"]:
            raise serializers.ValidationError({"versions": "只有指定版本模式可以配置版本列表。"})

        no_data_after = attrs.get("no_data_after", getattr(self.instance, "no_data_after", None))
        no_data_severity = attrs.get("no_data_severity", getattr(self.instance, "no_data_severity", ""))
        if bool(no_data_after) != bool(no_data_severity):
            field = "no_data_severity" if no_data_after else "no_data_after"
            raise serializers.ValidationError({field: "无数据持续次数与级别必须同时配置或同时关闭。"})
        no_data_alert_name = attrs.get(
            "no_data_alert_name",
            getattr(self.instance, "no_data_alert_name", ""),
        )
        attrs["no_data_alert_name"] = str(no_data_alert_name).strip()

        notification_targets = attrs.get("notification_targets")
        if notification_targets is not None:
            channel_ids = [target["channel_id"] for target in notification_targets]
            if len(channel_ids) != len(set(channel_ids)):
                raise serializers.ValidationError({"notification_targets": "同一通知渠道不能重复选择。"})
        return attrs

    @staticmethod
    def _validate_thresholds(thresholds, metric_type):
        severity_rank = {"critical": 0, "error": 1, "warning": 2}
        normalized = []
        seen = set()
        comparators = set()
        for threshold in thresholds:
            severity = str(threshold["severity"])
            if severity in seen:
                raise serializers.ValidationError({"thresholds": "同一告警级别不能重复配置。"})
            seen.add(severity)
            comparator = str(threshold["comparator"])
            comparators.add(comparator)
            try:
                value = Decimal(str(threshold["value"]))
            except (InvalidOperation, TypeError, ValueError):
                raise serializers.ValidationError({"thresholds": "阈值必须是有限数值。"}) from None
            if not value.is_finite():
                raise serializers.ValidationError({"thresholds": "阈值必须是有限数值。"})
            if metric_type == ApmPolicy.MetricType.ERROR_RATE and not 0 <= value <= 1:
                raise serializers.ValidationError({"thresholds": "错误率阈值必须在 0 到 1 之间。"})
            normalized.append({"severity": severity, "comparator": comparator, "value": str(value)})
        if len(comparators) != 1:
            raise serializers.ValidationError({"thresholds": "多级阈值必须使用相同比较符。"})
        normalized.sort(key=lambda item: severity_rank[item["severity"]])
        values = [Decimal(item["value"]) for item in normalized]
        comparator = next(iter(comparators))
        valid = values == sorted(values, reverse=comparator in {"gt", "gte"})
        if not valid:
            raise serializers.ValidationError({"thresholds": "多级阈值必须按严重、错误、警告保持单调。"})
        return normalized


class ApmDeploymentEventSerializer(serializers.ModelSerializer):
    service_id = serializers.UUIDField(read_only=True)
    service_namespace = serializers.CharField(source="service.namespace", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = ApmDeploymentEvent
        fields = (
            "id",
            "service_id",
            "service_namespace",
            "service_name",
            "environment",
            "version",
            "deployed_at",
            "deployed_by",
            "status",
            "source",
        )


class ApmDeploymentQuerySerializer(serializers.Serializer):
    service_id = serializers.UUIDField(required=False)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=ApmDeploymentEvent.Status.choices, required=False)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)

    def validate_environment(self, value):
        return normalize_identity(value)

    def validate(self, attrs):
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(days=7)
        if ended_at <= started_at:
            raise serializers.ValidationError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > timedelta(days=90):
            raise serializers.ValidationError("部署事件查询时间窗不能超过 90 天")
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        if not attrs.get("environment"):
            attrs.pop("environment", None)
        return attrs


class ApmDashboardQuerySerializer(serializers.Serializer):
    window = serializers.ChoiceField(
        choices=("15m", "1h", "4h", "1d", "7d"),
        default="1h",
        required=False,
    )


class ApmEventQuerySerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    action = serializers.ChoiceField(choices=("triggered", "escalated", "recovered", "closed"), required=False)
    severity = serializers.ChoiceField(choices=("critical", "error", "warning"), required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)

    def validate(self, attrs):
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(days=7)
        if ended_at <= started_at:
            raise serializers.ValidationError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > timedelta(days=90):
            raise serializers.ValidationError("事件查询时间窗不能超过 90 天")
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        return attrs


class ApmAlertQuerySerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    status = serializers.ChoiceField(choices=("active", "recovered", "closed"), required=False)
    status_group = serializers.ChoiceField(choices=("active", "history"), required=False)
    severity = serializers.ChoiceField(choices=("critical", "error", "warning"), required=False)
    metric_type = serializers.ChoiceField(choices=ApmPolicy.MetricType.choices, required=False)
    service_id = serializers.UUIDField(required=False)
    keyword = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)

    def validate(self, attrs):
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(days=7)
        if ended_at <= started_at:
            raise serializers.ValidationError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > timedelta(days=90):
            raise serializers.ValidationError("告警查询时间窗不能超过 90 天")
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        return attrs


class NotificationDeliveryQuerySerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=320, required=False)
    status = serializers.ChoiceField(choices=("pending", "delivered", "failed"), required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)


class NotificationRecipientQuerySerializer(serializers.Serializer):
    search = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=100, default=100)


class NotificationDeliveryRetrySerializer(serializers.Serializer):
    recipients = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
        allow_empty=True,
        max_length=100,
    )

    def validate_recipients(self, value):
        return list(dict.fromkeys(item.strip() for item in value))
