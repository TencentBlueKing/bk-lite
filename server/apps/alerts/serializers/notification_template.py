from django.db import transaction
from rest_framework import serializers

from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent
from apps.alerts.notification_templates.operation import is_supported_operation_channel
from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source
from apps.alerts.utils.i18n import serializer_message
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.system_mgmt.models.channel import Channel

SUPPORTED_CHANNEL_TYPES = {
    "email",
    "enterprise_wechat",
    "enterprise_wechat_bot",
    "dingtalk_bot",
    "feishu_bot",
    "custom_webhook",
    "nats",
    "im_notification",
}
SUBJECT_CHANNEL_TYPES = {"email", "dingtalk_bot", "feishu_bot", "im_notification"}


class NotificationTemplateContentSerializer(serializers.ModelSerializer):
    def validate_channel_type(self, value):
        if value not in SUPPORTED_CHANNEL_TYPES:
            raise serializers.ValidationError(serializer_message(self, "error.channel_template_unsupported"))
        return value

    class Meta:
        model = NotificationTemplateContent
        fields = ["id", "channel_type", "subject_template", "body_template"]
        read_only_fields = ["id"]


class NotificationTemplateSerializer(serializers.ModelSerializer):
    contents = NotificationTemplateContentSerializer(many=True)
    is_builtin = serializers.BooleanField(read_only=True)
    assignment_count = serializers.SerializerMethodField()
    revision = serializers.IntegerField(required=False, min_value=1)
    channel_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def get_assignment_count(self, instance):
        return len(
            {reference.source_id for reference in instance.references.all() if reference.source_type == "assignment" and not reference.is_snapshot}
        )

    def validate_team(self, value):
        try:
            normalized = normalize_team_ids(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if len(normalized) > 100:
            raise serializers.ValidationError(serializer_message(self, "error.template_team_limit"))
        request = self.context.get("request")
        if request and not getattr(request.user, "is_superuser", False):
            authorized = set(get_authorized_group_ids(request))
            if not normalized or not set(normalized).issubset(authorized):
                raise serializers.ValidationError(serializer_message(self, "error.team_outside_authorized_scope"))
        elif not normalized:
            raise serializers.ValidationError(serializer_message(self, "error.template_team_required"))
        return sorted(set(normalized))

    def validate_contents(self, value):
        if not value:
            raise serializers.ValidationError(serializer_message(self, "error.template_channel_required"))
        channel_types = [item["channel_type"] for item in value]
        if len(channel_types) != len(set(channel_types)):
            raise serializers.ValidationError(serializer_message(self, "error.template_channel_unique"))
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        scope = attrs.get("scope", getattr(self.instance, "scope", NotificationTemplate.SCOPE_SINGLE_ALERT))
        contents = attrs.get("contents")
        if contents is None and self.instance:
            contents = list(self.instance.contents.values("channel_type", "subject_template", "body_template"))
        errors = []
        for item in contents or []:
            channel_type = item["channel_type"]
            subject = item.get("subject_template", "")
            body = item.get("body_template", "")
            if channel_type in SUBJECT_CHANNEL_TYPES and not subject.strip():
                errors.append({"channel_type": channel_type, "subject_template": serializer_message(self, "error.channel_subject_required")})
            if not body.strip():
                errors.append({"channel_type": channel_type, "body_template": serializer_message(self, "error.body_required")})
                continue
            try:
                if subject:
                    validate_source(subject, channel_type=channel_type, is_subject=True, scope=scope)
                validate_source(body, channel_type=channel_type, scope=scope)
            except TemplateValidationError as exc:
                errors.append({"channel_type": channel_type, "detail": str(exc)})
        if errors:
            raise serializers.ValidationError({"contents": errors})

        channel_id = attrs.get("channel_id", getattr(self.instance, "channel_id", None))
        if scope == NotificationTemplate.SCOPE_ALERT_OPERATION:
            if not self.instance or not self.instance.is_alert_operation:
                raise serializers.ValidationError({"scope": serializer_message(self, "error.operation_template_builtin_only")})
            if len(contents or []) != 1:
                raise serializers.ValidationError({"contents": serializer_message(self, "error.operation_template_single_channel")})
            if not channel_id:
                raise serializers.ValidationError({"channel_id": serializer_message(self, "error.channel_required")})
            channel = Channel.objects.filter(pk=channel_id).first()
            if not channel or not is_supported_operation_channel(channel):
                raise serializers.ValidationError({"channel_id": serializer_message(self, "error.channel_missing_or_unsupported")})
            next_team = attrs.get("team", self.instance.team)
            channel_teams = {str(item) for item in (channel.team or [])}
            if not channel_teams.intersection(str(item) for item in next_team or []):
                raise serializers.ValidationError({"channel_id": serializer_message(self, "error.channel_wrong_team")})
            if contents[0]["channel_type"] != channel.channel_type:
                raise serializers.ValidationError({"contents": serializer_message(self, "error.template_channel_mismatch")})
            immutable_fields = {
                "name": self.instance.name,
                "description": self.instance.description,
                "team": self.instance.team,
                "scope": self.instance.scope,
            }
            for field, current_value in immutable_fields.items():
                if field in attrs and attrs[field] != current_value:
                    raise serializers.ValidationError({field: serializer_message(self, "error.builtin_operation_template_limited")})
        elif channel_id is not None:
            raise serializers.ValidationError({"channel_id": serializer_message(self, "error.plain_template_no_channel")})

        if self.instance and self.instance.references.exists():
            if scope != self.instance.scope:
                raise serializers.ValidationError({"scope": serializer_message(self, "error.template_scope_locked")})
            next_team = attrs.get("team", self.instance.team)
            if next_team != self.instance.team:
                raise serializers.ValidationError({"team": serializer_message(self, "error.template_team_locked")})
            next_types = {item["channel_type"] for item in contents or []}
            current_types = set(self.instance.contents.values_list("channel_type", flat=True))
            removed_types = sorted(current_types - next_types)
            if removed_types:
                raise serializers.ValidationError(
                    {"contents": serializer_message(self, "error.template_channel_removal_locked", types=", ".join(removed_types))}
                )

        name = attrs.get("name", getattr(self.instance, "name", ""))
        team = attrs.get("team", getattr(self.instance, "team", []))
        duplicate = NotificationTemplate.objects.filter(name=name, team=team, scope=scope, is_global=False)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({"name": serializer_message(self, "error.template_name_exists")})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        contents = validated_data.pop("contents")
        validated_data.pop("revision", None)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        actor_context = {"username": getattr(actor, "username", ""), "domain": getattr(actor, "domain", "")}
        instance = NotificationTemplate.objects.create(**validated_data, **maintainer_kwargs(actor_context))
        NotificationTemplateContent.objects.bulk_create([NotificationTemplateContent(template=instance, **item) for item in contents])
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        contents = validated_data.pop("contents", None)
        validated_data.pop("revision", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        instance.updated_by = getattr(actor, "username", "")
        instance.updated_by_domain = getattr(actor, "domain", "") or "domain.com"
        instance.revision += 1
        instance.save()
        if contents is not None:
            instance.contents.all().delete()
            NotificationTemplateContent.objects.bulk_create([NotificationTemplateContent(template=instance, **item) for item in contents])
        return instance

    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "name",
            "description",
            "team",
            "scope",
            "is_global",
            "builtin_key",
            "is_builtin",
            "channel_id",
            "assignment_count",
            "revision",
            "contents",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = [
            "id",
            "is_global",
            "builtin_key",
            "is_builtin",
            "assignment_count",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
