from django.db import transaction
from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import IMAccountAssociation
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.services import im_notification_service
from apps.system_mgmt.services.capability_contract_service import CapabilityContractError, validate_im_notification_contract


class IMAccountAssociationSerializer(UsernameSerializer):
    integration_instance_name = serializers.SerializerMethodField()
    provider_key = serializers.SerializerMethodField()

    class Meta:
        model = IMAccountAssociation
        fields = (
            "id",
            "name",
            "integration_instance",
            "integration_instance_name",
            "provider_key",
            "platform_match_field",
            "external_match_field",
            "external_receive_field",
            "schedule_config",
            "status",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("status",)

    def get_integration_instance_name(self, obj):
        return obj.integration_instance.name if obj.integration_instance_id else ""

    def get_provider_key(self, obj):
        return obj.integration_instance.provider_key if obj.integration_instance_id else ""

    def validate(self, attrs):
        if self.instance and "integration_instance" in attrs and attrs["integration_instance"].id != self.instance.integration_instance_id:
            raise serializers.ValidationError({"integration_instance": "Integration instance cannot be changed"})
        integration_instance = attrs.get("integration_instance") or getattr(self.instance, "integration_instance", None)
        if integration_instance is None:
            raise serializers.ValidationError({"integration_instance": "Integration instance is required"})
        if "im_notification" not in (integration_instance.capability_status or {}):
            raise serializers.ValidationError({"integration_instance": "Integration instance does not provide IM notification"})

        manifest = RuntimeApplicationService().get_provider_manifest(integration_instance.provider_key)
        try:
            validate_im_notification_contract(
                manifest,
                external_match_field=attrs.get("external_match_field") or getattr(self.instance, "external_match_field", ""),
                external_receive_field=attrs.get("external_receive_field") or getattr(self.instance, "external_receive_field", ""),
                schedule_config=attrs.get("schedule_config", getattr(self.instance, "schedule_config", None)),
            )
        except CapabilityContractError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc

        if im_notification_service.association_config_changed(self.instance, attrs):
            attrs["status"] = im_notification_service.ASSOCIATION_STATUS_NEEDS_RESYNC
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            updated = super().update(instance, validated_data)
        self._sync_periodic_task(updated)
        if updated.status == im_notification_service.ASSOCIATION_STATUS_NEEDS_RESYNC:
            im_notification_service.refresh_notification_channel_status(updated)
        return updated

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._sync_periodic_task(instance)
        return instance

    def _sync_periodic_task(self, instance: IMAccountAssociation):
        schedule_config = instance.schedule_config or {}
        if schedule_config.get("enabled") and schedule_config.get("sync_time"):
            instance.create_sync_periodic_task()
        else:
            instance.delete_sync_periodic_task()
