import json
from pathlib import Path


SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def test_cmdb_classification_options_datasource_definition():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    source = next(item for item in entries if item.get("rest_api") == "cmdb/get_model_classification_options")
    assert source["chart_type"] == []
    assert {field["key"] for field in source["field_schema"]} >= {"classification_id", "classification_name"}


def test_cmdb_classification_model_counts_datasource_definition():
    entries = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    source = next(item for item in entries if item.get("rest_api") == "cmdb/get_classification_model_instance_counts")
    assert source["chart_type"] == ["multiValue"]
    param = next(item for item in source["params"] if item["name"] == "classification_id")
    assert param["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "cmdb/get_model_classification_options"
    assert param["inputConfig"]["optionsSource"]["valueField"] == "classification_id"
    assert param["inputConfig"]["optionsSource"]["labelField"] == "classification_name"
    assert {field["key"] for field in source["field_schema"]} == {"label", "value"}
