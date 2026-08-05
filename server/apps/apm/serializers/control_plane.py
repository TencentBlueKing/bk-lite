from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.apm.models import ApmApplication, ApmPolicy, ApmService, ApmServiceInstance, ApmSlo
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
    is_enabled = serializers.BooleanField(required=False)

    def validate_application_id(self, value):
        if ApmApplication.objects.filter(application_id=value).exists():
            raise serializers.ValidationError("该应用 ID 已存在。")
        return value

    def validate(self, attrs):
        if self.context.get("creating") and not attrs.get("application_id"):
            raise serializers.ValidationError({"application_id": "该字段必填。"})
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
            "is_enabled",
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
                        archived_at=instance.archived_at,
                        observed_at=observed_at,
                    ),
                }
            elif current["status"] != "active" and instance.archived_at is None:
                current["status"] = catalog_status(
                    last_seen_at=instance.last_seen_at,
                    archived_at=instance.archived_at,
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
            "archived_at",
            "archive_reason",
            "status",
            "organization_ids",
        )

    def get_organization_ids(self, obj):
        return list(obj.organization_links.order_by("organization").values_list("organization", flat=True))

    def get_status(self, obj):
        return catalog_status(last_seen_at=obj.last_seen_at, archived_at=obj.archived_at)


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
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的 RED 查询参数: {', '.join(unsupported)}")
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        return attrs


class TraceSearchSerializer(serializers.Serializer):
    service_namespace = serializers.CharField(max_length=256, required=False, allow_blank=True)
    service_name = serializers.CharField(max_length=256)
    environment = serializers.CharField(max_length=256, allow_blank=True)
    instance_id = serializers.CharField(max_length=512, required=False)
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


class ApmPolicySerializer(serializers.ModelSerializer):
    service_id = serializers.UUIDField(required=False)
    service_namespace = serializers.CharField(source="service.namespace", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    notice_type_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    notice_users = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
        allow_empty=True,
    )
    notification_targets = ApmPolicyNotificationTargetSerializer(many=True, required=False)
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
            "metric_type",
            "comparator",
            "threshold",
            "duration_window",
            "recovery_window",
            "severity",
            "notice",
            "notice_type_ids",
            "notice_users",
            "notification_targets",
            "is_enabled",
            "state",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        extra_kwargs = {
            "environment": {"allow_blank": True},
            "duration_window": {"min_value": 1, "max_value": 1440},
            "recovery_window": {"min_value": 1, "max_value": 1440},
        }

    def get_state(self, obj):
        state = getattr(obj, "state", None)
        if state is None:
            return None
        return {
            "status": state.status,
            "consecutive_hits": state.consecutive_hits,
            "consecutive_recoveries": state.consecutive_recoveries,
            "last_succeeded_at": state.last_succeeded_at,
            "last_failed_at": state.last_failed_at,
        }

    def validate(self, attrs):
        if self.instance is None and "service_id" not in attrs:
            raise serializers.ValidationError({"service_id": "该字段必填。"})
        metric_type = attrs.get("metric_type", getattr(self.instance, "metric_type", None))
        threshold = attrs.get("threshold", getattr(self.instance, "threshold", None))
        if metric_type == ApmPolicy.MetricType.ERROR_RATE and threshold is not None:
            if threshold < 0 or threshold > 1:
                raise serializers.ValidationError({"threshold": "错误率阈值必须在 0 到 1 之间。"})
        notice = attrs.get("notice", getattr(self.instance, "notice", False))
        notice_type_ids = attrs.get(
            "notice_type_ids",
            getattr(self.instance, "notice_type_ids", []),
        )
        notification_targets = attrs.get("notification_targets")
        existing_targets = list(self.instance.notification_targets.values_list("channel_id", flat=True)) if self.instance is not None else []
        if notice and not notice_type_ids and not notification_targets and not existing_targets:
            raise serializers.ValidationError({"notification_targets": "启用通知时至少选择一个渠道。"})
        if notification_targets is not None:
            channel_ids = [target["channel_id"] for target in notification_targets]
            if len(channel_ids) != len(set(channel_ids)):
                raise serializers.ValidationError({"notification_targets": "同一通知渠道不能重复选择。"})
        if "notice_type_ids" in attrs:
            attrs["notice_type_ids"] = sorted(set(notice_type_ids))
        if "notice_users" in attrs:
            attrs["notice_users"] = list(dict.fromkeys(attrs["notice_users"]))
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        targets = list(instance.notification_targets.all())
        if targets:
            data["notice_type_ids"] = [target.channel_id for target in targets]
            recipients = []
            for target in targets:
                for recipient in target.recipients:
                    if recipient not in recipients:
                        recipients.append(recipient)
            data["notice_users"] = recipients
        return data


class ApmEventQuerySerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    action = serializers.ChoiceField(choices=("created", "recovery"), required=False)
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
