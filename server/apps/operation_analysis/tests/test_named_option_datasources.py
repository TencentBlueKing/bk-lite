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


def test_collect_named_option_ids_skips_ambiguous_rest_api_unless_unique_builtin():
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
