import pydantic.root_model  # noqa

import pytest

from apps.mlops import nats_api

pytestmark = pytest.mark.unit


def test_get_module_registry_merges_root_and_inherited():
    registry = nats_api._get_module_registry()
    # dataset has root datasets + inherited train_data/dataset_release
    assert "classification_dataset" in registry["dataset"]
    assert "classification_train_data" in registry["dataset"]
    assert "classification_dataset_release" in registry["dataset"]
    # serving has no inherited entries
    assert "classification_serving" in registry["serving"]
    # train_job inherited map is empty
    assert "classification_train_job" in registry["train_job"]


def test_get_mlops_module_list_shape_and_display_names():
    result = nats_api.get_mlops_module_list()
    by_name = {m["name"]: m for m in result}
    assert set(by_name) == {"dataset", "train_job", "serving"}
    assert by_name["dataset"]["display_name"] == "数据集"
    assert by_name["train_job"]["display_name"] == "训练任务"
    assert by_name["serving"]["display_name"] == "能力发布"


def test_get_mlops_module_list_children_use_display_names():
    result = nats_api.get_mlops_module_list()
    dataset_children = {c["name"]: c["display_name"] for m in result if m["name"] == "dataset" for c in m["children"]}
    assert dataset_children["anomaly_detection_dataset"] == "异常检测数据集"
    assert dataset_children["timeseries_predict_dataset_release"] == "时间序列预测数据集发布版本"


def test_get_mlops_module_list_child_falls_back_to_name_when_no_display(monkeypatch):
    # inject a child without a CHILD_DISPLAY_NAMES entry; display_name should equal the name
    patched = {
        "dataset": {"weird_child": (object, "team")},
        "train_job": {},
        "serving": {},
    }
    monkeypatch.setattr(nats_api, "_get_module_registry", lambda: patched)
    result = nats_api.get_mlops_module_list()
    dataset = next(m for m in result if m["name"] == "dataset")
    child = dataset["children"][0]
    assert child["name"] == "weird_child"
    assert child["display_name"] == "weird_child"
