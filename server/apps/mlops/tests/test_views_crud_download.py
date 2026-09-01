"""MLOps 六算法 Dataset CRUD 与训练数据下载：无文件 404，有 metadata 返回 JSON。"""
import importlib

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.mlops.constants import DatasetReleaseStatus

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

factory = APIRequestFactory()

ALGOS = [
    ("anomaly_detection", "AnomalyDetection", "anomaly_detection", "AnomalyDetection"),
    ("classification", "Classification", "classification", "Classification"),
    ("log_clustering", "LogClustering", "log_clustering", "LogClustering"),
    ("timeseries_predict", "TimeseriesPredict", "timeseries_predict", "TimeSeriesPredict"),
    ("image_classification", "ImageClassification", "image_classification", "ImageClassification"),
    ("object_detection", "ObjectDetection", "object_detection", "ObjectDetection"),
]
ALGO_IDS = [a[0] for a in ALGOS]


def _view_module(suffix):
    return importlib.import_module(f"apps.mlops.views.{suffix}")


def _model(model_module, basename, kind):
    mod = importlib.import_module(f"apps.mlops.models.{model_module}")
    return getattr(mod, f"{basename}{kind}")


@pytest.fixture
def superuser():
    return UserFactory(username="mlops-crud", domain="domain.com", roles=[], is_superuser=True)


def _call(view, request, superuser, **kwargs):
    force_authenticate(request, user=superuser)
    request.COOKIES["current_team"] = "1"
    return view(request, **kwargs)


@pytest.mark.parametrize("suffix,prefix,model_module,basename", ALGOS, ids=ALGO_IDS)
def test_dataset_list_create_retrieve_destroy(superuser, suffix, prefix, model_module, basename):
    Dataset = _model(model_module, basename, "Dataset")
    ds = Dataset.objects.create(name="ds-list", description="", team=[1])
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}DatasetViewSet")

    listed = _call(vs.as_view({"get": "list"}), factory.get("/"), superuser)
    assert listed.status_code == status.HTTP_200_OK

    retrieved = _call(vs.as_view({"get": "retrieve"}), factory.get("/x/"), superuser, pk=ds.id)
    assert retrieved.status_code == status.HTTP_200_OK
    assert retrieved.data["id"] == ds.id
    assert retrieved.data["name"] == "ds-list"

    created = _call(
        vs.as_view({"post": "create"}),
        factory.post("/", {"name": f"ds-new-{suffix}", "description": "", "team": [1]}, format="json"),
        superuser,
    )
    assert created.status_code == status.HTTP_201_CREATED
    assert Dataset.objects.filter(name=f"ds-new-{suffix}").exists()

    updated = _call(
        vs.as_view({"put": "update"}),
        factory.put("/x/", {"name": "ds-renamed", "description": "d", "team": [1]}, format="json"),
        superuser,
        pk=ds.id,
    )
    assert updated.status_code == status.HTTP_200_OK
    ds.refresh_from_db()
    assert ds.name == "ds-renamed"

    deleted = _call(vs.as_view({"delete": "destroy"}), factory.delete("/x/"), superuser, pk=ds.id)
    # as_view 直调不经 CustomRenderer，DRF destroy 成功仍是 204
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert not Dataset.objects.filter(id=ds.id).exists()


@pytest.mark.parametrize(
    "suffix,model_module,basename",
    [
        ("image_classification", "image_classification", "ImageClassification"),
    ],
    ids=["image_classification"],
)
def test_train_data_download_missing_file_and_metadata(superuser, suffix, model_module, basename):
    Dataset = _model(model_module, basename, "Dataset")
    TrainData = _model(model_module, basename, "TrainData")
    ds = Dataset.objects.create(name="ds-dl", description="", team=[1])
    td = TrainData.objects.create(name="td", dataset=ds, metadata={})
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}TrainDataViewSet")
    missing = _call(vs.as_view({"get": "download"}), factory.get("/x/download/"), superuser, pk=td.id)
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert missing.data == {"error": "Training data file was not found"}
    meta_missing = _call(vs.as_view({"get": "download_metadata"}), factory.get("/x/meta/"), superuser, pk=td.id)
    assert meta_missing.status_code == status.HTTP_404_NOT_FOUND

    td.metadata = {"labels": ["cat"]}
    td.save()
    meta_ok = _call(vs.as_view({"get": "download_metadata"}), factory.get("/x/meta/"), superuser, pk=td.id)
    assert meta_ok.status_code == status.HTTP_200_OK
    assert meta_ok.data["labels"] == ["cat"]


def test_object_detection_train_data_download_missing_file(superuser):
    Dataset = _model("object_detection", "ObjectDetection", "Dataset")
    TrainData = _model("object_detection", "ObjectDetection", "TrainData")
    ds = Dataset.objects.create(name="ds-od-dl", description="", team=[1])
    td = TrainData.objects.create(name="td", dataset=ds, metadata={})
    mod = _view_module("object_detection")
    vs = getattr(mod, "ObjectDetectionTrainDataViewSet")
    missing = _call(vs.as_view({"get": "download"}), factory.get("/x/download/"), superuser, pk=td.id)
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert missing.data == {"error": "Training data file was not found"}


@pytest.mark.parametrize(
    "suffix,model_module,basename",
    [
        ("image_classification", "image_classification", "ImageClassification"),
        ("object_detection", "object_detection", "ObjectDetection"),
    ],
    ids=["image_classification", "object_detection"],
)
def test_release_download_missing_file(superuser, suffix, model_module, basename):
    Dataset = _model(model_module, basename, "Dataset")
    Release = _model(model_module, basename, "DatasetRelease")
    ds = Dataset.objects.create(name="ds-rel", description="", team=[1])
    rel = Release.objects.create(
        name="r",
        description="",
        dataset=ds,
        version="v1",
        dataset_file="",
        status=DatasetReleaseStatus.PUBLISHED,
        metadata={},
        file_size=0,
    )
    mod = _view_module(suffix)
    vs = getattr(mod, f"{basename}DatasetReleaseViewSet")
    resp = _call(vs.as_view({"get": "download"}), factory.get("/x/download/"), superuser, pk=rel.id)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
