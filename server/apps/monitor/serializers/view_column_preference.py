from rest_framework import serializers


class MonitorViewColumnPreferenceSerializer(serializers.Serializer):
    field_keys = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=False),
        allow_empty=False,
        max_length=100,
    )

    def validate_field_keys(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("field_keys 不能包含重复字段")
        return value

    def validate(self, attrs):
        raw_keys = self.initial_data.get("field_keys")
        if isinstance(raw_keys, list) and any(type(item) is not str for item in raw_keys):
            raise serializers.ValidationError({"field_keys": "字段键必须是字符串"})
        return attrs
