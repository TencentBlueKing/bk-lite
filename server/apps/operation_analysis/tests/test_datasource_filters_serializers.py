"""数据源过滤器、序列化器校验与 schema 校验的覆盖测试。

对照 specs/capabilities/legacy-prd-运营分析-管理.md：数据源支持按名称/REST/标签/图表类型搜索，
field_schema 列定义需 key 非空且不重复。
"""

import json
from pathlib import Path

import pytest
from rest_framework import serializers
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.filters.datasource_filters import DataSourceAPIModelFilter
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag

# --------------------------------------------------------------------------
# DataSourceAPIModelFilter
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_filter_search_matches_name_or_rest_api():
    DataSourceAPIModel.objects.create(name="cpu-source", rest_api="monitor/cpu", created_by="s", updated_by="s")
    DataSourceAPIModel.objects.create(name="mem-source", rest_api="monitor/mem", created_by="s", updated_by="s")
    qs = DataSourceAPIModel.objects.all()

    assert DataSourceAPIModelFilter.filter_search(qs, "search", "cpu").count() == 1
    assert DataSourceAPIModelFilter.filter_search(qs, "search", "monitor").count() == 2
    # 空关键字返回原查询集
    assert DataSourceAPIModelFilter.filter_search(qs, "search", "  ").count() == 2


@pytest.mark.django_db
def test_filter_tags_by_ids():
    tag = DataSourceTag.objects.create(tag_id="t1", name="Tag1", created_by="s", updated_by="s")
    ds = DataSourceAPIModel.objects.create(name="ds", rest_api="monitor/x", created_by="s", updated_by="s")
    ds.tag.set([tag.id])

    qs = DataSourceAPIModel.objects.all()
    assert DataSourceAPIModelFilter.filter_tags(qs, "tags", str(tag.id)).count() == 1


@pytest.mark.django_db
def test_filter_chart_type_contains():
    DataSourceAPIModel.objects.create(name="ds1", rest_api="m/1", chart_type=["line"], created_by="s", updated_by="s")
    DataSourceAPIModel.objects.create(name="ds2", rest_api="m/2", chart_type=["bar"], created_by="s", updated_by="s")
    qs = DataSourceAPIModel.objects.all()

    assert DataSourceAPIModelFilter.filter_chart_type(qs, "chart_type", "line").count() == 1
    assert DataSourceAPIModelFilter.filter_chart_type(qs, "chart_type", "line,bar").count() == 2
    # 空值返回原查询集
    assert DataSourceAPIModelFilter.filter_chart_type(qs, "chart_type", "  ").count() == 2


# --------------------------------------------------------------------------
# DataSourceAPIModelSerializer.validate_field_schema
# --------------------------------------------------------------------------


def _validate_field_schema(value):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    # validate_field_schema 不依赖 self，直接通过未初始化实例调用
    return DataSourceAPIModelSerializer.validate_field_schema(DataSourceAPIModelSerializer.__new__(DataSourceAPIModelSerializer), value)


def test_validate_field_schema_empty_passes():
    assert _validate_field_schema([]) == []


def test_validate_field_schema_non_list_rejected():
    with pytest.raises(serializers.ValidationError):
        _validate_field_schema({"key": "x"})


@pytest.mark.parametrize("value", [[1], [None], ["x"], [{"key": 1}]])
@pytest.mark.django_db
def test_validate_field_schema_malformed_items_return_serializer_error(value, authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer(
        data=_nats_datasource_payload(field_schema=value),
        context={"request": _serializer_request(authenticated_user)},
    )

    assert serializer.is_valid() is False
    assert "field_schema" in serializer.errors


def test_validate_field_schema_empty_key_rejected():
    with pytest.raises(serializers.ValidationError):
        _validate_field_schema([{"key": "  "}])


def test_validate_field_schema_duplicate_key_rejected():
    with pytest.raises(serializers.ValidationError):
        _validate_field_schema([{"key": "a"}, {"key": "a"}])


def test_validate_field_schema_valid():
    value = [{"key": "a"}, {"key": "b"}]
    assert _validate_field_schema(value) == value


def _validate_params(value):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer.__new__(DataSourceAPIModelSerializer)
    return DataSourceAPIModelSerializer.validate_params(serializer, value)


@pytest.mark.parametrize("param_type", ["number", "boolean", "date"])
@pytest.mark.unit
def test_validate_params_rejects_unsupported_unified_filter_types(param_type):
    with pytest.raises(serializers.ValidationError):
        _validate_params(
            [
                {
                    "name": "invalid_filter",
                    "alias_name": "非法筛选",
                    "type": param_type,
                    "filterType": "filter",
                    "value": None,
                }
            ]
        )


@pytest.mark.parametrize("param_type", ["string", "timeRange", "dateRange"])
@pytest.mark.unit
def test_validate_params_accepts_supported_unified_filter_types(param_type):
    value = [
        {
            "name": "valid_filter",
            "alias_name": "合法筛选",
            "type": param_type,
            "filterType": "filter",
            "value": None,
        }
    ]
    assert _validate_params(value) == value


def _serializer_request(user):
    request = APIRequestFactory().post("/operation_analysis/api/data_source/", data={}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    request.user = user
    force_authenticate(request, user=user)
    return request


def _nats_datasource_payload(**overrides):
    payload = {
        "name": "自定义监控查询",
        "rest_api": "monitor/query_safe",
        "source_type": "nats",
        "connection_config": {},
        "query_config": {},
        "params": [],
        "chart_type": ["line"],
        "field_schema": [],
        "groups": [1],
        "namespaces": [],
        "tag": [],
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
@pytest.mark.parametrize("rest_api", ["monitor/mm_query", "monitor/mm_query_range"])
def test_datasource_serializer_rejects_new_raw_monitor_query_routes(authenticated_user, rest_api):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data=_nats_datasource_payload(rest_api=rest_api),
    )

    assert not serializer.is_valid()
    assert serializer.errors["rest_api"] == ["该监控裸查询接口已退役，禁止继续使用"]


@pytest.mark.django_db
def test_datasource_serializer_rejects_raw_monitor_query_with_default_source_type(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    payload = _nats_datasource_payload(rest_api="monitor/mm_query")
    payload.pop("source_type")
    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data=payload,
    )

    assert not serializer.is_valid()
    assert serializer.errors["rest_api"] == ["该监控裸查询接口已退役，禁止继续使用"]


@pytest.mark.django_db
def test_datasource_serializer_rejects_existing_raw_monitor_query_route(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="历史监控查询",
        rest_api="monitor/mm_query_range",
        source_type="nats",
        groups=[1],
        created_by="system",
        updated_by="system",
    )
    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data=_nats_datasource_payload(name="历史监控查询", rest_api="monitor/mm_query_range"),
    )

    assert not serializer.is_valid()
    assert serializer.errors["rest_api"] == ["该监控裸查询接口已退役，禁止继续使用"]


@pytest.mark.django_db
def test_datasource_serializer_allows_migrating_existing_raw_route(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="历史监控查询",
        rest_api="monitor/mm_query_range",
        source_type="nats",
        groups=[1],
        created_by="system",
        updated_by="system",
    )
    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data=_nats_datasource_payload(name="历史监控查询", rest_api="monitor/get_host_metric_range"),
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_empty_groups_on_create(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data=_nats_datasource_payload(groups=[]),
    )

    assert not serializer.is_valid()
    assert "groups" in serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_create_that_omits_groups(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    payload = _nats_datasource_payload()
    payload.pop("groups")
    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data=payload,
    )

    assert not serializer.is_valid()
    assert "groups" in serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_empty_groups_on_update(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="自定义源",
        rest_api="custom/query",
        source_type="nats",
        groups=[1],
        created_by="s",
        updated_by="s",
    )
    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={"groups": []},
        partial=True,
    )

    assert not serializer.is_valid()
    assert "groups" in serializer.errors
    datasource.refresh_from_db()
    assert datasource.groups == [1]


@pytest.mark.django_db
def test_serializer_allows_empty_groups_for_builtin_instance(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="内置源",
        rest_api="builtin/query",
        source_type="nats",
        groups=[1],
        is_build_in=True,
        build_in_key="builtin::query",
        created_by="s",
        updated_by="s",
    )
    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={"groups": []},
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["groups"] == []


def test_builtin_datasource_registry_stops_publishing_raw_monitor_query_routes():
    source_file = Path(__file__).parents[1] / "support-files" / "source_api.json"
    rest_apis = {item["rest_api"] for item in json.loads(source_file.read_text())}

    assert "monitor/mm_query" not in rest_apis
    assert "monitor/mm_query_range" not in rest_apis


@pytest.mark.django_db
def test_datasource_serializer_accepts_rest_api_connector_config(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "外部订单 API",
            "rest_api": "",
            "source_type": "rest_api",
            "connection_config": {
                "url": "https://example.com/orders",
                "method": "GET",
                "headers": {"Authorization": "Bearer token"},
                "timeout": 10,
            },
            "query_config": {"response_path": "data.items", "limit": 100},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        },
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_datasource_serializer_rejects_unknown_source_type(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "bad",
            "rest_api": "",
            "source_type": "ftp",
            "connection_config": {},
            "query_config": {},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        },
    )

    assert not serializer.is_valid()
    assert "source_type" in serializer.errors


@pytest.mark.django_db
@pytest.mark.integration
def test_datasource_serializer_cannot_forge_builtin_identity(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    serializer = DataSourceAPIModelSerializer(
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "custom",
            "rest_api": "custom/query",
            "source_type": "nats",
            "connection_config": {},
            "query_config": {},
            "params": [],
            "chart_type": ["single"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
            "is_build_in": True,
            "build_in_key": "forged",
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert "is_build_in" not in serializer.validated_data
    assert "build_in_key" not in serializer.validated_data


@pytest.mark.django_db
def test_datasource_serializer_preserves_redacted_connection_secret(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="db-source",
        rest_api="",
        source_type="mysql",
        connection_config={
            "host": "127.0.0.1",
            "port": 3306,
            "username": "root",
            "password": "real-password",
        },
        query_config={"table": "orders"},
        params=[],
        chart_type=["table"],
        field_schema=[],
        groups=[1],
        created_by="s",
        updated_by="s",
    )

    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "db-source",
            "rest_api": "",
            "source_type": "mysql",
            "connection_config": {
                "host": "127.0.0.1",
                "port": 3306,
                "username": "root",
                "password": "******",
            },
            "query_config": {"table": "orders"},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["connection_config"]["password"] == "real-password"


@pytest.mark.django_db
def test_datasource_serializer_redacts_and_preserves_nested_separator_variants(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="rest-source",
        rest_api="",
        source_type="rest_api",
        connection_config={"headers": {"X-API-Key": "real-api-key"}},
        query_config={"body": {"items": [{"client-secret": "real-client-secret"}]}},
        groups=[1],
        created_by="s",
        updated_by="s",
    )

    output = DataSourceAPIModelSerializer(datasource, context={"request": _serializer_request(authenticated_user)}).data
    assert output["connection_config"]["headers"]["X-API-Key"] == "******"
    assert output["query_config"]["body"]["items"][0]["client-secret"] == "******"

    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={**output, "namespaces": [], "tag": []},
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["connection_config"]["headers"]["X-API-Key"] == "real-api-key"
    assert serializer.validated_data["query_config"]["body"]["items"][0]["client-secret"] == "real-client-secret"


def test_transform_config_for_source_type_strips_python_transform_for_database():
    from apps.operation_analysis.serializers.datasource_serializers import DISABLED_TRANSFORM_CONFIG, transform_config_for_source_type

    leftover = {
        "enabled": True,
        "language": "python",
        "script": "def transform(rows, params): return rows",
    }
    assert transform_config_for_source_type("postgresql", leftover) == DISABLED_TRANSFORM_CONFIG
    assert transform_config_for_source_type("mysql", leftover) == DISABLED_TRANSFORM_CONFIG
    assert transform_config_for_source_type("prometheus", leftover) == DISABLED_TRANSFORM_CONFIG
    assert transform_config_for_source_type("nats", leftover) == DISABLED_TRANSFORM_CONFIG
    assert transform_config_for_source_type("rest_api", leftover) == leftover
    assert transform_config_for_source_type("excel", leftover) == leftover


@pytest.mark.django_db
def test_datasource_serializer_strips_transform_when_switching_rest_to_postgresql(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    datasource = DataSourceAPIModel.objects.create(
        name="rest1",
        rest_api="",
        source_type="rest_api",
        connection_config={"url": "https://example.com/orders", "method": "GET", "timeout": 10},
        query_config={"response_path": "data.items"},
        transform_config={
            "enabled": True,
            "language": "python",
            "script": "def transform(rows, params): return rows",
        },
        params=[],
        chart_type=["table"],
        field_schema=[],
        groups=[1],
        created_by="s",
        updated_by="s",
    )

    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "rest1",
            "rest_api": "",
            "source_type": "postgresql",
            "connection": None,
            "connection_config": {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "bklite",
                "username": "bklite",
                "password": "secret",
            },
            "query_config": {"sql": "SELECT 1", "table": ""},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["transform_config"]["enabled"] is False
    updated = serializer.save()
    assert updated.source_type == "postgresql"
    assert (updated.transform_config or {}).get("enabled") is False


@pytest.mark.django_db
def test_datasource_serializer_keeps_rest_transform_when_type_unchanged(authenticated_user):
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    transform_config = {
        "enabled": True,
        "language": "python",
        "script": "def transform(rows, params): return rows",
    }
    datasource = DataSourceAPIModel.objects.create(
        name="rest-keep",
        rest_api="",
        source_type="rest_api",
        connection_config={"url": "https://example.com/orders", "method": "GET", "timeout": 10},
        query_config={"response_path": "data.items"},
        transform_config=transform_config,
        params=[],
        chart_type=["table"],
        field_schema=[],
        groups=[1],
        created_by="s",
        updated_by="s",
    )

    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "rest-keep",
            "rest_api": "",
            "source_type": "rest_api",
            "connection_config": {"url": "https://example.com/orders", "method": "GET", "timeout": 10},
            "query_config": {"response_path": "data.items"},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["transform_config"]["enabled"] is True


@pytest.mark.django_db
def test_datasource_serializer_clears_connection_when_switching_rest_to_excel(authenticated_user):
    from apps.operation_analysis.models.datasource_models import DataConnection
    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer
    from apps.operation_analysis.services.data_connection.config_crypto import encrypt_connection_config

    connection = DataConnection.objects.create(
        name="rest-shared",
        connection_type=DataConnection.TYPE_REST_API,
        groups=[1],
        config=encrypt_connection_config({"base_url": "https://api.example.com", "headers": {}}),
    )
    datasource = DataSourceAPIModel.objects.create(
        name="rest-bound",
        rest_api="",
        source_type="rest_api",
        connection=connection,
        connection_overrides={"path": "orders", "method": "GET", "timeout": 10},
        connection_config={"method": "GET", "timeout": 10},
        query_config={"response_path": "data.items"},
        transform_config={"enabled": True, "language": "python", "script": "def transform(rows, params): return rows"},
        params=[],
        chart_type=["table"],
        field_schema=[],
        groups=[1],
        created_by="s",
        updated_by="s",
    )

    serializer = DataSourceAPIModelSerializer(
        datasource,
        context={"request": _serializer_request(authenticated_user)},
        data={
            "name": "rest-bound",
            "rest_api": "",
            "source_type": "excel",
            "connection_config": {"filename": "demo.xlsx"},
            "query_config": {},
            "params": [],
            "chart_type": ["table"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
        },
    )

    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.source_type == "excel"
    assert updated.connection_id is None
    assert updated.connection_overrides == {}


# --------------------------------------------------------------------------
# schema 校验工具函数
# --------------------------------------------------------------------------


def test_validate_business_key_format_rules():
    from apps.operation_analysis.constants.import_export import ObjectType
    from apps.operation_analysis.schemas.import_export_schema import validate_business_key_format

    assert validate_business_key_format("dashboard::db-a", ObjectType.DASHBOARD) is True
    assert validate_business_key_format("db-a", ObjectType.DASHBOARD) is False
    assert validate_business_key_format("ds::api", ObjectType.DATASOURCE) is True
    assert validate_business_key_format("noseparator", ObjectType.DATASOURCE) is False
    assert validate_business_key_format("123", ObjectType.NAMESPACE) is False
    assert validate_business_key_format("", ObjectType.NAMESPACE) is False
    assert validate_business_key_format("ns-a", ObjectType.NAMESPACE) is True


def test_detect_db_id_references_flags_numeric_ids():
    from apps.operation_analysis.schemas.import_export_schema import detect_db_id_references

    data = {"datasource_id": 5, "nested": {"namespace_ids": [1, 2]}, "organization_id": 9, "name": "ok"}
    violations = detect_db_id_references(data)
    fields = {v["field"] for v in violations}
    assert "datasource_id" in fields
    assert "namespace_ids" in fields
    # organization_id 被豁免
    assert "organization_id" not in fields


def test_detect_db_id_references_allows_network_topology_external_ids():
    from apps.operation_analysis.schemas.import_export_schema import detect_db_id_references

    data = {
        "network_topologies": [
            {
                "key": "networkTopology::demo",
                "name": "demo",
                "base_url": "https://weops.example",
                "token": "******",
                "view_sets": {
                    "nodes": [
                        {
                            "id": "node-1",
                            "bk_obj_id": "bk_firewall",
                            "bk_inst_id": 383679,
                            "plugin_template_id": 2170,
                            "network_collect_task_id": 197,
                            "network_collect_instance_id": 1994,
                        }
                    ],
                    "links": [
                        {
                            "id": "link-1",
                            "source_node_id": "node-1",
                            "target_node_id": "node-2",
                            "port_pairs": [
                                {
                                    "source_interface": {
                                        "bk_obj_id": "bk_interface",
                                        "bk_inst_id": 383676,
                                    },
                                    "target_interface": {
                                        "bk_obj_id": "bk_interface",
                                        "bk_inst_id": 36563,
                                    },
                                }
                            ],
                        }
                    ],
                },
                "refs": {"datasource_keys": [], "namespace_keys": []},
            }
        ]
    }

    assert detect_db_id_references(data) == []


def test_count_objects():
    from apps.operation_analysis.schemas.import_export_schema import YAMLDocument, count_objects

    doc = YAMLDocument(
        meta={"schema_version": "1.1.0"},
        namespaces=[{"key": "n", "name": "n", "domain": "d", "account": "a", "password": "p"}],
    )
    counts = count_objects(doc)
    assert counts["total"] == 1
    assert counts["by_type"]["namespace"] == 1
