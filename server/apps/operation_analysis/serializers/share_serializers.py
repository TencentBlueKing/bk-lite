from rest_framework import serializers


class ShareCreateSerializer(serializers.Serializer):
    permanent = serializers.BooleanField(default=False)
    duration_seconds = serializers.IntegerField(required=False, min_value=3600, max_value=7_776_000)

    def validate(self, attrs):
        if attrs["permanent"] and "duration_seconds" in attrs:
            raise serializers.ValidationError({"duration_seconds": "永久链接不能设置有效时长"})
        return attrs


class ShareExchangeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)

