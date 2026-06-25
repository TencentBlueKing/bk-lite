from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IMNotificationUserMapping, IntegrationInstanceStatusChoices
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.services import im_notification_service


class IMNotificationSyncRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMNotificationSyncRun
        fields = "__all__"


class IMNotificationUserMappingSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()

    class Meta:
        model = IMNotificationUserMapping
        fields = "__all__"

    def get_username(self, obj):
        return obj.user.username if obj.user_id else ""


class IMNotificationChannelSerializer(UsernameSerializer):
    integration_instance_name = serializers.SerializerMethodField()
    provider_key = serializers.SerializerMethodField()
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
        fields = "__all__"

    def get_integration_instance_name(self, obj):
        return obj.integration_instance.name if obj.integration_instance_id else ""
    
    def get_provider_key(self, obj):
        return obj.integration_instance.provider_key if obj.integration_instance_id else ""

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
        if (
            not integration_instance.enabled
            or integration_instance.status != IntegrationInstanceStatusChoices.READY
            or integration_instance.capability_status.get("im_notification") != IntegrationInstanceStatusChoices.READY
        ):
            raise serializers.ValidationError({"integration_instance": "Integration instance im_notification capability is not ready"})

        runtime_service = RuntimeApplicationService()
        manifest = runtime_service.get_provider_manifest(integration_instance.provider_key)
        template = manifest.business_templates.get("im_notification_form")
        if template is None:
            raise serializers.ValidationError({"integration_instance": "Integration instance im_notification template is missing"})

        external_match_field = attrs.get("external_match_field") or getattr(self.instance, "external_match_field", "")
        external_receive_field = attrs.get("external_receive_field") or getattr(self.instance, "external_receive_field", "")
        if external_match_field not in template.matchable_fields:
            raise serializers.ValidationError({"external_match_field": "External match field is not supported by the provider manifest"})
        if external_receive_field not in template.receivable_fields:
            raise serializers.ValidationError({"external_receive_field": "External receive field is not supported by the provider manifest"})
        schedule_config = attrs.get("schedule_config")
        if schedule_config is not None and not isinstance(schedule_config, dict):
            raise serializers.ValidationError({"schedule_config": "Schedule config must be an object"})

        if self.instance and im_notification_service.critical_config_changed(self.instance, attrs):
            attrs["status"] = im_notification_service.CHANNEL_STATUS_NEEDS_RESYNC
        elif self.instance is None and "status" not in attrs:
            attrs["status"] = im_notification_service.CHANNEL_STATUS_PENDING_SYNC

        return attrs

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._sync_periodic_task(instance)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._sync_periodic_task(instance)
        return instance

    def _get_latest_run(self, obj):
        latest_run = getattr(obj, "_prefetched_latest_run", None)
        if latest_run is None:
            latest_run = obj.sync_runs.order_by("-started_at", "-id").first()
        return latest_run

    def _sync_periodic_task(self, instance: IMNotificationChannel):
        schedule_config = instance.schedule_config or {}
        if instance.enabled and schedule_config.get("enabled") and schedule_config.get("sync_time"):
            instance.create_sync_periodic_task()
        else:
            instance.delete_sync_periodic_task()
