import pydantic.root_model  # noqa
import pytest

from apps.mlops import nats_api
from apps.mlops.utils.i18n import mlops_message_for_locale

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


def test_get_mlops_module_list_defaults_to_zh():
    result = nats_api.get_mlops_module_list()
    by_name = {m["name"]: m for m in result}
    assert set(by_name) == {"dataset", "train_job", "serving"}
    assert by_name["dataset"]["display_name"] == mlops_message_for_locale("zh-Hans", "module.dataset")
    assert by_name["train_job"]["display_name"] == mlops_message_for_locale("zh-Hans", "module.train_job")
    assert by_name["serving"]["display_name"] == mlops_message_for_locale("zh-Hans", "module.serving")


def test_get_mlops_module_list_uses_english_locale():
    result = nats_api.get_mlops_module_list(locale="en")
    by_name = {m["name"]: m for m in result}
    assert by_name["dataset"]["display_name"] == "Dataset"
    assert by_name["train_job"]["display_name"] == "Training Job"
    assert by_name["serving"]["display_name"] == "Serving"


def test_get_mlops_module_list_children_use_display_names_zh():
    result = nats_api.get_mlops_module_list(locale="zh-Hans")
    dataset_children = {c["name"]: c["display_name"] for m in result if m["name"] == "dataset" for c in m["children"]}
    assert dataset_children["anomaly_detection_dataset"] == "异常检测数据集"
    assert dataset_children["timeseries_predict_dataset_release"] == "时间序列预测数据集发布版本"


def test_get_mlops_module_list_children_use_display_names_en():
    result = nats_api.get_mlops_module_list(locale="en")
    dataset_children = {c["name"]: c["display_name"] for m in result if m["name"] == "dataset" for c in m["children"]}
    assert dataset_children["anomaly_detection_dataset"] == "Anomaly Detection Dataset"
    assert dataset_children["timeseries_predict_dataset_release"] == "Time Series Prediction Dataset Release"


def test_get_mlops_module_list_child_falls_back_to_name_when_no_display(monkeypatch):
    # inject a child without a CHILD_DISPLAY_NAME_KEYS entry; display_name should equal the name
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


def test_get_mlops_module_list_reads_locale_from_actor_context():
    result = nats_api.get_mlops_module_list(actor_context={"locale": "en"})
    by_name = {m["name"]: m for m in result}
    assert by_name["dataset"]["display_name"] == "Dataset"
