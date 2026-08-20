from rest_framework import serializers

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES, NETWORK_STATUS_TOPOLOGY_MAX_NODES


class NetworkStatusTopologyRequestSerializer(serializers.Serializer):
    inst_uuids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        min_length=1,
        max_length=NETWORK_STATUS_TOPOLOGY_MAX_NODES,
    )
    node_limit = serializers.IntegerField(
        required=False,
        default=NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES,
        min_value=1,
        max_value=NETWORK_STATUS_TOPOLOGY_MAX_NODES,
    )

    def validate_inst_uuids(self, value):
        strings = [str(item) for item in value]
        if len(set(strings)) != len(strings):
            raise serializers.ValidationError("inst_uuids 不允许重复")
        return strings

    def validate(self, attrs):
        inst_uuids = attrs.get("inst_uuids") or []
        node_limit = attrs.get("node_limit") or NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES
        if len(inst_uuids) > node_limit:
            raise serializers.ValidationError({"inst_uuids": f"不能超过 node_limit {node_limit}"})
        return attrs
