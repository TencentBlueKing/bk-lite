from django.db import transaction
from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IMNotificationUserMapping
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.providers.pack_i18n import resolve_bound_instance_provider_name
from apps.system_mgmt.services import im_notification_service
from apps.system_mgmt.services.capability_contract_service import (
    CapabilityContractError,
    get_integration_capability_availability,
    validate_im_notification_contract,
)
from apps.system_mgmt.services.notification_tag import assign_channel_tags, channel_tag_tokens, parse_tag_tokens


class IMNotificationSyncRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMNotificationSyncRun
        fields = "__all__"


class IMNotificationUserMappingSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = IMNotificationUserMapping
        fields = "__all__"

    def get_username(self, obj):
        return obj.user.username if obj.user_id else ""

    def get_display_name(self, obj):
        return obj.user.display_name if obj.user_id else ""


class IMNotificationChannelSerializer(UsernameSerializer):
    tag = serializers.ListField(child=serializers.CharField(), required=False, write_only=True)
    integration_instance_name = serializers.SerializerMethodField()
    provider_key = serializers.SerializerMethodField()
    provider_name = serializers.SerializerMethodField()
    dependency_status = serializers.SerializerMethodField()
    display_status = serializers.SerializerMethodField()
    display_sync_status = serializers.SerializerMethodField()
    display_sync_summary = serializers.SerializerMethodField()
    latest_sync_status = serializers.SerializerMethodField()
    latest_sync_started_at = serializers.SerializerMethodField()
    latest_sync_finished_at = serializers.SerializerMethodField()
    latest_sync_summary = serializers.SerializerMethodField()
    latest_sync_total_external_user_count = serializers.SerializerMethodField()
    latest_sync_matched_count = serializers.SerializerMethodField()
    latest_sync_unmatched_count = serializers.SerializerMethodField()
    latest_sync_conflict_count = serializers.SerializerMethodField()

    class Meta:
        model = IMNotificationChannel
        fields = (
            "id",
            "name",
            "integration_instance",
            "integration_instance_name",
            "provider_key",
            "provider_name",
            "dependency_status",
            "enabled",
            "description",
            "status",
            "display_status",
            "platform_match_field",
            "external_match_field",
            "external_receive_field",
            "schedule_config",
            "team",
            "display_sync_status",
            "display_sync_summary",
            "latest_sync_status",
            "latest_sync_started_at",
            "latest_sync_finished_at",
            "latest_sync_summary",
            "latest_sync_total_external_user_count",
            "latest_sync_matched_count",
            "latest_sync_unmatched_count",
            "latest_sync_conflict_count",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "created_at",
            "updated_at",
            "tag",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["tag"] = channel_tag_tokens(instance)
        return data

    def validate_tag(self, value):
        return parse_tag_tokens(value)

    def validate_team(self, value):
        if isinstance(value, (int, str)):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            raise serializers.ValidationError(self._team_required_message())

        team_ids = []
        for team_id in value:
            try:
                parsed = int(team_id)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(self._team_required_message()) from exc
            if parsed <= 0:
                raise serializers.ValidationError(self._team_required_message())
            team_ids.append(parsed)
        if not team_ids:
            raise serializers.ValidationError(self._team_required_message())
        return team_ids

    def get_integration_instance_name(self, obj):
        return obj.integration_instance.name if obj.integration_instance_id else ""

    def get_provider_key(self, obj):
        return obj.integration_instance.provider_key if obj.integration_instance_id else ""

    def get_provider_name(self, obj):
        return resolve_bound_instance_provider_name(obj, self.context.get("request"))

    def get_dependency_status(self, obj):
        if not obj.integration_instance_id:
            return {"available": False, "reason": "instance_not_ready"}
        return get_integration_capability_availability(obj.integration_instance, "im_notification")

    def get_display_status(self, obj):
        latest_run = self._get_latest_run(obj)
        if latest_run and latest_run.status == im_notification_service.SYNC_RUN_STATUS_RUNNING:
            return "syncing"
        return obj.status

    def get_display_sync_status(self, obj):
        latest_run = self._get_latest_run(obj)
        if latest_run and latest_run.status == im_notification_service.SYNC_RUN_STATUS_RUNNING:
            return "running"
        if latest_run:
            return latest_run.status
        return "never_synced"

    def get_display_sync_summary(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.summary if latest_run else ""

    def get_latest_sync_status(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.status if latest_run else ""

    def get_latest_sync_started_at(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.started_at if latest_run else None

    def get_latest_sync_finished_at(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.finished_at if latest_run else None

    def get_latest_sync_summary(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.summary if latest_run else ""

    def get_latest_sync_total_external_user_count(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.total_external_user_count if latest_run else None

    def get_latest_sync_matched_count(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.matched_count if latest_run else None

    def get_latest_sync_unmatched_count(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.unmatched_count if latest_run else None

    def get_latest_sync_conflict_count(self, obj):
        latest_run = self._get_latest_run(obj)
        return latest_run.conflict_count if latest_run else None

    def validate(self, attrs):
        integration_instance = attrs.get("integration_instance") or getattr(self.instance, "integration_instance", None)
        if integration_instance is None:
            raise serializers.ValidationError({"integration_instance": "Integration instance is required"})
        changes_instance = bool(
            self.instance and "integration_instance" in attrs and integration_instance.id != self.instance.integration_instance_id
        )
        if (self.instance is None or changes_instance) and not get_integration_capability_availability(integration_instance, "im_notification")[
            "available"
        ]:
            raise serializers.ValidationError({"integration_instance": "Integration instance im_notification capability is not ready"})

        runtime_service = RuntimeApplicationService()
        manifest = runtime_service.get_provider_manifest(integration_instance.provider_key)
        external_match_field = attrs.get("external_match_field") or getattr(self.instance, "external_match_field", "")
        external_receive_field = attrs.get("external_receive_field") or getattr(self.instance, "external_receive_field", "")
        schedule_config = attrs.get("schedule_config")
        try:
            validate_im_notification_contract(
                manifest,
                external_match_field=external_match_field,
                external_receive_field=external_receive_field,
                schedule_config=schedule_config,
            )
        except CapabilityContractError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc

        if self.instance and im_notification_service.critical_config_changed(self.instance, attrs):
            attrs["status"] = im_notification_service.CHANNEL_STATUS_NEEDS_RESYNC
        elif self.instance is None and "status" not in attrs:
            attrs["status"] = im_notification_service.CHANNEL_STATUS_PENDING_SYNC

        return attrs

    def create(self, validated_data):
        pairs = validated_data.pop("tag", [])
        with transaction.atomic():
            instance = super().create(validated_data)
            assign_channel_tags(instance, pairs, actor=self._actor())
        self._sync_periodic_task(instance)
        return instance

    def update(self, instance, validated_data):
        tag_provided = "tag" in self.initial_data
        pairs = validated_data.pop("tag", [])
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if tag_provided:
                assign_channel_tags(instance, pairs, actor=self._actor())
        self._sync_periodic_task(instance)
        return instance

    def _actor(self):
        return getattr(self.context.get("request"), "user", None)

    def _get_latest_run(self, obj):
        latest_run = getattr(obj, "_prefetched_latest_run", None)
        if isinstance(latest_run, list):
            latest_run = latest_run[0] if latest_run else None
        if latest_run is None:
            latest_run = obj.sync_runs.order_by("-started_at", "-id").first()
        return latest_run

    def _sync_periodic_task(self, instance: IMNotificationChannel):
        schedule_config = instance.schedule_config or {}
        if instance.enabled and schedule_config.get("enabled") and schedule_config.get("sync_time"):
            instance.create_sync_periodic_task()
        else:
            instance.delete_sync_periodic_task()

    def _team_required_message(self):
        return self._loader().get("error.channel_team_required", "请选择渠道所属组织")

    def _loader(self):
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", "en") or "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)
