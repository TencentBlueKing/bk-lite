"""OpenAPI 暴露 Serializer 的 Draft 7 JSON Schema 投影。"""

import json

from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.fields import empty

JSON_SCHEMA_DRAFT7 = "http://json-schema.org/draft-07/schema#"


def serializer_to_schema(serializer_class: type, *, allow_additional_properties: bool = False) -> dict:
    """把 DRF Serializer 类转为可直接发布的 Draft 7 object schema。"""
    if not (isinstance(serializer_class, type) and issubclass(serializer_class, serializers.BaseSerializer)):
        raise ValueError("serializer_class must be a DRF Serializer class")

    try:
        serializer = serializer_class()
    except Exception as exc:
        raise ValueError(f"cannot instantiate {serializer_class.__name__}") from exc

    schema = _field_to_schema(
        serializer,
        serializer_class.__name__,
        allow_additional_properties=allow_additional_properties,
    )
    if schema.get("type") != "object":
        raise ValueError(f"{serializer_class.__name__} must describe a JSON object")
    result = {"$schema": JSON_SCHEMA_DRAFT7, **schema}
    try:
        json.dumps(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{serializer_class.__name__} contains non-JSON schema values") from exc
    return result


def success_response_schema(serializer_class: type) -> dict:
    """构造内部端点统一成功 envelope 的完整 Draft 7 schema。"""
    data_schema = dict(serializer_to_schema(serializer_class, allow_additional_properties=True))
    data_schema.pop("$schema", None)
    return {
        "$schema": JSON_SCHEMA_DRAFT7,
        "type": "object",
        "properties": {
            "result": {"type": "boolean", "enum": [True]},
            "data": data_schema,
        },
        "required": ["result", "data"],
        "additionalProperties": True,
    }


def _field_to_schema(field, path: str, *, allow_additional_properties: bool) -> dict:
    if isinstance(field, serializers.ListSerializer):
        schema = {
            "type": "array",
            "items": _field_to_schema(
                field.child,
                f"{path}[]",
                allow_additional_properties=allow_additional_properties,
            ),
        }
        _apply_array_limits(schema, field)
    elif isinstance(field, serializers.BaseSerializer):
        properties = {}
        required = []
        for name, child in field.fields.items():
            properties[name] = _field_to_schema(
                child,
                f"{path}.{name}",
                allow_additional_properties=allow_additional_properties,
            )
            if child.required:
                required.append(name)
        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": allow_additional_properties,
        }
        if required:
            schema["required"] = required
    elif isinstance(field, serializers.ListField):
        schema = {
            "type": "array",
            "items": _list_item_schema(
                field.child,
                f"{path}[]",
                allow_additional_properties=allow_additional_properties,
            ),
        }
        _apply_array_limits(schema, field)
    elif isinstance(field, serializers.DictField):
        schema = {
            "type": "object",
            "additionalProperties": _dict_value_schema(
                field.child,
                f"{path}.*",
                allow_additional_properties=allow_additional_properties,
            ),
        }
    elif isinstance(field, serializers.JSONField):
        # JSONField 接受任意 JSON 值，空 schema 比伪造 object 字段更忠实。
        schema = {} if field.allow_null else {"not": {"type": "null"}}
    elif isinstance(field, serializers.ChoiceField):
        choices = list(field.choices)
        schema = {"enum": choices}
        choice_type = _choice_type(choices)
        if choice_type is not None:
            schema["type"] = choice_type
    elif isinstance(field, serializers.BooleanField):
        schema = {"type": "boolean"}
    elif isinstance(field, serializers.IntegerField):
        schema = {"type": "integer"}
        _copy_number_limits(schema, field)
    elif isinstance(field, serializers.FloatField):
        schema = {"type": "number"}
        _copy_number_limits(schema, field)
    elif isinstance(field, serializers.DateTimeField):
        schema = {"type": "string", "format": "date-time"}
    elif isinstance(field, serializers.DateField):
        schema = {"type": "string", "format": "date"}
    elif isinstance(field, serializers.TimeField):
        schema = {"type": "string", "format": "time"}
    elif isinstance(field, serializers.UUIDField):
        schema = {"type": "string", "format": "uuid"}
    elif isinstance(field, serializers.RegexField):
        validator = next((item for item in field.validators if isinstance(item, RegexValidator)), None)
        if validator is None:
            raise ValueError(f"unsupported DRF field at {path}: RegexField without regex")
        pattern = getattr(validator.regex, "pattern", validator.regex)
        schema = {"type": "string", "pattern": pattern}
        _copy_string_limits(schema, field)
    elif isinstance(field, serializers.CharField):
        schema = {"type": "string"}
        _copy_string_limits(schema, field)
    else:
        raise ValueError(f"unsupported DRF field at {path}: {type(field).__name__}")

    _apply_nullable(schema, field)
    _apply_default(schema, field)
    return schema


def _list_item_schema(child, path: str, *, allow_additional_properties: bool) -> dict:
    if type(child).__name__ == "_UnvalidatedField":
        return {}
    return _field_to_schema(child, path, allow_additional_properties=allow_additional_properties)


def _dict_value_schema(child, path: str, *, allow_additional_properties: bool):
    if type(child).__name__ == "_UnvalidatedField":
        return True
    return _field_to_schema(child, path, allow_additional_properties=allow_additional_properties)


def _choice_type(choices):
    non_null = [choice for choice in choices if choice is not None]
    if not non_null:
        return None
    if all(isinstance(choice, bool) for choice in non_null):
        return "boolean"
    if all(isinstance(choice, int) and not isinstance(choice, bool) for choice in non_null):
        return "integer"
    if all(isinstance(choice, (int, float)) and not isinstance(choice, bool) for choice in non_null):
        return "number"
    if all(isinstance(choice, str) for choice in non_null):
        return "string"
    return None


def _copy_number_limits(schema, field):
    if field.min_value is not None:
        schema["minimum"] = field.min_value
    if field.max_value is not None:
        schema["maximum"] = field.max_value


def _copy_string_limits(schema, field):
    minimum = field.min_length
    if minimum is None and not field.allow_blank:
        minimum = 1
    if minimum is not None:
        schema["minLength"] = minimum
    if field.max_length is not None:
        schema["maxLength"] = field.max_length


def _apply_array_limits(schema, field):
    if not field.allow_empty:
        schema["minItems"] = 1
    if field.min_length is not None:
        schema["minItems"] = field.min_length
    if field.max_length is not None:
        schema["maxItems"] = field.max_length


def _apply_nullable(schema, field):
    if not field.allow_null or not schema:
        return
    field_type = schema.get("type")
    if isinstance(field_type, str):
        schema["type"] = [field_type, "null"]
    enum = schema.get("enum")
    if enum is not None and None not in enum:
        enum.append(None)


def _apply_default(schema, field):
    default = field.default
    if default is empty:
        return
    if default is list:
        value = []
    elif default is dict:
        value = {}
    elif callable(default):
        return
    else:
        value = default
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return
    schema["default"] = value
