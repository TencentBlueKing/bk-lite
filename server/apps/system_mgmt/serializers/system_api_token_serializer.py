from rest_framework import serializers

from apps.core.openapi.registry import SERVICE_NAME_RE
from apps.core.openapi.token_scope import normalize_scope
from apps.system_mgmt.models import SystemAPIToken


class SystemAPITokenSerializer(serializers.ModelSerializer):
    api_secret_preview = serializers.SerializerMethodField()

    class Meta:
        model = SystemAPIToken
        fields = (
            "id",
            "system_id",
            "name",
            "scope",
            "enabled",
            "expires_at",
            "created_at",
            "updated_at",
            "created_by",
            "api_secret_preview",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "api_secret_preview",
        )

    def __init__(self, instance=None, data=serializers.empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        if instance is not None:
            self.fields["system_id"].read_only = True

    def get_api_secret_preview(self, instance):
        return instance.get_secret_preview()

    def get_unique_together_validators(self):
        return []

    def validate_system_id(self, value):
        raw = (value or "").strip()
        if not SERVICE_NAME_RE.match(raw):
            raise serializers.ValidationError("invalid system_id")
        return raw

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("name is required")
        return name

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and "scope" not in attrs:
            raise serializers.ValidationError({"scope": "scope is required"})
        name = attrs.get("name")
        if name is None:
            if self.instance is None:
                raise serializers.ValidationError({"name": "name is required"})
            name = self.instance.name
        system_id = attrs.get("system_id", getattr(self.instance, "system_id", None))
        queryset = SystemAPIToken.objects.filter(system_id=system_id, name=name)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError({"name": "name already exists"})
        return attrs

    def validate_scope(self, value):
        try:
            return normalize_scope(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def to_representation(self, instance):
        data = super().to_representation(instance)
        plain = getattr(instance, "_plain_api_secret", None)
        if plain:
            data["api_secret"] = plain
        return data
