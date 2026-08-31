# -- coding: utf-8 --
from rest_framework import serializers

from apps.operation_analysis.constants.import_export import CANVAS_TYPES, CONFIG_TYPES, ConflictAction, ObjectType, ScopeType


class ExportRequestSerializer(serializers.Serializer):
    MAX_OBJECT_IDS = 1000

    object_type = serializers.ChoiceField(
        choices=[t.value for t in ObjectType],
        help_text="对象类型",
    )
    object_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=MAX_OBJECT_IDS,
        help_text="要导出的对象ID列表",
    )

    def validate(self, attrs):
        object_type = attrs["object_type"]

        if object_type in [t.value for t in CANVAS_TYPES]:
            attrs["scope"] = ScopeType.CANVAS.value
        elif object_type in [t.value for t in CONFIG_TYPES]:
            attrs["scope"] = ScopeType.CONFIG.value
        else:
            raise serializers.ValidationError("object_type不支持导出")

        return attrs


class ImportPrecheckRequestSerializer(serializers.Serializer):
    yaml_content = serializers.CharField(
        help_text="YAML文件内容",
    )
    target_directory_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="画布对象目标目录ID（导入画布时必填）",
    )

    def validate_yaml_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("YAML内容不能为空")
        return value


class ConflictDecisionSerializer(serializers.Serializer):
    object_key = serializers.CharField(help_text="对象业务键")
    action = serializers.ChoiceField(
        choices=[a.value for a in ConflictAction],
        help_text="冲突处理策略",
    )


class SecretSupplementSerializer(serializers.Serializer):
    object_key = serializers.CharField(help_text="对象业务键")
    field = serializers.CharField(help_text="敏感字段名")
    value = serializers.CharField(help_text="敏感字段值")


class ImportSubmitRequestSerializer(serializers.Serializer):
    yaml_content = serializers.CharField(
        help_text="YAML文件内容（与precheck相同）",
    )
    target_directory_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="画布对象目标目录ID",
    )
    conflict_decisions = serializers.ListField(
        child=ConflictDecisionSerializer(),
        required=False,
        default=list,
        help_text="冲突决策列表",
    )
    secret_supplements = serializers.ListField(
        child=SecretSupplementSerializer(),
        required=False,
        default=list,
        help_text="敏感字段补充列表",
    )

    def validate_yaml_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("YAML内容不能为空")
        return value


class ConflictItemSerializer(serializers.Serializer):
    object_key = serializers.CharField()
    object_type = serializers.CharField()
    reason = serializers.CharField()
    suggested_actions = serializers.ListField(child=serializers.CharField())


class WarningItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    object_key = serializers.CharField(required=False)
    field = serializers.CharField(required=False)


class ErrorItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField(required=False)


class ObjectCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    by_type = serializers.DictField(child=serializers.IntegerField())


class PrecheckResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    counts = ObjectCountsSerializer()
    conflicts = ConflictItemSerializer(many=True)
    warnings = WarningItemSerializer(many=True)
    errors = ErrorItemSerializer(many=True)


class ImportResultItemSerializer(serializers.Serializer):
    object_key = serializers.CharField()
    object_type = serializers.CharField()
    status = serializers.CharField()
    message = serializers.CharField()
    new_id = serializers.IntegerField(allow_null=True)


class ImportSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    success = serializers.IntegerField()
    failed = serializers.IntegerField()
    skipped = serializers.IntegerField()
    overwritten = serializers.IntegerField()


class ImportSubmitResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    results = ImportResultItemSerializer(many=True)
    summary = ImportSummarySerializer()


class ExportResponseSerializer(serializers.Serializer):
    yaml_content = serializers.CharField()
    summary = serializers.DictField()
