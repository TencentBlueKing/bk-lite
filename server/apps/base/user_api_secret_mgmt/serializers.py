from rest_framework import serializers
from rest_framework.fields import empty

from apps.base.models.user import UserAPISecret
from apps.core.openapi.token_scope import normalize_scope


class BaseUserAPISecretSerializer(serializers.ModelSerializer):
    team_name = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context["request"]
        groups = request.user.group_list
        self.group_map = {i["id"]: i["name"] for i in groups if isinstance(i, dict) and "id" in i and "name" in i}

    def get_team_name(self, instance):
        return self.group_map.get(instance.team, instance.team) if instance.team else ""

    def get_unique_together_validators(self):
        return []

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
        username = attrs.get("username", getattr(self.instance, "username", None))
        domain = attrs.get("domain", getattr(self.instance, "domain", None))
        team = attrs.get("team", getattr(self.instance, "team", None))
        queryset = UserAPISecret.objects.filter(username=username, domain=domain, team=team, name=name)
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


class UserAPISecretSerializer(BaseUserAPISecretSerializer):
    api_secret_preview = serializers.SerializerMethodField()

    class Meta:
        model = UserAPISecret
        fields = (
            "id",
            "username",
            "domain",
            "team",
            "team_name",
            "name",
            "expires_at",
            "scope",
            "created_at",
            "updated_at",
            "api_secret_preview",
        )
        read_only_fields = (
            "id",
            "username",
            "domain",
            "team",
            "team_name",
            "created_at",
            "updated_at",
            "api_secret_preview",
        )

    def get_api_secret_preview(self, instance):
        return instance.get_api_secret_preview()


class UserAPISecretCreateSerializer(BaseUserAPISecretSerializer):
    api_secret = serializers.CharField(write_only=True)

    class Meta:
        model = UserAPISecret
        fields = (
            "id",
            "username",
            "domain",
            "team",
            "team_name",
            "name",
            "expires_at",
            "scope",
            "created_at",
            "updated_at",
            "api_secret",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        api_secret = getattr(instance, "_plain_api_secret", None)
        if api_secret:
            data["api_secret"] = api_secret
        return data
