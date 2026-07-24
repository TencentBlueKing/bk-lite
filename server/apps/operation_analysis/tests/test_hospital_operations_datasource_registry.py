import json
from pathlib import Path


SOURCE_FILE = Path(__file__).parents[1] / "support-files" / "source_api.json"


def sources_by_api():
    rows = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    return {row["rest_api"]: row for row in rows}


def test_network_device_resource_top_registry_contract():
    source = sources_by_api()["monitor/get_network_device_resource_top"]
    assert source["chart_type"] == ["topN", "table"]
    assert [(x["name"], x["value"]) for x in source["params"]] == [
        ("metric_type", "cpu"), ("limit", 10)
    ]
    metric = source["params"][0]
    assert metric["inputConfig"]["componentSwitch"] is True
    assert [x["value"] for x in metric["inputConfig"]["optionsSource"]["staticItems"]] == [
        "cpu", "memory", "traffic"
    ]
    assert [x["key"] for x in source["field_schema"]] == [
        "rank", "display_name", "value", "unit", "instance_id",
        "device_type", "sampled_at",
    ]


def test_alert_source_distribution_registry_contract():
    source = sources_by_api()["alert/get_alert_source_distribution"]
    assert source["chart_type"] == ["pie"]
    assert source["params"] == []
    assert [x["key"] for x in source["field_schema"]] == ["name", "value"]


def test_excluded_alert_datasources_are_unchanged():
    sources = sources_by_api()
    assert sources["alert/get_alert_trend_data"]["chart_type"] == ["single"]
    assert "alert/get_active_alert_top" not in sources
