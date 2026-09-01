from rest_framework import serializers


class ApplicationResourceTopologyQuerySerializer(serializers.Serializer):
    depth = serializers.IntegerField(required=False, min_value=1, max_value=5, default=1)


class ApplicationResourceEntrySerializer(serializers.Serializer):
    model_id = serializers.ChoiceField(choices=["system", "application"])


class ApplicationResourceNodeUuidsSerializer(serializers.Serializer):
    node_uuids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )
