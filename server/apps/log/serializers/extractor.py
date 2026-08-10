from rest_framework import serializers

from apps.log.models import LogExtractor
from apps.log.services.log_extractor.semantics import RuleValidationError, format_path, normalize_rule


class LogExtractorSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogExtractor
        fields = (
            "id",
            "name",
            "collect_instance",
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

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("名称不能为空")
        return value

    def validate(self, attrs):
        if self.instance and "collect_instance" in attrs and attrs["collect_instance"].pk != self.instance.collect_instance_id:
            raise serializers.ValidationError({"collect_instance": "编辑时不能更换采集实例"})
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
