"""CMDB 网关请求 Schema：实例 UUID 按 string 暴露，不带 format:uuid。"""

import pytest
from rest_framework import serializers

from apps.cmdb.openapi_serializers import (
    CmdbInstanceAssociationCreateSerializer,
    CmdbInstanceAssociationDeleteSerializer,
    CmdbInstanceBatchDeleteSerializer,
    CmdbInstanceBatchUpdateSerializer,
    CmdbInstanceBatchCreateSerializer,
    CmdbInstanceCreateSerializer,
    CmdbInstanceKeySerializer,
    CmdbInstanceListSerializer,
    CmdbInstanceUpdateSerializer,
    CmdbModelIdSerializer,
    CmdbModuleDataQuerySerializer,
    CmdbNoParamsSerializer,
    InstUuidField,
)
from apps.core.openapi.schema import serializer_to_schema

pytestmark = pytest.mark.unit

CMDB_GATEWAY_SERIALIZERS = (
    CmdbNoParamsSerializer,
    CmdbModelIdSerializer,
    CmdbInstanceListSerializer,
    CmdbModuleDataQuerySerializer,
    CmdbInstanceKeySerializer,
    CmdbInstanceCreateSerializer,
    CmdbInstanceBatchCreateSerializer,
    CmdbInstanceUpdateSerializer,
    CmdbInstanceBatchUpdateSerializer,
    CmdbInstanceBatchDeleteSerializer,
    CmdbInstanceAssociationCreateSerializer,
    CmdbInstanceAssociationDeleteSerializer,
)


def _collect_formats(node, found):
    if isinstance(node, dict):
        if node.get("format") == "uuid":
            found.append(node)
        for value in node.values():
            _collect_formats(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_formats(item, found)


def test_cmdb_gateway_schemas_do_not_emit_uuid_format():
    for serializer_class in CMDB_GATEWAY_SERIALIZERS:
        found = []
        _collect_formats(serializer_to_schema(serializer_class), found)
        assert found == [], serializer_class.__name__


def test_instance_key_schema_exposes_inst_uuid_as_plain_string():
    properties = serializer_to_schema(CmdbInstanceKeySerializer)["properties"]
    assert properties["inst_uuid"] == {"type": "string", "minLength": 1}


def test_inst_uuid_field_accepts_uuid_and_rejects_invalid():
    field = InstUuidField()
    assert field.run_validation("123e4567-e89b-42d3-a456-426614174000") == "123e4567-e89b-42d3-a456-426614174000"
    with pytest.raises(serializers.ValidationError):
        field.run_validation("not-a-uuid")
