"""数据源过滤器、序列化器校验与 schema 校验的覆盖测试。

对照 spec/prd/运营分析·管理：数据源支持按名称/REST/标签/图表类型搜索，
field_schema 列定义需 key 非空且不重复。
"""

import pytest
from rest_framework import serializers

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


def test_validate_field_schema_empty_key_rejected():
    with pytest.raises(serializers.ValidationError):
        _validate_field_schema([{"key": "  "}])


def test_validate_field_schema_duplicate_key_rejected():
    with pytest.raises(serializers.ValidationError):
        _validate_field_schema([{"key": "a"}, {"key": "a"}])


def test_validate_field_schema_valid():
    value = [{"key": "a"}, {"key": "b"}]
    assert _validate_field_schema(value) == value


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


def test_count_objects():
    from apps.operation_analysis.schemas.import_export_schema import YAMLDocument, count_objects

    doc = YAMLDocument(
        meta={"schema_version": "1.1.0"},
        namespaces=[{"key": "n", "name": "n", "domain": "d", "account": "a", "password": "p"}],
    )
    counts = count_objects(doc)
    assert counts["total"] == 1
    assert counts["by_type"]["namespace"] == 1
