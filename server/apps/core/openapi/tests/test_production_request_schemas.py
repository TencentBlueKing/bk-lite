"""现有各模块请求 Serializer 必须能发布成 ITSM 可加载的对象 Schema。

规则与 ITSM 网关动作的输入渲染子集一致：单一 type，对象必须声明 properties，
数组必须声明 items，不使用 not / 组合关键字。真正多态、无法收成单一 type 的字段
才允许留在豁免名单里。
"""

import importlib

import pytest
from rest_framework import serializers

from apps.core.openapi.schema import serializer_to_schema

pytestmark = pytest.mark.unit

_MODULES = (
    "apps.alerts.openapi_serializers",
    "apps.apm.openapi_serializers",
    "apps.cmdb.openapi_serializers",
    "apps.job_mgmt.openapi_serializers",
    "apps.log.openapi_serializers",
    "apps.monitor.openapi_serializers",
    "apps.node_mgmt.openapi_serializers",
    "apps.patch_mgmt.openapi_serializers",
    "apps.system_mgmt.openapi_serializers",
    "apps.workflow.openapi_serializers",
)

# match_rules.value 按字段可以是字符串、数字或列表，不能收成 ITSM 接受的单一 type。
_ITSM_INPUT_EXEMPT = {
    "AlertShieldCreateRequestSerializer",
    "AlertShieldUpdateRequestSerializer",
}

_SUPPORTED_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean"})
_UNSUPPORTED_KEYWORDS = frozenset({"$ref", "allOf", "anyOf", "oneOf", "not", "if", "then", "else"})


def _serializer_classes():
    found = []
    for module_name in _MODULES:
        module = importlib.import_module(module_name)
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, serializers.BaseSerializer) and obj.__module__ == module.__name__ and "Response" not in name:
                found.append(obj)
    return found


def _normalize_nullable(node):
    node_type = node.get("type")
    if isinstance(node_type, list) and len(node_type) == 2 and "null" in node_type:
        node["type"] = next(item for item in node_type if item != "null")
    for child in node.get("properties", {}).values():
        _normalize_nullable(child)
    items = node.get("items")
    if isinstance(items, dict):
        _normalize_nullable(items)


def _input_schema_error(node, path):
    if not isinstance(node, dict):
        return f"{path} must be an object"
    for keyword in _UNSUPPORTED_KEYWORDS:
        if keyword in node:
            return f"{path} uses {keyword}"
    node_type = node.get("type")
    if not isinstance(node_type, str) or node_type not in _SUPPORTED_TYPES:
        return f"{path} type {node_type!r} is not a single supported type"
    if node_type == "object":
        properties = node.get("properties")
        if not isinstance(properties, dict):
            return f"{path} object is missing properties"
        for name, child in properties.items():
            error = _input_schema_error(child, f"{path}.{name}")
            if error:
                return error
    elif node_type == "array":
        if "items" not in node:
            return f"{path} array is missing items"
        return _input_schema_error(node["items"], f"{path}[]")
    return None


def test_production_request_serializers_publish_itsm_loadable_schemas():
    failures = []
    seen = set()
    for serializer_class in _serializer_classes():
        seen.add(serializer_class.__name__)
        schema = serializer_to_schema(serializer_class)
        if serializer_class.__name__ in _ITSM_INPUT_EXEMPT:
            continue
        _normalize_nullable(schema)
        error = _input_schema_error(schema, "$")
        if error:
            failures.append(f"{serializer_class.__name__}: {error}")

    missing = _ITSM_INPUT_EXEMPT - seen
    assert not missing, missing
    assert failures == []
