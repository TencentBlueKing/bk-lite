import json
from pathlib import Path


SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def test_host_resource_top_data_source_supports_topn_table_and_metric_switch():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    source = next(item for item in entries if item.get("rest_api") == "monitor/get_host_resource_top")

    assert source["chart_type"] == ["topN", "table"]
    param = next(item for item in source["params"] if item["name"] == "metric_type")
    assert param["value"] == "cpu"
    assert param["inputConfig"]["componentSwitch"] is True
    assert {item["value"] for item in param["inputConfig"]["optionsSource"]["staticItems"]} == {
        "cpu",
        "memory",
        "disk",
    }
    assert {field["key"] for field in source["field_schema"]} >= {
        "rank",
        "display_name",
        "usage_percent",
        "sampled_at",
    }
