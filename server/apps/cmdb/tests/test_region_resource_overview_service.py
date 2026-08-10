import json

import pytest

from apps.cmdb.services.region_resource_overview import (
    build_region_resource_items,
    extract_region_options,
)


@pytest.mark.unit
def test_extract_region_options_supports_list_and_legacy_json_attrs():
    tag_attr = {
        "attr_id": "tag", "attr_type": "tag",
        "option": {"options": [
            {"key": "region", "value": " 本部 "},
            {"key": "env", "value": "prod"},
            {"key": "Region", "value": "ignored"},
        ]},
    }
    models = [
        {"model_id": "host", "classification_id": "host", "attrs": [tag_attr]},
        {"model_id": "mysql", "classification_id": "database", "attrs": json.dumps([
            {"attr_id": "tag", "attr_type": "tag", "option": {"options": [
                {"key": "region", "value": "东区"},
                {"key": "region", "value": "本部"},
            ]}},
        ], ensure_ascii=False)},
    ]
    assert extract_region_options(models, {"host", "database"}) == [
        {"label": "东区", "value": "东区"},
        {"label": "本部", "value": "本部"},
    ]


@pytest.mark.unit
def test_extract_region_options_ignores_hidden_classification_and_malformed_data():
    models = [
        {"classification_id": "hidden", "attrs": [{"attr_id": "tag", "attr_type": "tag", "option": {"options": [{"key": "region", "value": "秘密"}]}}]},
        {"classification_id": "host", "attrs": "not-json"},
        {"classification_id": "host", "attrs": [{"attr_id": "tag", "attr_type": "tag", "option": {"options": {}}}]},
        {"classification_id": "host", "attrs": [{"attr_id": "tag", "attr_type": "tag", "option": {"options": [None, {}, {"key": "region", "value": "  "}]}}]},
    ]
    assert extract_region_options(models, {"host"}) == []


@pytest.mark.unit
def test_build_region_resource_items_accumulates_filters_and_sorts():
    models = [
        {"model_id": "mysql", "classification_id": "database"},
        {"model_id": "postgres", "classification_id": "database"},
        {"model_id": "linux", "classification_id": "host"},
        {"model_id": "nginx", "classification_id": "middleware"},
        {"model_id": "zero", "classification_id": "middleware"},
        {"model_id": "missing-class", "classification_id": "missing"},
        {"model_id": "unclassified"},
    ]
    classifications = [
        {"classification_id": "database", "classification_name": "数据库"},
        {"classification_id": "host", "classification_name": "主机"},
        {"classification_id": "middleware", "classification_name": "中间件"},
    ]
    model_counts = {"mysql": 150, "postgres": 150, "linux": 200, "nginx": 200, "zero": 0}
    assert build_region_resource_items(models, classifications, model_counts) == [
        {"label": "数据库", "value": 300},
        {"label": "中间件", "value": 200},
        {"label": "主机", "value": 200},
    ]


@pytest.mark.unit
def test_build_region_resource_items_returns_empty_for_no_positive_visible_counts():
    assert build_region_resource_items(
        [{"model_id": "host", "classification_id": "host"}],
        [{"classification_id": "host", "classification_name": "主机"}],
        {"host": 0},
    ) == []
