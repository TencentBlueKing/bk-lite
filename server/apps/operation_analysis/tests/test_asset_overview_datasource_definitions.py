import json
from pathlib import Path

SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _sources():
    return {item["rest_api"]: item for item in json.loads(SOURCE_API.read_text(encoding="utf-8"))}


def test_cloud_region_options_have_no_chart_and_no_params():
    source = _sources()["cmdb/get_cloud_region_options"]
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} >= {"id", "name"}


def test_model_association_options_fix_host_model():
    source = _sources()["cmdb/get_model_association_options"]
    assert source["chart_type"] == []
    assert source["params"] == [
        {
            "name": "model_id",
            "type": "string",
            "value": "host",
            "alias_name": "模型",
            "filterType": "fixed",
            "required": True,
        }
    ]
    assert {field["key"] for field in source["field_schema"]} >= {"model_asst_id", "label"}


def test_classification_instance_counts_select_many_classifications():
    source = _sources()["cmdb/get_classification_instance_counts"]
    assert "multiValue" in source["chart_type"]
    param = next(item for item in source["params"] if item["name"] == "classification_ids")
    assert param["required"] is True
    assert param["inputConfig"]["multiple"] is True
    options = param["inputConfig"]["optionsSource"]
    assert options["sourceRef"]["value"] == "cmdb/get_model_classification_options"
    assert options["valueField"] == "classification_id"
    assert options["labelField"] == "classification_name"


def test_cloud_region_resource_counts_bind_option_sources():
    source = _sources()["cmdb/get_cloud_region_resource_counts"]
    params = {item["name"]: item for item in source["params"]}
    assert params["cloud_region_ids"]["inputConfig"]["multiple"] is True
    assert params["cloud_region_ids"]["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "cmdb/get_cloud_region_options"
    assert params["model_asst_ids"]["inputConfig"]["multiple"] is True
    assert params["model_asst_ids"]["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "cmdb/get_model_association_options"
    assert params["supplement_tag_key"].get("required") is not True
    assert params["supplement_tag_value"].get("required") is not True
    assert {field["key"] for field in source["field_schema"]} >= {"model_id", "model_name", "value"}
