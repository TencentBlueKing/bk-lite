from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.apm.models import ApmIngestSource, ApmPolicy, ApmService, ApmServiceInstance
from apps.apm.services.status import catalog_status


class OrganizationAssignmentSerializer(serializers.Serializer):
    organization_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_organization_ids(self, value):
        return sorted(set(value))


class CreateIngestSourceSerializer(OrganizationAssignmentSerializer):
    name = serializers.CharField(max_length=128)
    ingest_type = serializers.ChoiceField(choices=ApmIngestSource.IngestType.choices)
    cloud_region_id = serializers.IntegerField(required=False, allow_null=True)
    environment_hint = serializers.CharField(max_length=128, required=False, allow_blank=True)


class ApmIngestSourceSerializer(serializers.ModelSerializer):
    organization_ids = serializers.SerializerMethodField()
    missing_instance_identity = serializers.SerializerMethodField()

    class Meta:
        model = ApmIngestSource
        fields = (
            "id",
            "name",
            "ingest_type",
            "cloud_region_id",
            "environment_hint",
            "credential_prefix",
            "is_enabled",
            "first_received_at",
            "last_received_at",
            "last_missing_instance_identity_at",
            "missing_instance_identity",
            "organization_ids",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )

    def get_organization_ids(self, obj):
        return list(obj.organization_links.order_by("organization").values_list("organization", flat=True))

    def get_missing_instance_identity(self, obj):
        missing_at = obj.last_missing_instance_identity_at
        return missing_at is not None and missing_at >= timezone.now() - timedelta(minutes=15)


class ApmServiceSerializer(serializers.ModelSerializer):
    organization_ids = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    environment_views = serializers.SerializerMethodField()

    class Meta:
        model = ApmService
        fields = (
            "id",
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
    ingest_source_name = serializers.CharField(source="ingest_source.name", read_only=True)
    organization_ids = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = ApmServiceInstance
        fields = (
            "id",
            "service_namespace",
            "service_name",
            "instance_id",
            "environment",
            "version",
            "ingest_source_id",
            "ingest_source_name",
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


class ServiceMetricQuerySerializer(serializers.Serializer):
    environment = serializers.CharField(max_length=256, allow_blank=True)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
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
        if notice and not notice_type_ids:
            raise serializers.ValidationError({"notice_type_ids": "启用通知时至少选择一个渠道。"})
        if "notice_type_ids" in attrs:
            attrs["notice_type_ids"] = sorted(set(notice_type_ids))
        if "notice_users" in attrs:
            attrs["notice_users"] = list(dict.fromkeys(attrs["notice_users"]))
        return attrs


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
