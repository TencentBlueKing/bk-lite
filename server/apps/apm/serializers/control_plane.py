import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework import serializers

from apps.apm.models import ApmApplication, ApmDeploymentEvent, ApmPolicy, ApmPolicyTargetState, ApmService, ApmServiceInstance, ApmSlo
from apps.apm.services.identity import normalize_identity
from apps.apm.services.policies import MAX_POLICY_TARGETS
from apps.apm.services.policy_conditions import MIRROR_FIELDS, REQUEST_COUNT_METRIC, anchor_from_policy, compare_window_key
from apps.apm.services.query import MAX_METRIC_WINDOW
from apps.apm.services.status import catalog_status
from apps.apm.utils.locale_text import serializer_text


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
    )
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(max_length=512, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["application_id"].error_messages["invalid"] = serializer_text(self, "error.application_id_invalid")

    def validate_application_id(self, value):
        if not self.context.get("creating"):
            return value
        if ApmApplication.objects.filter(application_id=value).exists():
            raise serializers.ValidationError(serializer_text(self, "error.application_id_exists"))
        return value

    def validate(self, attrs):
        if self.context.get("creating") and not attrs.get("application_id"):
            raise serializers.ValidationError({"application_id": serializer_text(self, "error.field_required")})
        if not self.context.get("creating"):
            attrs.pop("application_id", None)
        return attrs


class IngestSnippetSerializer(serializers.Serializer):
    application_id = serializers.CharField(max_length=128)
    cloud_region_id = serializers.IntegerField(min_value=1)
    language = serializers.ChoiceField(choices=("python", "nodejs", "java", "go", "dotnet"))
    runtime = serializers.ChoiceField(choices=("kubernetes", "docker", "host", "other"))
    endpoint = serializers.CharField(max_length=512, required=False, write_only=True)
    service_name = serializers.CharField(max_length=256)
    service_version = serializers.CharField(max_length=256, required=False, allow_blank=True)
    environment = serializers.CharField(max_length=256, allow_blank=True)
    sample_rate = serializers.IntegerField(min_value=1, max_value=100, required=False, default=100)

    def validate_endpoint(self, _value):
        raise serializers.ValidationError(serializer_text(self, "error.otlp_endpoint_server_resolved"))


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
    unassigned = serializers.BooleanField(required=False)

    def validate(self, attrs):
        started_at = attrs.get("started_at")
        ended_at = attrs.get("ended_at")
        if started_at is not None and ended_at is not None and started_at >= ended_at:
            raise serializers.ValidationError(serializer_text(self, "error.started_before_ended"))
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
    unassigned = serializers.BooleanField(required=False)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_instance_query", names=", ".join(unsupported)))
        started_at = attrs.get("started_at")
        ended_at = attrs.get("ended_at")
        if started_at is not None and ended_at is not None and started_at >= ended_at:
            raise serializers.ValidationError(serializer_text(self, "error.started_before_ended"))
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
            raise serializers.ValidationError({"service_id": serializer_text(self, "error.field_required")})
        sli_type = attrs.get("sli_type", getattr(self.instance, "sli_type", None))
        threshold = attrs.get(
            "latency_threshold_ms",
            getattr(self.instance, "latency_threshold_ms", None),
        )
        if sli_type == ApmSlo.SliType.AVAILABILITY:
            attrs["latency_threshold_ms"] = None
        elif not threshold:
            raise serializers.ValidationError({"latency_threshold_ms": serializer_text(self, "error.latency_threshold_positive")})
        return attrs


class ServiceMetricQuerySerializer(serializers.Serializer):
    environment = serializers.CharField(max_length=256, allow_blank=True)
    endpoint = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    include_breakdown = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_red_query", names=", ".join(unsupported)))
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > MAX_METRIC_WINDOW:
            raise serializers.ValidationError(serializer_text(self, "error.red_window_limit"))
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        return attrs


class ServiceMetricBatchTargetSerializer(serializers.Serializer):
    service_id = serializers.UUIDField()
    environment = serializers.CharField(max_length=256, allow_blank=True)


class ServiceMetricBatchSerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    include_breakdown = serializers.BooleanField(required=False, default=True)
    targets = ServiceMetricBatchTargetSerializer(many=True)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_batch_red_query", names=", ".join(unsupported)))
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > MAX_METRIC_WINDOW:
            raise serializers.ValidationError(serializer_text(self, "error.red_window_limit"))
        targets = attrs.get("targets") or []
        if not targets:
            raise serializers.ValidationError({"targets": serializer_text(self, "error.field_not_empty")})
        if len(targets) > 40:
            raise serializers.ValidationError({"targets": serializer_text(self, "error.batch_red_target_limit", count=40)})
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        return attrs


class ServiceErrorBreakdownQuerySerializer(serializers.Serializer):
    environment = serializers.CharField(max_length=256, allow_blank=True)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    sample_limit = serializers.IntegerField(min_value=1, max_value=50, default=20)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_error_query", names=", ".join(unsupported)))
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > MAX_METRIC_WINDOW:
            raise serializers.ValidationError(serializer_text(self, "error.error_window_limit"))
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
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_trace_query", names=", ".join(unsupported)))
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        min_duration = attrs.get("min_duration_ms")
        max_duration = attrs.get("max_duration_ms")
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            raise serializers.ValidationError(serializer_text(self, "error.duration_range"))
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
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_span_query", names=", ".join(unsupported)))
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        min_duration = attrs.get("min_duration_ms")
        max_duration = attrs.get("max_duration_ms")
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            raise serializers.ValidationError(serializer_text(self, "error.duration_range"))
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
    entry_only = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(serializer_text(self, "error.unsupported_issue_query", names=", ".join(unsupported)))
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > timedelta(days=7):
            raise serializers.ValidationError(serializer_text(self, "error.issue_window_limit"))
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


class PolicyOrganizationsField(serializers.ListField):
    def get_attribute(self, instance):
        return list(instance.organization_links.order_by("organization").values_list("organization", flat=True))


class ApmPolicySerializer(serializers.ModelSerializer):
    service_id = serializers.UUIDField(required=False)
    scope_mode = serializers.ChoiceField(choices=ApmPolicy.ScopeMode.choices, required=False)
    service_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True, max_length=20)
    application = serializers.PrimaryKeyRelatedField(queryset=ApmApplication.objects.all(), required=False, allow_null=True)
    endpoint_mode = serializers.ChoiceField(choices=ApmPolicy.EndpointMode.choices, required=False)
    instance_mode = serializers.ChoiceField(choices=ApmPolicy.InstanceMode.choices, required=False)
    target_kind = serializers.ChoiceField(choices=ApmPolicy.TargetKind.choices, required=False)
    dependencies = serializers.ListField(child=serializers.DictField(), required=False, allow_empty=True, max_length=20)
    service_namespace = serializers.CharField(source="service.namespace", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    organizations = PolicyOrganizationsField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False,
    )
    notification_targets = ApmPolicyNotificationTargetSerializer(many=True, required=False)
    thresholds = ApmPolicyThresholdSerializer(many=True, required=False, min_length=1, max_length=3)
    compare_mode = serializers.ChoiceField(choices=ApmPolicy.CompareMode.choices, required=False)
    compare_offset_amount = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    compare_value_kind = serializers.ChoiceField(
        choices=(("delta", "delta"), ("percent", "percent")),
        required=False,
        allow_blank=True,
    )
    min_request_count = serializers.IntegerField(min_value=1, max_value=100000, required=False, allow_null=True)
    slow_threshold_ms = serializers.IntegerField(required=False, allow_null=True)
    apdex_threshold_ms = serializers.IntegerField(required=False, allow_null=True)
    trigger_window = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=20)
    recovery_threshold = serializers.JSONField(required=False, allow_null=True)
    conditions = serializers.JSONField(required=False)
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
            "scope_mode",
            "service_ids",
            "application",
            "endpoint_mode",
            "instance_mode",
            "target_kind",
            "dependencies",
            "service_namespace",
            "service_name",
            "organizations",
            "environment",
            "alert_name",
            "endpoints",
            "version_mode",
            "versions",
            "metric_type",
            "evaluation_interval",
            "metric_window",
            "aggregation",
            "compare_mode",
            "compare_offset_amount",
            "compare_value_kind",
            "min_request_count",
            "slow_threshold_ms",
            "apdex_threshold_ms",
            "thresholds",
            "conditions",
            "trigger_after",
            "trigger_window",
            "recovery_threshold",
            "recover_after",
            "no_data_after",
            "no_data_severity",
            "no_data_alert_name",
            "notification_targets",
            "handlers",
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
            raise serializers.ValidationError({field: serializer_text(self, "error.policy_field_unsupported") for field in unknown_fields})
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

    def validate_organizations(self, value):
        return sorted(set(value))

    _CONDITION_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,15}$")
    _REGULAR_KEYS = frozenset(
        {
            "ref",
            "role",
            "metric_type",
            "aggregation",
            "compare_mode",
            "compare_offset_amount",
            "compare_value_kind",
            "min_request_count",
            "slow_threshold_ms",
            "apdex_threshold_ms",
            "thresholds",
        }
    )
    _GUARD_KEYS = frozenset({"ref", "role", "metric_type", "comparator", "value"})

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data.get("conditions"):
            data["conditions"] = [anchor_from_policy(instance)]
        return data

    def _condition_error(self, key):
        raise serializers.ValidationError({"conditions": serializer_text(self, key)})

    def _validate_condition_list(self, raw, metric_window):
        if not isinstance(raw, list):
            self._condition_error("error.conditions_shape")
        regulars = []
        guards = []
        refs = []
        for item in raw:
            if not isinstance(item, dict):
                self._condition_error("error.conditions_shape")
            if "recovery_threshold" in item:
                self._condition_error("error.conditions_recovery_anchor")
            role = item.get("role")
            if role == "guard":
                normalized = self._normalize_guard(item)
                guards.append(normalized)
            elif role == "regular":
                normalized = self._normalize_regular(item, metric_window)
                regulars.append(normalized)
            else:
                self._condition_error("error.conditions_shape")
            refs.append(normalized["ref"])
        if not 1 <= len(regulars) <= 3:
            self._condition_error("error.conditions_count")
        if len(guards) > 2:
            self._condition_error("error.conditions_guard_count")
        if len(refs) != len(set(refs)):
            self._condition_error("error.conditions_ref_duplicate")
        windows = {key for key in (compare_window_key(item) for item in regulars) if key is not None}
        if len(windows) > 2:
            self._condition_error("error.conditions_windows")
        no_traffic = [item for item in regulars if item["metric_type"] == ApmPolicy.MetricType.NO_TRAFFIC]
        if no_traffic and (len(regulars) != 1 or guards or no_traffic[0]["compare_mode"] != ApmPolicy.CompareMode.ABSOLUTE):
            self._condition_error("error.conditions_no_traffic")
        return regulars + guards

    def _clean_ref(self, item):
        ref = str(item.get("ref") or "")
        if not self._CONDITION_REF.match(ref):
            self._condition_error("error.conditions_shape")
        return ref

    def _normalize_guard(self, item):
        unknown = set(item) - self._GUARD_KEYS
        if unknown or item.get("metric_type") == ApmPolicy.MetricType.NO_TRAFFIC:
            self._condition_error("error.conditions_guard_shape")
        metric_type = str(item.get("metric_type") or "")
        allowed = {choice for choice, _label in ApmPolicy.MetricType.choices} | {REQUEST_COUNT_METRIC}
        if metric_type not in allowed:
            self._condition_error("error.conditions_shape")
        comparator = str(item.get("comparator") or "")
        if comparator not in {choice for choice, _label in ApmPolicy.Comparator.choices}:
            self._condition_error("error.conditions_shape")
        value = self._finite_decimal(item.get("value"), "conditions", "error.threshold_finite")
        return {
            "ref": self._clean_ref(item),
            "role": "guard",
            "metric_type": metric_type,
            "comparator": comparator,
            "value": self._decimal_payload(value),
        }

    def _normalize_regular(self, item, metric_window):
        if set(item) - self._REGULAR_KEYS:
            self._condition_error("error.conditions_shape")
        metric_type = str(item.get("metric_type") or "")
        if metric_type not in {choice for choice, _label in ApmPolicy.MetricType.choices}:
            self._condition_error("error.conditions_shape")
        aggregation = str(item.get("aggregation") or ApmPolicy.Aggregation.AVERAGE)
        if aggregation not in {choice for choice, _label in ApmPolicy.Aggregation.choices}:
            self._condition_error("error.conditions_shape")
        if metric_type in ApmPolicy.COUNT_METRIC_TYPES:
            aggregation = ApmPolicy.Aggregation.AVERAGE
        compare_mode = str(item.get("compare_mode") or ApmPolicy.CompareMode.ABSOLUTE)
        if compare_mode not in {choice for choice, _label in ApmPolicy.CompareMode.choices}:
            self._condition_error("error.conditions_shape")
        compare_value_kind = item.get("compare_value_kind") or ""
        compare_offset_amount = item.get("compare_offset_amount")
        min_request_count = item.get("min_request_count")
        slow_threshold_ms, apdex_threshold_ms = self._validate_metric_params(
            metric_type,
            item.get("slow_threshold_ms"),
            item.get("apdex_threshold_ms"),
        )
        self._validate_compare(
            metric_type,
            compare_mode,
            compare_value_kind,
            min_request_count,
            metric_window,
            compare_offset_amount,
        )
        if compare_mode not in {
            ApmPolicy.CompareMode.OFFSET_HOURS,
            ApmPolicy.CompareMode.OFFSET_DAYS,
            ApmPolicy.CompareMode.BASELINE_DAYS,
        }:
            compare_offset_amount = None
        thresholds = item.get("thresholds")
        if not isinstance(thresholds, list) or not thresholds:
            self._condition_error("error.conditions_shape")
        normalized = self._validate_thresholds(thresholds, metric_type, compare_mode, compare_value_kind)
        return {
            "ref": self._clean_ref(item),
            "role": "regular",
            "metric_type": metric_type,
            "aggregation": aggregation,
            "compare_mode": compare_mode,
            "compare_offset_amount": compare_offset_amount,
            "compare_value_kind": compare_value_kind or "",
            "min_request_count": min_request_count,
            "slow_threshold_ms": slow_threshold_ms,
            "apdex_threshold_ms": apdex_threshold_ms,
            "thresholds": normalized,
        }

    def _validated_anchor_fields(self, attrs, metric_type, compare_mode, compare_value_kind, min_request_count):
        if "aggregation" in attrs:
            aggregation = attrs["aggregation"]
        elif self.instance is not None:
            aggregation = self.instance.aggregation
        else:
            aggregation = ApmPolicy.Aggregation.AVERAGE
        return {
            "metric_type": metric_type,
            "aggregation": aggregation,
            "compare_mode": compare_mode or ApmPolicy.CompareMode.ABSOLUTE,
            "compare_offset_amount": attrs.get("compare_offset_amount"),
            "compare_value_kind": compare_value_kind or "",
            "min_request_count": min_request_count,
            "slow_threshold_ms": attrs.get("slow_threshold_ms"),
            "apdex_threshold_ms": attrs.get("apdex_threshold_ms"),
            "thresholds": list(attrs.get("thresholds") or []),
        }

    def validate(self, attrs):
        initial = self.initial_data if isinstance(getattr(self, "initial_data", None), dict) else {}
        scope_mode = attrs.get(
            "scope_mode",
            getattr(self.instance, "scope_mode", ApmPolicy.ScopeMode.SERVICE) or ApmPolicy.ScopeMode.SERVICE,
        )
        if self.instance is None and "service_id" not in attrs and scope_mode == ApmPolicy.ScopeMode.SERVICE:
            raise serializers.ValidationError({"service_id": serializer_text(self, "error.field_required")})
        environment = attrs.get("environment", getattr(self.instance, "environment", ""))
        if not str(environment).strip():
            raise serializers.ValidationError({"environment": serializer_text(self, "error.environment_required")})
        attrs["environment"] = str(environment).strip()
        self._conditions_supplied = "conditions" in initial
        if self._conditions_supplied:
            metric_window = self._stored_or_incoming(attrs, "metric_window", 5)
            self._pending_conditions = self._validate_condition_list(attrs.get("conditions"), metric_window)
            anchor = next(item for item in self._pending_conditions if item["role"] == "regular")
            for field in MIRROR_FIELDS:
                attrs[field] = anchor[field]

        metric_type = attrs.get("metric_type", getattr(self.instance, "metric_type", None))
        compare_mode = self._stored_or_incoming(attrs, "compare_mode", ApmPolicy.CompareMode.ABSOLUTE)
        compare_value_kind = self._stored_or_incoming(attrs, "compare_value_kind", "")
        compare_offset_amount = self._stored_or_incoming(attrs, "compare_offset_amount", None)
        metric_window = self._stored_or_incoming(attrs, "metric_window", 5)
        min_request_count = self._stored_or_incoming(attrs, "min_request_count", None)
        slow_threshold_ms = self._stored_or_incoming(attrs, "slow_threshold_ms", None)
        apdex_threshold_ms = self._stored_or_incoming(attrs, "apdex_threshold_ms", None)
        slow_threshold_ms, apdex_threshold_ms = self._validate_metric_params(
            metric_type,
            slow_threshold_ms,
            apdex_threshold_ms,
        )
        attrs["slow_threshold_ms"] = slow_threshold_ms
        attrs["apdex_threshold_ms"] = apdex_threshold_ms
        if metric_type in ApmPolicy.COUNT_METRIC_TYPES:
            attrs["aggregation"] = ApmPolicy.Aggregation.AVERAGE
        self._validate_compare(
            metric_type,
            compare_mode,
            compare_value_kind,
            min_request_count,
            metric_window,
            compare_offset_amount,
        )
        attrs["compare_offset_amount"] = (
            compare_offset_amount
            if compare_mode
            in {
                ApmPolicy.CompareMode.OFFSET_HOURS,
                ApmPolicy.CompareMode.OFFSET_DAYS,
                ApmPolicy.CompareMode.BASELINE_DAYS,
            }
            else None
        )
        thresholds = attrs.get("thresholds")
        if thresholds is None:
            thresholds = list(getattr(self.instance, "thresholds", []) or [])
        if not thresholds:
            raise serializers.ValidationError({"thresholds": serializer_text(self, "error.threshold_required")})
        normalized_thresholds = self._validate_thresholds(thresholds, metric_type, compare_mode, compare_value_kind)
        attrs["thresholds"] = normalized_thresholds

        endpoints = attrs.get("endpoints", list(getattr(self.instance, "endpoints", []) or []))
        attrs["endpoints"] = list(dict.fromkeys(item.strip() for item in endpoints))
        self._apply_scope(attrs, initial)
        self._apply_target(attrs, initial)
        versions = attrs.get("versions", list(getattr(self.instance, "versions", []) or []))
        attrs["versions"] = list(dict.fromkeys(item.strip() for item in versions))
        version_mode = attrs.get("version_mode", getattr(self.instance, "version_mode", ApmPolicy.VersionMode.ALL))
        if version_mode == ApmPolicy.VersionMode.SPECIFIC and not attrs["versions"]:
            raise serializers.ValidationError({"versions": serializer_text(self, "error.versions_required")})
        if version_mode != ApmPolicy.VersionMode.SPECIFIC and attrs["versions"]:
            raise serializers.ValidationError({"versions": serializer_text(self, "error.versions_mode_only")})
        if version_mode == ApmPolicy.VersionMode.SPECIFIC:
            combination_count = max(1, len(attrs["endpoints"])) * len(attrs["versions"])
            if combination_count > MAX_POLICY_TARGETS:
                raise serializers.ValidationError({"endpoints": serializer_text(self, "error.policy_target_limit", count=MAX_POLICY_TARGETS)})

        no_data_after = attrs.get("no_data_after", getattr(self.instance, "no_data_after", None))
        no_data_severity = attrs.get("no_data_severity", getattr(self.instance, "no_data_severity", ""))
        if bool(no_data_after) != bool(no_data_severity):
            field = "no_data_severity" if no_data_after else "no_data_after"
            raise serializers.ValidationError({field: serializer_text(self, "error.no_data_pair")})
        no_data_alert_name = attrs.get(
            "no_data_alert_name",
            getattr(self.instance, "no_data_alert_name", ""),
        )
        attrs["no_data_alert_name"] = str(no_data_alert_name).strip()

        self._validate_judgment(
            attrs,
            metric_type=metric_type,
            thresholds=normalized_thresholds,
            compare_mode=compare_mode,
            compare_value_kind=compare_value_kind,
        )

        notification_targets = attrs.get("notification_targets")
        if notification_targets is not None:
            channel_ids = [target["channel_id"] for target in notification_targets]
            if len(channel_ids) != len(set(channel_ids)):
                raise serializers.ValidationError({"notification_targets": serializer_text(self, "error.channel_duplicate")})
        self._validate_policy_handlers(attrs)
        anchor_fields = self._validated_anchor_fields(attrs, metric_type, compare_mode, compare_value_kind, min_request_count)
        if getattr(self, "_conditions_supplied", False):
            synced = []
            replaced = False
            for item in self._pending_conditions:
                if item["role"] == "regular" and not replaced:
                    updated = dict(item)
                    updated.update(anchor_fields)
                    synced.append(updated)
                    replaced = True
                else:
                    synced.append(item)
            attrs["conditions"] = synced
        elif self.instance is None or any(field in initial for field in MIRROR_FIELDS):
            attrs["conditions"] = [{"ref": "a", "role": "regular", **anchor_fields}]
        return attrs

    def _apply_scope(self, attrs, initial):
        scope_mode = attrs.get(
            "scope_mode",
            getattr(self.instance, "scope_mode", ApmPolicy.ScopeMode.SERVICE) or ApmPolicy.ScopeMode.SERVICE,
        )
        if scope_mode == ApmPolicy.ScopeMode.SERVICES:
            raw_ids = attrs.get("service_ids", list(getattr(self.instance, "service_ids", None) or []))
            ordered = []
            for item in raw_ids:
                text = str(item)
                if text not in ordered:
                    ordered.append(text)
            if not 2 <= len(ordered) <= 20:
                raise serializers.ValidationError({"service_ids": serializer_text(self, "error.scope_service_ids")})
            found = {str(item.id): item for item in ApmService.objects.filter(id__in=ordered)}
            if len(found) != len(ordered):
                raise serializers.ValidationError({"service_ids": serializer_text(self, "error.scope_service_ids")})
            attrs["scope_mode"] = scope_mode
            attrs["service_ids"] = ordered
            attrs["service_id"] = found[ordered[0]].id
            attrs["application"] = None
        elif scope_mode == ApmPolicy.ScopeMode.APPLICATION:
            application = attrs.get("application", getattr(self.instance, "application", None))
            if application is None:
                raise serializers.ValidationError({"application": serializer_text(self, "error.scope_application_required")})
            first = (
                ApmService.objects.filter(application=application, archived_at__isnull=True)
                .order_by("normalized_namespace", "normalized_name", "id")
                .first()
            )
            if first is None:
                raise serializers.ValidationError({"application": serializer_text(self, "error.scope_application_empty")})
            attrs["scope_mode"] = scope_mode
            attrs["application"] = application
            attrs["service_ids"] = []
            attrs["service_id"] = first.id
        else:
            attrs["scope_mode"] = ApmPolicy.ScopeMode.SERVICE
            attrs["service_ids"] = []
            attrs["application"] = None

        if "endpoint_mode" in initial:
            endpoint_mode = attrs.get("endpoint_mode") or ApmPolicy.EndpointMode.SERVICE
        elif attrs.get("endpoints"):
            endpoint_mode = ApmPolicy.EndpointMode.SELECTED
        else:
            endpoint_mode = getattr(self.instance, "endpoint_mode", None) or ApmPolicy.EndpointMode.SERVICE
            if endpoint_mode == ApmPolicy.EndpointMode.SELECTED and not attrs.get("endpoints"):
                endpoint_mode = ApmPolicy.EndpointMode.SERVICE
        if endpoint_mode in {ApmPolicy.EndpointMode.SERVICE, ApmPolicy.EndpointMode.ALL}:
            attrs["endpoints"] = []
        attrs["endpoint_mode"] = endpoint_mode
        attrs["instance_mode"] = attrs.get(
            "instance_mode",
            getattr(self.instance, "instance_mode", None) or ApmPolicy.InstanceMode.ALL,
        )

    def _apply_target(self, attrs, initial):
        if "target_kind" in initial:
            target_kind = attrs.get("target_kind") or ApmPolicy.TargetKind.ENTRY
        else:
            target_kind = getattr(self.instance, "target_kind", None) or ApmPolicy.TargetKind.ENTRY
        attrs["target_kind"] = target_kind
        if target_kind != ApmPolicy.TargetKind.DEPENDENCY:
            attrs["dependencies"] = []
            return
        if attrs.get("endpoint_mode") != ApmPolicy.EndpointMode.SERVICE or attrs.get("instance_mode") == ApmPolicy.InstanceMode.GROUPED:
            raise serializers.ValidationError({"target_kind": serializer_text(self, "error.dependency_scope")})
        metrics = [attrs.get("metric_type", getattr(self.instance, "metric_type", None))]
        for condition in list(attrs.get("conditions") or getattr(self.instance, "conditions", None) or []):
            if isinstance(condition, dict):
                metrics.append(condition.get("metric_type"))
        blocked = {ApmPolicy.MetricType.APDEX, ApmPolicy.MetricType.NO_TRAFFIC}
        if any(item in blocked for item in metrics):
            raise serializers.ValidationError({"target_kind": serializer_text(self, "error.dependency_metric")})
        raw = attrs.get("dependencies")
        if raw is None:
            raw = list(getattr(self.instance, "dependencies", None) or [])
        normalized = []
        for item in raw:
            if not isinstance(item, dict):
                raise serializers.ValidationError({"dependencies": serializer_text(self, "error.dependency_item")})
            channel = str(item.get("channel") or "").strip()
            system = str(item.get("system") or "").strip()
            statement = str(item.get("statement") or "").strip()
            if channel not in {"database", "outbound", "http"} or not system or not statement:
                raise serializers.ValidationError({"dependencies": serializer_text(self, "error.dependency_item")})
            normalized.append({"channel": channel, "system": system, "statement": statement})
        attrs["dependencies"] = normalized
        attrs["endpoints"] = []
        attrs["endpoint_mode"] = ApmPolicy.EndpointMode.SERVICE
        attrs["instance_mode"] = ApmPolicy.InstanceMode.ALL

    def _policy_organization_ids(self, attrs):
        if "organizations" in attrs:
            return attrs.get("organizations") or []
        if self.instance is not None:
            return list(self.instance.organization_links.values_list("organization", flat=True))
        return []

    def _validate_policy_handlers(self, attrs):
        handlers_provided = "handlers" in attrs
        organizations_provided = "organizations" in attrs
        if not handlers_provided and not organizations_provided:
            return
        from apps.apm.services.alerts import AlertHandlerInvalid, DjangoApmAlertService

        handlers = attrs["handlers"] if handlers_provided else list(getattr(self.instance, "handlers", None) or [])
        try:
            resolved = DjangoApmAlertService.normalize_policy_handlers(handlers, self._policy_organization_ids(attrs))
        except AlertHandlerInvalid as exc:
            raise serializers.ValidationError({"handlers": str(exc)}) from exc
        if handlers_provided:
            attrs["handlers"] = resolved

    def _validate_judgment(self, attrs, *, metric_type, thresholds, compare_mode, compare_value_kind):
        trigger_window = self._stored_or_incoming(attrs, "trigger_window", None)
        recovery = self._stored_or_incoming(attrs, "recovery_threshold", {}) or {}
        trigger_after = self._stored_or_incoming(attrs, "trigger_after", 1)
        if metric_type == ApmPolicy.MetricType.NO_TRAFFIC and (trigger_window is not None or recovery):
            raise serializers.ValidationError({"metric_type": serializer_text(self, "error.no_traffic_plain")})
        if trigger_window is not None and (trigger_window < trigger_after or trigger_window > 20):
            raise serializers.ValidationError({"trigger_window": serializer_text(self, "error.trigger_window_order")})
        attrs["trigger_window"] = trigger_window
        attrs["recovery_threshold"] = self._validate_recovery(recovery, thresholds, metric_type, compare_mode, compare_value_kind)

    def _validate_recovery(self, recovery, thresholds, metric_type, compare_mode, compare_value_kind):
        if recovery in (None, {}, ""):
            return {}
        if not isinstance(recovery, dict) or set(recovery) - {"comparator", "value"}:
            raise serializers.ValidationError({"recovery_threshold": serializer_text(self, "error.recovery_shape")})
        comparator = str(recovery.get("comparator") or "")
        allowed = {choice for choice, _label in ApmPolicy.Comparator.choices}
        if comparator not in allowed:
            raise serializers.ValidationError({"recovery_threshold": serializer_text(self, "error.recovery_shape")})
        ladder = str(thresholds[0]["comparator"])
        higher = {ApmPolicy.Comparator.GREATER_THAN, ApmPolicy.Comparator.GREATER_THAN_OR_EQUAL}
        lower = {ApmPolicy.Comparator.LESS_THAN, ApmPolicy.Comparator.LESS_THAN_OR_EQUAL}
        opposite = (ladder in higher and comparator in lower) or (ladder in lower and comparator in higher)
        if not opposite:
            raise serializers.ValidationError({"recovery_threshold": serializer_text(self, "error.recovery_direction")})
        value = self._finite_decimal(recovery.get("value"), "recovery_threshold", "error.recovery_value")
        kind = compare_value_kind or ""
        if metric_type in ApmPolicy.RATIO_METRIC_TYPES and (compare_mode == ApmPolicy.CompareMode.ABSOLUTE or kind == ""):
            if not 0 <= value <= 1:
                raise serializers.ValidationError({"recovery_threshold": serializer_text(self, "error.error_rate_range")})
        elif metric_type in ApmPolicy.RATIO_METRIC_TYPES and kind == ApmPolicy.CompareValueKind.DELTA and not -1 <= value <= 1:
            raise serializers.ValidationError({"recovery_threshold": serializer_text(self, "error.error_rate_delta_range")})
        return {"comparator": comparator, "value": self._decimal_payload(value)}

    def _finite_decimal(self, raw, field, error_key):
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            raise serializers.ValidationError({field: serializer_text(self, error_key)}) from None
        if not value.is_finite():
            raise serializers.ValidationError({field: serializer_text(self, error_key)})
        return value

    @staticmethod
    def _decimal_payload(value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    def _stored_or_incoming(self, attrs, field, default):
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field)
        return default

    def _validate_compare(
        self,
        metric_type,
        compare_mode,
        compare_value_kind,
        min_request_count,
        metric_window,
        compare_offset_amount,
    ):
        kind = compare_value_kind or ""
        offset_modes = {
            ApmPolicy.CompareMode.OFFSET_1H,
            ApmPolicy.CompareMode.OFFSET_24H,
            ApmPolicy.CompareMode.OFFSET_HOURS,
            ApmPolicy.CompareMode.OFFSET_DAYS,
        }
        if compare_mode == ApmPolicy.CompareMode.ABSOLUTE and kind != "":
            raise serializers.ValidationError({"compare_value_kind": serializer_text(self, "error.compare_absolute_kind")})
        if compare_mode == ApmPolicy.CompareMode.PREVIOUS_WINDOW and kind not in {"delta", "percent"}:
            raise serializers.ValidationError({"compare_value_kind": serializer_text(self, "error.compare_previous_kind")})
        if compare_mode == ApmPolicy.CompareMode.BASELINE_DAYS and kind not in {"delta", "percent"}:
            raise serializers.ValidationError({"compare_value_kind": serializer_text(self, "error.compare_baseline_days_kind")})
        if compare_mode in offset_modes and kind != "percent":
            raise serializers.ValidationError({"compare_value_kind": serializer_text(self, "error.compare_offset_percent_only")})
        self._validate_offset_amount(compare_mode, metric_window, compare_offset_amount)
        if metric_type == ApmPolicy.MetricType.NO_TRAFFIC and compare_mode != ApmPolicy.CompareMode.ABSOLUTE:
            raise serializers.ValidationError({"compare_mode": serializer_text(self, "error.compare_no_traffic_absolute")})
        if min_request_count is not None and metric_type not in ApmPolicy.MIN_REQUEST_METRIC_TYPES:
            raise serializers.ValidationError({"min_request_count": serializer_text(self, "error.compare_min_request_metric")})

    def _validate_metric_params(self, metric_type, slow_threshold_ms, apdex_threshold_ms):
        errors = {}
        if metric_type in ApmPolicy.SLOW_METRIC_TYPES:
            slow_threshold_ms = self._bounded_ms(
                slow_threshold_ms, "slow_threshold_ms", "error.slow_threshold_required", "error.slow_threshold_range", errors
            )
        elif slow_threshold_ms is not None:
            errors["slow_threshold_ms"] = serializer_text(self, "error.slow_threshold_unused")
            slow_threshold_ms = None
        else:
            slow_threshold_ms = None
        if metric_type == ApmPolicy.MetricType.APDEX:
            apdex_threshold_ms = self._bounded_ms(
                apdex_threshold_ms,
                "apdex_threshold_ms",
                "error.apdex_threshold_required",
                "error.apdex_threshold_range",
                errors,
            )
        elif apdex_threshold_ms is not None:
            errors["apdex_threshold_ms"] = serializer_text(self, "error.apdex_threshold_unused")
            apdex_threshold_ms = None
        else:
            apdex_threshold_ms = None
        if errors:
            raise serializers.ValidationError(errors)
        return slow_threshold_ms, apdex_threshold_ms

    def _bounded_ms(self, value, field, required_key, range_key, errors):
        if value is None:
            errors[field] = serializer_text(self, required_key)
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            errors[field] = serializer_text(self, range_key)
            return None
        if number != value or not 1 <= number <= 600_000:
            errors[field] = serializer_text(self, range_key)
            return None
        return number

    def _validate_offset_amount(self, compare_mode, metric_window, amount):
        if compare_mode == ApmPolicy.CompareMode.BASELINE_DAYS:
            if isinstance(amount, bool) or not isinstance(amount, int) or not 2 <= amount <= 7:
                raise serializers.ValidationError({"compare_offset_amount": serializer_text(self, "error.compare_baseline_days_range")})
            return
        if compare_mode == ApmPolicy.CompareMode.OFFSET_HOURS:
            limit = ApmPolicy.MAX_COMPARE_OFFSET_HOURS
            minutes = (amount or 0) * 60
        elif compare_mode == ApmPolicy.CompareMode.OFFSET_DAYS:
            limit = ApmPolicy.MAX_COMPARE_OFFSET_DAYS
            minutes = (amount or 0) * 24 * 60
        elif amount is not None:
            raise serializers.ValidationError({"compare_offset_amount": serializer_text(self, "error.compare_offset_amount_unused")})
        else:
            return
        if amount is None:
            raise serializers.ValidationError({"compare_offset_amount": serializer_text(self, "error.compare_offset_amount_required")})
        if amount > limit:
            raise serializers.ValidationError({"compare_offset_amount": serializer_text(self, "error.compare_offset_amount_range")})
        if minutes < max(metric_window or 1, 1):
            raise serializers.ValidationError({"compare_offset_amount": serializer_text(self, "error.compare_offset_shorter_than_window")})

    def _validate_thresholds(self, thresholds, metric_type, compare_mode, compare_value_kind):
        severity_rank = {"critical": 0, "error": 1, "warning": 2}
        normalized = []
        seen = set()
        comparators = set()
        for threshold in thresholds:
            severity = str(threshold["severity"])
            if severity in seen:
                raise serializers.ValidationError({"thresholds": serializer_text(self, "error.level_duplicate")})
            seen.add(severity)
            comparator = str(threshold["comparator"])
            comparators.add(comparator)
            try:
                value = Decimal(str(threshold["value"]))
            except (InvalidOperation, TypeError, ValueError):
                raise serializers.ValidationError({"thresholds": serializer_text(self, "error.threshold_finite")}) from None
            if not value.is_finite():
                raise serializers.ValidationError({"thresholds": serializer_text(self, "error.threshold_finite")})
            if metric_type in ApmPolicy.RATIO_METRIC_TYPES:
                kind = compare_value_kind or ""
                if compare_mode == ApmPolicy.CompareMode.ABSOLUTE or kind == "":
                    if not 0 <= value <= 1:
                        raise serializers.ValidationError({"thresholds": serializer_text(self, "error.error_rate_range")})
                elif kind == ApmPolicy.CompareValueKind.DELTA and not -1 <= value <= 1:
                    raise serializers.ValidationError({"thresholds": serializer_text(self, "error.error_rate_delta_range")})
            if (
                metric_type == ApmPolicy.MetricType.APDEX
                and compare_mode == ApmPolicy.CompareMode.ABSOLUTE
                and comparator in {ApmPolicy.Comparator.GREATER_THAN, ApmPolicy.Comparator.GREATER_THAN_OR_EQUAL}
            ):
                raise serializers.ValidationError({"thresholds": serializer_text(self, "error.apdex_comparator")})
            normalized.append({"severity": severity, "comparator": comparator, "value": str(value)})
        if len(comparators) != 1:
            raise serializers.ValidationError({"thresholds": serializer_text(self, "error.threshold_comparator")})
        normalized.sort(key=lambda item: severity_rank[item["severity"]])
        values = [Decimal(item["value"]) for item in normalized]
        comparator = next(iter(comparators))
        valid = values == sorted(values, reverse=comparator in {"gt", "gte"})
        if not valid:
            raise serializers.ValidationError({"thresholds": serializer_text(self, "error.threshold_monotonic")})
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
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > timedelta(days=90):
            raise serializers.ValidationError(serializer_text(self, "error.deployment_window_limit"))
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
    action = serializers.ChoiceField(
        choices=("triggered", "escalated", "claimed", "assigned", "reassigned", "recovered", "closed"),
        required=False,
    )
    severity = serializers.ChoiceField(choices=("critical", "error", "warning"), required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)

    def validate(self, attrs):
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(days=7)
        if ended_at <= started_at:
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > timedelta(days=90):
            raise serializers.ValidationError(serializer_text(self, "error.event_window_limit"))
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
    my_alert = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(days=7)
        if ended_at <= started_at:
            raise serializers.ValidationError(serializer_text(self, "error.ended_after_started"))
        if ended_at - started_at > timedelta(days=90):
            raise serializers.ValidationError(serializer_text(self, "error.alert_window_limit"))
        attrs["started_at"] = started_at
        attrs["ended_at"] = ended_at
        attrs["my_alert"] = str(attrs.get("my_alert") or "").strip().lower() in {"1", "true", "yes"}
        return attrs


class ApmAlertAssignSerializer(serializers.Serializer):
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


class NotificationDeliveryQuerySerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=320, required=False)
    status = serializers.ChoiceField(choices=("pending", "delivered", "failed"), required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)


class NotificationRecipientQuerySerializer(serializers.Serializer):
    search = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(min_value=1, max_value=100, default=100)
    organization_ids = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_organization_ids(self, value):
        if not value:
            return []
        parts = [part.strip() for part in str(value).split(",") if part.strip()]
        try:
            return sorted({int(part) for part in parts})
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError(serializer_text(self, "error.organization_ids_format")) from exc


class NotificationDeliveryRetrySerializer(serializers.Serializer):
    recipients = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
        allow_empty=True,
        max_length=100,
    )

    def validate_recipients(self, value):
        return list(dict.fromkeys(item.strip() for item in value))
