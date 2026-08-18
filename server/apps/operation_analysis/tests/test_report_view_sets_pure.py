import pytest

from apps.operation_analysis.services.report_view_sets import normalize_report_view_sets

pytestmark = pytest.mark.unit


def _section(section_id="section-1", chart_type="table"):
    return {
        "id": section_id,
        "valueConfig": {
            "name": "资产列表",
            "description": "当前资产状态",
            "chartType": chart_type,
            "dataSource": 7,
        },
    }


def test_empty_legacy_report_is_normalized_to_version_one():
    assert normalize_report_view_sets({}) == {
        "schema_version": 1,
        "filters": [],
        "sections": [],
    }


@pytest.mark.parametrize("chart_type", ["table", "eventTable"])
def test_registered_report_component_types_are_preserved(chart_type):
    section = _section(chart_type=chart_type)

    assert normalize_report_view_sets(
        {
            "schema_version": 1,
            "time_range": 60,
            "filters": [
                {
                    "id": "billing_period__dateRange",
                    "key": "billing_period",
                    "name": "计费日期",
                    "type": "dateRange",
                    "defaultValue": None,
                    "order": 0,
                    "enabled": True,
                }
            ],
            "sections": [section],
        }
    ) == {
        "schema_version": 1,
        "filters": [
            {
                "id": "billing_period__dateRange",
                "key": "billing_period",
                "name": "计费日期",
                "type": "dateRange",
                "defaultValue": None,
                "order": 0,
                "enabled": True,
            }
        ],
        "sections": [section],
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "view_sets 必须是 JSON 对象"),
        ({"schema_version": 2, "sections": []}, "schema_version 仅支持 1"),
        ({"schema_version": 1, "filters": {}, "sections": []}, "filters 必须是数组"),
        (
            {"schema_version": 1, "filters": [{"id": "bad"}], "sections": []},
            "filters[0].key 必须是非空字符串",
        ),
        (
            {"schema_version": 1, "sections": [_section(chart_type="line")]},
            "sections[0].valueConfig.chartType 不支持报表组件类型 'line'",
        ),
        (
            {"schema_version": 1, "sections": [_section(), _section()]},
            "sections[1].id 与其它组件重复",
        ),
        (
            {"schema_version": 1, "sections": [{"id": "missing-source", "valueConfig": {"chartType": "table"}}]},
            "sections[0].valueConfig.dataSource 必须是正整数数据源 ID",
        ),
        (
            {
                "schema_version": 1,
                "sections": [
                    {
                        "id": "bad-params",
                        "valueConfig": {"chartType": "eventTable", "dataSource": 7, "dataSourceParams": {}},
                    }
                ],
            },
            "sections[0].valueConfig.dataSourceParams 必须是数组",
        ),
    ],
)
def test_invalid_report_view_sets_are_rejected_with_paths(value, message):
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        normalize_report_view_sets(value)


def test_portable_datasource_key_is_accepted_before_import_rewrite():
    section = _section()
    section["valueConfig"]["dataSource"] = "report-source::api/table"

    normalized = normalize_report_view_sets(
        {"schema_version": 1, "sections": [section]},
        allow_portable_datasource_ref=True,
    )

    assert normalized["sections"][0]["valueConfig"]["dataSource"] == "report-source::api/table"


def test_portable_datasource_key_is_rejected_for_storage():
    section = _section()
    section["valueConfig"]["dataSource"] = "report-source::api/table"

    with pytest.raises(ValueError, match="sections\\[0\\].valueConfig.dataSource"):
        normalize_report_view_sets({"schema_version": 1, "sections": [section]})
