from rest_framework import serializers

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES, NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.operation_analysis.services.user_messages import oa_message


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
    depth = serializers.IntegerField(required=False, min_value=1, max_value=1)

    def validate_inst_uuids(self, value):
        strings = [str(item) for item in value]
        if len(set(strings)) != len(strings):
            raise serializers.ValidationError(oa_message("messages.sw_inst_duplicate", "inst_uuids 不允许重复"))
        return strings

    def validate(self, attrs):
        inst_uuids = attrs.get("inst_uuids") or []
        node_limit = attrs.get("node_limit") or NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES
        if len(inst_uuids) > node_limit:
            raise serializers.ValidationError(
                {"inst_uuids": oa_message("messages.sw_over_node_limit", "不能超过 node_limit {node_limit}", node_limit=node_limit)}
            )
        if attrs.get("depth") is not None and len(inst_uuids) != 1:
            raise serializers.ValidationError({"depth": oa_message("messages.nst_one_hop_single", "一跳展开只接受单个 inst_uuid")})
        return attrs


class _Application3DStrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(oa_message("messages.sw_body_object", "请求体必须为对象"))
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: oa_message("messages.sw_unknown_field", "不支持的字段") for key in sorted(unknown)})
        return super().to_internal_value(data)


class Application3DWallRequestSerializer(_Application3DStrictSerializer):
    applied_filters = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField(allow_blank=False)),
        required=False,
        allow_empty=True,
    )
    application_id = serializers.UUIDField(required=False)


class Application3DApplicationDetailRequestSerializer(_Application3DStrictSerializer):
    application_id = serializers.UUIDField()
    cursor = serializers.CharField(required=False, allow_blank=False, max_length=512)


class Application3DArchitectureRequestSerializer(_Application3DStrictSerializer):
    application_id = serializers.UUIDField()


class Application3DAlarmDetailRequestSerializer(_Application3DStrictSerializer):
    application_id = serializers.UUIDField()
    alarm_id = serializers.CharField(allow_blank=False, max_length=100)


class Application3DMetricRequestSerializer(Application3DAlarmDetailRequestSerializer):
    pass


class RelatedTopologyRequestSerializer(_Application3DStrictSerializer):
    inst_uuid = serializers.UUIDField()

    def validate_inst_uuid(self, value):
        return str(value)


class Room3DRoomsRequestSerializer(_Application3DStrictSerializer):
    pass


class Room3DLayoutRequestSerializer(_Application3DStrictSerializer):
    server_room_id = serializers.UUIDField()

    def validate_server_room_id(self, value):
        return str(value)
