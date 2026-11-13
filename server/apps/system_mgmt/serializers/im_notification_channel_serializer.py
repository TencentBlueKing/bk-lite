from django.db import transaction
from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IMNotificationUserMapping
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.providers.pack_i18n import resolve_bound_instance_provider_name
from apps.system_mgmt.services import im_notification_service
from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability
from apps.system_mgmt.services.notification_tag import assign_channel_tags, channel_tag_tokens, parse_tag_tokens


class IMNotificationSyncRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = IMNotificationSyncRun
        fields = "__all__"


class AccountAssociationSyncRunListSerializer(serializers.ModelSerializer):
    account_association_name = serializers.SerializerMethodField()

    class Meta:
        model = IMNotificationSyncRun
        fields = (
            "id",
            "account_association",
            "account_association_name",
            "trigger_mode",
            "status",
            "matched_count",
            "unmatched_count",
            "conflict_count",
            "started_at",
            "summary",
        )

    def get_account_association_name(self, obj):
        association = getattr(obj, "account_association", None)
        return association.name if association is not None else ""


class AccountAssociationUserMappingSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = IMNotificationUserMapping
        fields = (
            "id",
            "account_association",
            "user",
            "username",
            "display_name",
            "external_identity_key",
            "external_identity_value",
            "external_receive_key",
            "external_display_name",
            "synced_at",
        )

    def get_username(self, obj):
        return obj.user.username if obj.user_id else ""

    def get_display_name(self, obj):
        return obj.user.display_name if obj.user_id else ""


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
    account_association_name = serializers.SerializerMethodField()

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
            "account_association",
            "account_association_name",
            "team",
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
        return obj.status

    def get_account_association_name(self, obj):
        return obj.account_association.name if obj.account_association_id else ""

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
        if manifest is None:
            raise serializers.ValidationError({"integration_instance": "Integration provider is not available"})

        association = attrs.get("account_association", getattr(self.instance, "account_association", None))
        if association is not None and association.integration_instance_id != integration_instance.id:
            if self.instance and "integration_instance" in attrs and "account_association" not in attrs:
                attrs["account_association"] = None
                association = None
            else:
                raise serializers.ValidationError({"account_association": "Account association does not belong to the integration instance"})

        enabled = attrs.get("enabled", getattr(self.instance, "enabled", True))
        if not enabled:
            attrs["status"] = im_notification_service.CHANNEL_STATUS_DISABLED
        elif association is None or association.status != im_notification_service.ASSOCIATION_STATUS_READY:
            attrs["status"] = im_notification_service.CHANNEL_STATUS_NEEDS_RESYNC
        else:
            attrs["status"] = im_notification_service.CHANNEL_STATUS_READY

        return attrs

    def create(self, validated_data):
        pairs = validated_data.pop("tag", [])
        with transaction.atomic():
            instance = super().create(validated_data)
            assign_channel_tags(instance, pairs, actor=self._actor())
        return instance

    def update(self, instance, validated_data):
        tag_provided = "tag" in self.initial_data
        pairs = validated_data.pop("tag", [])
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if tag_provided:
                assign_channel_tags(instance, pairs, actor=self._actor())
        return instance

    def _actor(self):
        return getattr(self.context.get("request"), "user", None)

    def _team_required_message(self):
        return self._loader().get("error.channel_team_required", "请选择渠道所属组织")

    def _loader(self):
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", "en") or "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)
