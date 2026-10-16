"""DRF Serializer 到 Draft 7 JSON Schema 的公共契约测试。"""

import pytest
from jsonschema import Draft7Validator
from rest_framework import serializers

from apps.core.openapi.schema import serializer_to_schema, success_response_schema
from apps.core.openapi.serializers import OpenAPIRequestSerializer

pytestmark = pytest.mark.unit


def _dynamic_default():
    return "must-not-run"


class ChildSerializer(OpenAPIRequestSerializer):
    code = serializers.CharField(max_length=16)


class ExampleSerializer(OpenAPIRequestSerializer):
    id = serializers.UUIDField()
    name = serializers.CharField(min_length=1, max_length=32)
    count = serializers.IntegerField(required=False, default=20, min_value=1, max_value=500)
    state = serializers.ChoiceField(choices=("ready", "failed"))
    cursor = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list, min_length=1, max_length=3)
    metadata = serializers.DictField(required=False, default=dict)
    children = ChildSerializer(many=True, required=False)
    payload = serializers.JSONField(required=False)
    generated = serializers.CharField(required=False, default=_dynamic_default)


def test_serializer_to_schema_emits_draft7_object_contract():
    schema = serializer_to_schema(ExampleSerializer)
    Draft7Validator.check_schema(schema)
    assert schema == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "name": {"type": "string", "minLength": 1, "maxLength": 32},
            "count": {"type": "integer", "default": 20, "minimum": 1, "maximum": 500},
            "state": {"type": "string", "enum": ["ready", "failed"]},
            "cursor": {
                "type": ["integer", "null"],
                "default": None,
                "minimum": 1,
            },
            "tags": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "default": [],
                "minItems": 1,
                "maxItems": 3,
            },
            "metadata": {"type": "object", "properties": {}, "additionalProperties": True, "default": {}},
            "children": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"code": {"type": "string", "minLength": 1, "maxLength": 16}},
                    "required": ["code"],
                    "additionalProperties": False,
                },
            },
            # JSONField 是动态 JSON 值，不能伪造成固定 object 字段。
            "payload": {"not": {"type": "null"}},
            # 任意 callable 默认值既不执行也不投影。
            "generated": {"type": "string", "minLength": 1},
        },
        "required": ["id", "name", "state"],
        "additionalProperties": False,
    }


def test_success_response_schema_wraps_business_data_in_standard_envelope():
    schema = success_response_schema(ChildSerializer)
    Draft7Validator.check_schema(schema)

    assert schema["properties"]["result"] == {"type": "boolean", "enum": [True]}
    assert schema["properties"]["data"] == {
        "type": "object",
        "properties": {"code": {"type": "string", "minLength": 1, "maxLength": 16}},
        "required": ["code"],
        "additionalProperties": True,
    }
    validator = Draft7Validator(schema)
    assert not list(validator.iter_errors({"result": True, "data": {"code": "ok"}}))
    assert list(validator.iter_errors({"result": False, "data": {"code": "ok"}}))


def test_success_response_schema_allows_additive_fields_without_weakening_declared_contracts():
    class ResponseSerializer(serializers.Serializer):
        child = ChildSerializer()
        children = ChildSerializer(many=True)
        counters = serializers.DictField(child=serializers.IntegerField())

    schema = success_response_schema(ResponseSerializer)
    validator = Draft7Validator(schema)

    additive_response = {
        "result": True,
        "data": {
            "child": {"code": "one", "new_child_field": "later"},
            "children": [{"code": "two", "new_item_field": "later"}],
            "counters": {"known_later": 1},
            "new_data_field": "later",
        },
        "new_envelope_field": "later",
    }
    assert not list(validator.iter_errors(additive_response))

    assert list(validator.iter_errors({"result": True, "data": additive_response["data"] | {"child": {}}}))
    assert list(validator.iter_errors({"result": True, "data": additive_response["data"] | {"child": {"code": 1}}}))
    assert list(validator.iter_errors({"result": True, "data": additive_response["data"] | {"counters": {"known_later": "one"}}}))
    assert list(validator.iter_errors({"result": True}))
    assert list(validator.iter_errors(additive_response | {"result": False}))


def test_serializer_to_schema_keeps_request_objects_strict_recursively():
    class RequestSerializer(serializers.Serializer):
        child = ChildSerializer()
        children = ChildSerializer(many=True)

    validator = Draft7Validator(serializer_to_schema(RequestSerializer))

    assert list(validator.iter_errors({"child": {"code": "one"}, "children": [{"code": "two"}], "unknown": True}))
    assert list(validator.iter_errors({"child": {"code": "one", "unknown": True}, "children": [{"code": "two"}]}))
    assert list(validator.iter_errors({"child": {"code": "one"}, "children": [{"code": "two", "unknown": True}]}))


def test_nullable_is_preserved_recursively_without_narrowing_dynamic_json():
    class NullableSerializer(OpenAPIRequestSerializer):
        child = ChildSerializer(allow_null=True)
        values = serializers.ListField(child=serializers.IntegerField(allow_null=True), allow_null=True)
        payload = serializers.JSONField(allow_null=True)

    properties = serializer_to_schema(NullableSerializer)["properties"]
    assert properties["child"]["type"] == ["object", "null"]
    assert properties["values"]["type"] == ["array", "null"]
    assert properties["values"]["items"]["type"] == ["integer", "null"]
    assert properties["payload"] == {}


def test_serializer_to_schema_rejects_unsupported_field_type():
    class UnsupportedSerializer(serializers.Serializer):
        value = serializers.Field()

    with pytest.raises(ValueError, match="UnsupportedSerializer.value"):
        serializer_to_schema(UnsupportedSerializer)
