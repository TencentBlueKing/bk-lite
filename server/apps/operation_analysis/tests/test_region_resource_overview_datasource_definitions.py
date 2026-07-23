import json
from pathlib import Path


SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _sources_by_api():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    return {item["rest_api"]: item for item in entries}


def test_cmdb_region_options_datasource_contract():
    source = _sources_by_api()["cmdb/get_region_options"]
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} == {"label", "value"}
    assert {field["value_type"] for field in source["field_schema"]} == {"string"}


def test_cmdb_region_resource_overview_datasource_contract():
    source = _sources_by_api()["cmdb/get_region_resource_overview"]
    assert source["chart_type"] == ["multiValue"]
    param = next(item for item in source["params"] if item["name"] == "region")
    assert param["type"] == "string"
    assert param["required"] is True
    assert param["inputConfig"]["control"] == "select"
    assert param["inputConfig"]["optionsSource"] == {
        "type": "dynamic",
        "sourceRef": {"type": "rest_api", "value": "cmdb/get_region_options"},
        "valueField": "value",
        "labelField": "label",
    }
    field_types = {field["key"]: field["value_type"] for field in source["field_schema"]}
    assert field_types == {"label": "string", "value": "number"}
