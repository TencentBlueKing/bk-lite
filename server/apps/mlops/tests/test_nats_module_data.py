import pydantic.root_model  # noqa

import pytest

from apps.mlops import nats_api
from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionTrainData,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_get_mlops_module_data_unknown_module():
    result = nats_api.get_mlops_module_data("nope", "x", 1, 10, 1)
    assert result["result"] is False
    assert "未知模块" in result["message"]


def test_get_mlops_module_data_unknown_child():
    result = nats_api.get_mlops_module_data("dataset", "bad_child", 1, 10, 1)
    assert result["result"] is False
    assert "未知子模块" in result["message"]


def test_get_mlops_module_data_root_filters_by_group():
    AnomalyDetectionDataset.objects.create(name="d1", description="", team=[1])
    AnomalyDetectionDataset.objects.create(name="d2", description="", team=[2])
    result = nats_api.get_mlops_module_data("dataset", "anomaly_detection_dataset", 1, 10, 1)
    assert result["result"] is True
    assert result["count"] == 1
    assert result["items"][0]["name"] == "d1"


def test_get_mlops_module_data_pagination():
    for i in range(5):
        AnomalyDetectionDataset.objects.create(name=f"d{i}", description="", team=[1])
    page1 = nats_api.get_mlops_module_data("dataset", "anomaly_detection_dataset", 1, 2, 1)
    page2 = nats_api.get_mlops_module_data("dataset", "anomaly_detection_dataset", 2, 2, 1)
    assert page1["count"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    # disjoint pages
    ids1 = {it["id"] for it in page1["items"]}
    ids2 = {it["id"] for it in page2["items"]}
    assert ids1.isdisjoint(ids2)


def test_get_mlops_module_data_page_size_clamped_to_max(monkeypatch):
    monkeypatch.setattr(nats_api, "MAX_PAGE_SIZE", 3)
    for i in range(5):
        AnomalyDetectionDataset.objects.create(name=f"d{i}", description="", team=[1])
    result = nats_api.get_mlops_module_data("dataset", "anomaly_detection_dataset", 1, 999, 1)
    assert result["count"] == 5
    assert len(result["items"]) == 3


def test_get_mlops_module_data_page_size_floor_one():
    AnomalyDetectionDataset.objects.create(name="d", description="", team=[1])
    result = nats_api.get_mlops_module_data("dataset", "anomaly_detection_dataset", 1, 0, 1)
    # page_size floored to 1
    assert len(result["items"]) == 1


def test_get_mlops_module_data_inherited_child_uses_dataset_team():
    ds1 = AnomalyDetectionDataset.objects.create(name="parent1", description="", team=[1])
    ds2 = AnomalyDetectionDataset.objects.create(name="parent2", description="", team=[2])
    AnomalyDetectionTrainData.objects.create(name="t-in", dataset=ds1, is_train_data=True)
    AnomalyDetectionTrainData.objects.create(name="t-out", dataset=ds2, is_train_data=True)
    result = nats_api.get_mlops_module_data("dataset", "anomaly_detection_train_data", 1, 10, 1)
    assert result["count"] == 1
    assert result["items"][0]["name"] == "t-in"


def test_get_mlops_module_data_empty_result():
    result = nats_api.get_mlops_module_data("dataset", "anomaly_detection_dataset", 1, 10, 999)
    assert result["result"] is True
    assert result["count"] == 0
    assert result["items"] == []
