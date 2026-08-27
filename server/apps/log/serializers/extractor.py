from rest_framework import serializers

from apps.log.models import LogExtractor
from apps.log.services.log_extractor.semantics import RuleValidationError, format_path, normalize_rule


class LogExtractorSerializer(serializers.ModelSerializer):
    collect_type = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = LogExtractor
        fields = (
            "id",
            "name",
            "collect_instance",
            "collect_type",
            "condition",
            "extractor_type",
            "source_field",
            "target_field",
            "delete_source",
            "config",
            "sort_order",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"collect_instance": {"required": False, "allow_null": True}}
        validators = []
        read_only_fields = (
            "id",
            "sort_order",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "created_at",
            "updated_at",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["collect_type"] = instance.collect_type.name if instance.collect_type_id else None
        return data

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("名称不能为空")
        return value

    def validate(self, attrs):
        collect_type_name = attrs.pop("collect_type", None)
        if collect_type_name not in (None, ""):
            attrs["_collect_type_name"] = str(collect_type_name).strip()
        if self.instance and "collect_instance" in attrs and attrs["collect_instance"] is not None:
            if attrs["collect_instance"].pk != self.instance.collect_instance_id:
                raise serializers.ValidationError({"collect_instance": "编辑时不能更换采集实例"})
        if self.instance and attrs.get("_collect_type_name"):
            current_name = self.instance.collect_type.name if self.instance.collect_type_id else None
            if attrs["_collect_type_name"] != current_name:
                raise serializers.ValidationError({"collect_type": "编辑时不能更换采集类型"})
        merged = {
            field: attrs.get(field, getattr(self.instance, field, None) if self.instance else None)
            for field in ("extractor_type", "source_field", "target_field", "condition", "config", "delete_source")
        }
        if not merged["source_field"]:
            merged["source_field"] = "message"
        try:
            normalized = normalize_rule(merged)
        except RuleValidationError as exc:
            raise serializers.ValidationError({"rule": str(exc)}) from exc
        attrs["source_field"] = format_path(normalized.source_path)
        attrs["target_field"] = format_path(normalized.target_path) if normalized.target_path else None
        attrs["condition"] = normalized.condition
        attrs["config"] = normalized.config
        attrs["delete_source"] = normalized.delete_source
        return attrs
