import json

from rest_framework import serializers

FILTER_TYPES = {"str=", "str*", "str[]", "int=", "int[]", "list[]"}
FORBIDDEN_FIELDS = {"_id", "model_id", "organization", "_creator", "_created_at", "_updated_at"}
ORDER_ALIASES = {"created_at": "_created_at", "updated_at": "_updated_at", "inst_id": "_id"}


class InstanceListQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=20, min_value=1, max_value=200)
    order = serializers.CharField(default="", allow_blank=True)
    filters = serializers.CharField(default="[]", allow_blank=True)

    def validate_filters(self, raw):
        try:
            filters = json.loads(raw or "[]")
        except (TypeError, ValueError):
            raise serializers.ValidationError("filters 必须是 JSON 数组") from None
        if not isinstance(filters, list):
            raise serializers.ValidationError("filters 必须是 JSON 数组")
        attrs = {item["attr_id"]: item for item in self.context["attrs"] if item.get("attr_id")}
        for item in filters:
            if not isinstance(item, dict) or set(item) != {"field", "type", "value"}:
                raise serializers.ValidationError("过滤条件必须包含 field、type、value")
            if item["field"] in FORBIDDEN_FIELDS or item["field"] not in attrs:
                raise serializers.ValidationError("过滤字段不可用")
            if item["type"] not in FILTER_TYPES:
                raise serializers.ValidationError("过滤操作符不可用")
            attr_type = attrs[item["field"]].get("attr_type")
            compatible_types = {
                "str": {"str=", "str*", "str[]"},
                "int": {"int=", "int[]"},
                "list": {"list[]"},
            }
            if item["type"] not in compatible_types.get(attr_type, set()):
                raise serializers.ValidationError("过滤操作符与字段类型不兼容")
        return filters

    def validate_order(self, raw):
        descending = raw.startswith("-")
        field = raw[1:] if descending else raw
        if not field:
            return ""
        attrs = {item["attr_id"] for item in self.context["attrs"] if item.get("attr_id")}
        mapped = ORDER_ALIASES.get(field, field)
        if field not in attrs and field not in ORDER_ALIASES:
            raise serializers.ValidationError("排序字段不可用")
        return f"-{mapped}" if descending else mapped


def validate_instance_payload(data, attrs, *, team_id, for_update):
    if not isinstance(data, dict) or not data:
        raise serializers.ValidationError("实例属性必须是非空对象")
    allowed = {
        item["attr_id"]
        for item in attrs
        if item.get("attr_id")
        and (not for_update or item.get("editable", False))
        and not item.get("is_display_field", False)
    }
    invalid = set(data) - allowed
    if invalid or set(data) & FORBIDDEN_FIELDS:
        raise serializers.ValidationError({"fields": sorted(invalid | (set(data) & FORBIDDEN_FIELDS))})
    result = dict(data)
    if not for_update:
        result["organization"] = [team_id]
    return result


class BatchCreateSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)


class BatchUpdateSerializer(serializers.Serializer):
    inst_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100)
    update_data = serializers.DictField()


class BatchDeleteSerializer(serializers.Serializer):
    inst_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100)


class AssociationCreateSerializer(serializers.Serializer):
    model_asst_id = serializers.CharField(max_length=255)
    target_model_id = serializers.CharField(max_length=255)
    target_inst_id = serializers.IntegerField(min_value=1)
