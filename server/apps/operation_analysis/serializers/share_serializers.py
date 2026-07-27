from rest_framework import serializers


class SharePrepareSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)


class ShareExchangeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512, required=False, allow_blank=True)
    state = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate(self, attrs):
        token = (attrs.get("token") or "").strip()
        state = (attrs.get("state") or "").strip()
        if bool(token) == bool(state):
            raise serializers.ValidationError("必须提供 token 或 state 之一")
        attrs["token"] = token or None
        attrs["state"] = state or None
        return attrs


class ShareNetworkTopologyMetricValuesSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField(), allow_empty=True)


class ShareNetworkTopologyLinkRuntimeSerializer(serializers.Serializer):
    link = serializers.DictField()
    nodes = serializers.ListField(child=serializers.DictField(), required=False, allow_null=True)
