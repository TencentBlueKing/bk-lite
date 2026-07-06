from rest_framework import serializers


class ApplicationResourceTopologyQuerySerializer(serializers.Serializer):
    depth = serializers.IntegerField(required=False, min_value=1, max_value=3, default=1)


class ApplicationResourceEntrySerializer(serializers.Serializer):
    model_id = serializers.ChoiceField(choices=["system", "application"])


class ApplicationResourceNodeIdsSerializer(serializers.Serializer):
    node_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )
