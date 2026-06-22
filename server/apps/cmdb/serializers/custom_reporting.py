from rest_framework import serializers


class CustomReportingCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    team = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    config = serializers.DictField()
    quick_model = serializers.DictField(required=False)
    is_enabled = serializers.BooleanField(default=True)


class CustomReportingUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False)
    team = serializers.ListField(child=serializers.IntegerField(), required=False)
    config = serializers.DictField(required=False)
    quick_model = serializers.DictField(required=False)
    is_enabled = serializers.BooleanField(required=False)
