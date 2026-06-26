from rest_framework import serializers

from apps.cmdb.constants.constants import NETWORK_TOPO_DEFAULT_HOP, NETWORK_TOPO_MAX_HOP


class NetworkStatusTopologyRequestSerializer(serializers.Serializer):
    model_id = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    inst_id = serializers.IntegerField(required=True, min_value=1)
    depth = serializers.IntegerField(
        required=False,
        default=NETWORK_TOPO_DEFAULT_HOP,
        min_value=1,
        max_value=NETWORK_TOPO_MAX_HOP,
    )
