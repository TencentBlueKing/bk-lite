import pytest

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.named_option_datasources import (
    collect_named_option_datasource_ids,
    expand_widget_manifest_with_named_option_datasources,
)

pytestmark = pytest.mark.django_db

ROOM3D_SWITCH_PARAMS = [
    {
        "name": "server_room_id",
        "inputConfig": {
            "control": "select",
            "componentSwitch": True,
            "optionsSource": {
                "type": "dynamic",
                "sourceRef": {"type": "rest_api", "value": "cmdb/get_room_list"},
                "valueField": "inst_uuid",
                "labelField": "inst_name",
            },
        },
    }
]


def test_collect_named_option_ids_keeps_unique_rest_api_and_existing_source_id():
    DataSourceAPIModel.objects.create(
        id=17,
        name="CMDB 3D机房布局",
        rest_api="cmdb/get_room3d_layout",
        params=ROOM3D_SWITCH_PARAMS
        + [
            {
                "name": "namespace",
                "inputConfig": {
                    "control": "select",
                    "optionsSource": {
                        "type": "dynamic",
                        "sourceId": 9,
                        "valueField": "id",
                        "labelField": "name",
                    },
                },
            },
            {
                "name": "missing",
                "inputConfig": {
                    "control": "select",
                    "optionsSource": {
                        "type": "dynamic",
                        "sourceId": "not-a-number",
                        "valueField": "id",
                        "labelField": "name",
                    },
                },
            },
        ],
    )
    DataSourceAPIModel.objects.create(
        id=42,
        name="CMDB 机房列表",
        rest_api="cmdb/get_room_list",
    )
    DataSourceAPIModel.objects.create(
        id=9,
        name="命名空间选项",
        rest_api="system/namespaces",
    )
    DataSourceAPIModel.objects.create(
        id=18,
        name="无关数据源",
        rest_api="other/query",
    )

    assert collect_named_option_datasource_ids({17}) == {9, 42}


def test_export_closure_fails_when_a_filter_path_matches_more_than_one_source():
    from apps.operation_analysis.constants.import_export import ObjectType, ScopeType
    from apps.operation_analysis.models.models import Dashboard
    from apps.operation_analysis.schemas.import_export_schema import ImportExportValidationError
    from apps.operation_analysis.services.import_export.export_service import ExportService

    DataSourceAPIModel.objects.create(id=42, name="机房列表 A", rest_api="cmdb/get_room_list")
    DataSourceAPIModel.objects.create(id=43, name="机房列表 B", rest_api="cmdb/get_room_list", is_build_in=True)
    dashboard = Dashboard.objects.create(
        name="歧义导出",
        groups=[1],
        created_by="s",
        filters=[
            {
                "key": "room",
                "inputConfig": {
                    "control": "select",
                    "optionsSource": {
                        "type": "dynamic",
                        "sourceRef": {"type": "rest_api", "value": "cmdb/get_room_list"},
                    },
                },
            }
        ],
        view_sets=[],
    )

    with pytest.raises(ImportExportValidationError) as raised:
        ExportService.collect_export_dependencies(
            ScopeType.CANVAS.value,
            ObjectType.DASHBOARD.value,
            [dashboard.id],
        )

    assert raised.value.code == "OA_EXPORT_OPTION_SOURCE_AMBIGUOUS"
    assert "cmdb/get_room_list" not in raised.value.message


def test_collect_named_option_ids_does_not_guess_one_builtin_among_same_address():
    DataSourceAPIModel.objects.create(
        id=17,
        name="主数据源",
        rest_api="cmdb/get_room3d_layout",
        params=ROOM3D_SWITCH_PARAMS,
    )
    DataSourceAPIModel.objects.create(
        id=42,
        name="机房列表 A",
        rest_api="cmdb/get_room_list",
    )
    DataSourceAPIModel.objects.create(
        id=43,
        name="机房列表 B",
        rest_api="cmdb/get_room_list",
    )
    assert collect_named_option_datasource_ids({17}) == set()

    DataSourceAPIModel.objects.filter(id=43).update(is_build_in=True)
    assert collect_named_option_datasource_ids({17}) == set()


def test_collect_named_option_ids_follows_builtin_key_when_rest_api_collides():
    DataSourceAPIModel.objects.create(
        id=17,
        name="主数据源",
        rest_api="cmdb/get_room3d_layout",
        params=[
            {
                "name": "server_room_id",
                "inputConfig": {
                    "control": "select",
                    "optionsSource": {
                        "type": "dynamic",
                        "sourceRef": {"type": "rest_api", "value": "CMDB 机房列表::cmdb/get_room_list"},
                    },
                },
            }
        ],
    )
    DataSourceAPIModel.objects.create(
        id=42,
        name="按模型的同路径",
        rest_api="cmdb/get_room_list",
        is_build_in=True,
        build_in_key="另一条机房列表::cmdb/get_room_list",
    )
    DataSourceAPIModel.objects.create(
        id=43,
        name="机房列表",
        rest_api="cmdb/get_room_list",
        is_build_in=True,
        build_in_key="CMDB 机房列表::cmdb/get_room_list",
    )
    assert collect_named_option_datasource_ids({17}) == {43}


def test_expand_widget_manifest_appends_named_option_identity():
    DataSourceAPIModel.objects.create(
        id=17,
        name="CMDB 3D机房布局",
        rest_api="cmdb/get_room3d_layout",
        params=ROOM3D_SWITCH_PARAMS,
    )
    DataSourceAPIModel.objects.create(
        id=42,
        name="CMDB 机房列表",
        rest_api="cmdb/get_room_list",
    )
    manifest = [
        {
            "widget_id": "room-1",
            "widget_type": "room3D",
            "datasource_id": 17,
        }
    ]
    assert expand_widget_manifest_with_named_option_datasources(manifest) == [
        {
            "widget_id": "room-1",
            "widget_type": "room3D",
            "datasource_id": 17,
        },
        {
            "widget_id": "room-1",
            "widget_type": "room3D",
            "datasource_id": 42,
        },
    ]


def test_collect_named_option_ids_from_canvas_filters():
    DataSourceAPIModel.objects.create(
        id=42,
        name="监控主机列表",
        rest_api="monitor/get_host_instance_list",
        is_build_in=True,
    )
    DataSourceAPIModel.objects.create(
        id=9,
        name="命名空间选项",
        rest_api="system/namespaces",
    )

    from apps.operation_analysis.services.named_option_datasources import collect_named_option_datasource_ids_from_filters

    filters = [
        {
            "id": "instance_ids__string",
            "key": "instance_ids",
            "type": "string",
            "inputConfig": {
                "control": "select",
                "multiple": True,
                "optionsSource": {
                    "type": "dynamic",
                    "sourceRef": {"type": "rest_api", "value": "monitor/get_host_instance_list"},
                    "valueField": "instance_id",
                    "labelField": "display_name",
                },
            },
        },
        {
            "id": "ns__string",
            "key": "namespace",
            "type": "string",
            "inputConfig": {
                "control": "select",
                "optionsSource": {
                    "type": "dynamic",
                    "sourceId": 9,
                    "valueField": "id",
                    "labelField": "name",
                },
            },
        },
    ]

    assert collect_named_option_datasource_ids_from_filters(filters) == {9, 42}


def test_expand_widget_manifest_appends_filter_option_identity():
    DataSourceAPIModel.objects.create(
        id=42,
        name="监控主机列表",
        rest_api="monitor/get_host_instance_list",
        is_build_in=True,
    )
    manifest = [
        {
            "widget_id": "cpu-1",
            "widget_type": "line",
            "datasource_id": 17,
        }
    ]
    filters = [
        {
            "id": "instance_ids__string",
            "inputConfig": {
                "control": "select",
                "optionsSource": {
                    "type": "dynamic",
                    "sourceRef": {"type": "rest_api", "value": "monitor/get_host_instance_list"},
                    "valueField": "instance_id",
                    "labelField": "display_name",
                },
            },
        }
    ]
    expanded = expand_widget_manifest_with_named_option_datasources(manifest, filters=filters)
    assert expanded[-1] == {
        "widget_id": "__unified_filter__",
        "widget_type": "unifiedFilter",
        "datasource_id": 42,
    }


def _condition_fields(**fields):
    return {
        "name": "filters",
        "type": "conditionFilter",
        "inputConfig": {
            "control": "conditionFilter",
            "fields": {"kind": "dynamic", "valueField": "name", "labelField": "label", **fields},
        },
    }


def test_condition_field_source_id_is_collected_beside_chart_and_option_sources():
    DataSourceAPIModel.objects.create(id=17, name="主图表", rest_api="demo/chart", params=[_condition_fields(sourceId=9)])
    DataSourceAPIModel.objects.create(id=9, name="条件字段", rest_api="demo/fields")
    DataSourceAPIModel.objects.create(id=8, name="普通选项", rest_api="demo/options")
    DataSourceAPIModel.objects.create(
        id=18,
        name="带普通选项的主源",
        rest_api="demo/chart-options",
        params=[
            {
                "name": "site",
                "inputConfig": {
                    "control": "select",
                    "optionsSource": {"type": "dynamic", "sourceId": 8, "valueField": "id", "labelField": "name"},
                },
            }
        ],
    )

    assert collect_named_option_datasource_ids({17, 18}) == {8, 9}
    assert 99 not in collect_named_option_datasource_ids({17})


def test_condition_field_source_ref_follows_unique_rest_api_or_builtin_key_and_does_not_guess():
    DataSourceAPIModel.objects.create(
        id=17,
        name="主图表",
        rest_api="demo/chart",
        params=[_condition_fields(sourceRef={"type": "rest_api", "value": "monitor/list_metric_dimensions"})],
    )
    DataSourceAPIModel.objects.create(
        id=21,
        name="监控指标维度",
        rest_api="monitor/list_metric_dimensions",
        is_build_in=True,
        build_in_key="监控指标维度::monitor/list_metric_dimensions",
    )
    assert collect_named_option_datasource_ids({17}) == {21}

    DataSourceAPIModel.objects.create(id=22, name="同地址另一条", rest_api="monitor/list_metric_dimensions")
    assert collect_named_option_datasource_ids({17}) == set()

    DataSourceAPIModel.objects.filter(id=17).update(
        params=[
            _condition_fields(
                sourceRef={"type": "rest_api", "value": "监控指标维度::monitor/list_metric_dimensions"},
            )
        ],
    )
    assert collect_named_option_datasource_ids({17}) == {21}

    DataSourceAPIModel.objects.filter(id=17).update(
        params=[_condition_fields(builtinKey="监控指标维度::monitor/list_metric_dimensions")],
    )
    assert collect_named_option_datasource_ids({17}) == {21}


def test_canvas_filter_and_widget_condition_sources_are_declared_dependencies():
    from apps.operation_analysis.services.named_option_datasources import collect_named_option_datasource_ids_from_filters
    from apps.operation_analysis.views.share_view import _canvas_data_source_ids

    DataSourceAPIModel.objects.create(id=17, name="主图表", rest_api="demo/chart", params=[])
    DataSourceAPIModel.objects.create(id=9, name="全局条件字段", rest_api="demo/global-fields")
    DataSourceAPIModel.objects.create(id=31, name="组件条件字段", rest_api="demo/widget-fields")
    filters = [
        {
            "id": "row_filter__conditionFilter",
            "key": "row_filter",
            "name": "条件",
            "type": "conditionFilter",
            "order": 1,
            "enabled": True,
            "inputConfig": _condition_fields(
                sourceId=9,
                queryParams={"metric_id": {"ref": "metric_id"}},
            )["inputConfig"],
        },
        {
            "id": "static_fields__conditionFilter",
            "key": "static_fields",
            "name": "静态",
            "type": "conditionFilter",
            "order": 2,
            "enabled": False,
            "inputConfig": {
                "control": "conditionFilter",
                "fields": {"kind": "static", "items": [], "sourceId": 99},
            },
        },
        {
            "id": "list_fields__conditionFilter",
            "key": "list_fields",
            "name": "错误数组",
            "type": "conditionFilter",
            "order": 3,
            "enabled": True,
            "inputConfig": {
                "control": "conditionFilter",
                "fields": [{"kind": "dynamic", "sourceId": 77}],
            },
        },
    ]
    DataSourceAPIModel.objects.create(id=77, name="不该因数组形状放行", rest_api="demo/not-a-field-list")
    DataSourceAPIModel.objects.create(id=99, name="不该因静态放行", rest_api="demo/static-not-allowed")
    assert collect_named_option_datasource_ids_from_filters(filters) == {9}

    class _Canvas:
        view_sets = [
            {
                "children": [
                    {
                        "valueConfig": {
                            "dataSource": 17,
                            "dataSourceParams": [
                                _condition_fields(
                                    sourceId=31,
                                    queryParams={"dim_id": {"ref": "dim"}},
                                )
                            ],
                        }
                    }
                ]
            }
        ]

    _Canvas.filters = filters
    found = _canvas_data_source_ids(_Canvas())
    assert {17, 9, 31} <= found
    assert 77 not in found
    assert 99 not in found


def test_declared_query_keys_follow_the_resolved_condition_or_option_source():
    from apps.operation_analysis.services.named_option_datasources import declared_option_query_keys

    DataSourceAPIModel.objects.create(id=9, name="条件字段", rest_api="demo/fields")
    DataSourceAPIModel.objects.create(id=8, name="普通选项", rest_api="demo/options")
    DataSourceAPIModel.objects.create(id=21, name="监控指标维度", rest_api="monitor/list_metric_dimensions")
    DataSourceAPIModel.objects.create(id=22, name="同地址另一条", rest_api="monitor/list_metric_dimensions")
    items = [
        _condition_fields(sourceId=9, queryParams={"metric_id": {"ref": "metric_id"}}),
        {
            "name": "site",
            "inputConfig": {
                "control": "select",
                "optionsSource": {
                    "type": "dynamic",
                    "sourceId": 8,
                    "valueField": "id",
                    "labelField": "name",
                    "queryParams": {"site_id": {"ref": "site"}},
                },
            },
        },
        _condition_fields(
            sourceRef={"type": "rest_api", "value": "monitor/list_metric_dimensions"},
            queryParams={"metric_id": {"ref": "metric_id"}},
        ),
    ]

    keys = declared_option_query_keys(items)
    assert keys[9] == {"metric_id"}
    assert keys[8] == {"site_id"}
    assert 21 not in keys
    assert 22 not in keys
