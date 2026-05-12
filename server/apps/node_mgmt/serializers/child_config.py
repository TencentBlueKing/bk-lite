from rest_framework import serializers

from apps.node_mgmt.models.sidecar import ChildConfig, CollectorConfiguration


class ChildConfigSerializer(serializers.ModelSerializer):
    collector_config = serializers.PrimaryKeyRelatedField(queryset=CollectorConfiguration.objects.all())

    class Meta:
        model = ChildConfig
        fields = [
            "id",
            "collect_type",
            "config_type",
            "content",
            "collector_config",
            "env_config",
            "sort_order",
            "config_section",
        ]
        read_only_fields = ["id"]
