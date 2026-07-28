"""
测试 mlops 六个算法 predict 端点的批量上界校验（Issue #3495）。

验证策略：当 len(data/texts/images) > MAX_BATCH_SIZE 时，
视图应返回 HTTP 413，而不是转发给下游推理服务。
revert 修复代码后，测试应该失败（requests.post 会被调用而非被拒绝）。
"""

import pytest
from rest_framework import status

from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob, AnomalyDetectionServing
from apps.mlops.models.classification import ClassificationTrainJob, ClassificationServing
from apps.mlops.models.image_classification import ImageClassificationTrainJob, ImageClassificationServing
from apps.mlops.models.log_clustering import LogClusteringTrainJob, LogClusteringServing
from apps.mlops.models.timeseries_predict import TimeSeriesPredictTrainJob, TimeSeriesPredictServing
from apps.mlops.models.object_detection import ObjectDetectionTrainJob, ObjectDetectionServing
from apps.mlops.constants import TrainJobStatus

from .conftest import create_train_job


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONTAINER_INFO = {"port": 3000, "state": "running", "status": "success"}


def _create_serving(serving_model, train_job, team=1):
    return serving_model.objects.create(
        name=f"serving-test-{team}",
        description="",
        team=[team],
        train_job=train_job,
        model_version="latest",
        status="inactive",
        container_info=CONTAINER_INFO,
    )


def _fake_build_predict_url(serving_id, container_info):
    return "http://fake-predict/predict"


# ---------------------------------------------------------------------------
# anomaly_detection — data list
# ---------------------------------------------------------------------------


def test_anomaly_detection_predict_rejects_oversized_batch(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("anomaly_detection-Predict")
    train_job = create_train_job(AnomalyDetectionTrainJob, team=1)
    serving = _create_serving(AnomalyDetectionServing, train_job)

    monkeypatch.setattr("apps.mlops.views.anomaly_detection.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_BATCH_SIZE", "3")

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.anomaly_detection.requests.post", fake_post)

    oversized_data = [{"value": i} for i in range(4)]  # 4 > limit 3
    response = mlops_api_client.post(
        f"/api/v1/mlops/anomaly_detection_servings/{serving.id}/predict/",
        {"data": oversized_data},
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0, "requests.post must NOT be called for oversized batches"


def test_anomaly_detection_predict_allows_batch_at_limit(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("anomaly_detection-Predict")
    train_job = create_train_job(AnomalyDetectionTrainJob, team=1)
    serving = _create_serving(AnomalyDetectionServing, train_job)

    monkeypatch.setattr("apps.mlops.views.anomaly_detection.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_BATCH_SIZE", "3")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True, "data": []}

    monkeypatch.setattr("apps.mlops.views.anomaly_detection.requests.post", lambda *a, **kw: FakeResponse())

    data = [{"value": i} for i in range(3)]  # exactly at limit
    response = mlops_api_client.post(
        f"/api/v1/mlops/anomaly_detection_servings/{serving.id}/predict/",
        {"data": data},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# classification — texts list
# ---------------------------------------------------------------------------


def test_classification_predict_rejects_oversized_batch(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("classification-Predict")
    train_job = create_train_job(ClassificationTrainJob, team=1)
    serving = _create_serving(ClassificationServing, train_job)

    monkeypatch.setattr("apps.mlops.views.classification.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_BATCH_SIZE", "2")

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.classification.requests.post", fake_post)

    response = mlops_api_client.post(
        f"/api/v1/mlops/classification_servings/{serving.id}/predict/",
        {"texts": ["a", "b", "c"]},  # 3 > limit 2
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0


# ---------------------------------------------------------------------------
# image_classification — images list + single-item byte limit
# ---------------------------------------------------------------------------


def test_image_classification_predict_rejects_oversized_batch(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("image_classification-Predict")
    train_job = create_train_job(ImageClassificationTrainJob, team=1)
    serving = _create_serving(ImageClassificationServing, train_job)

    monkeypatch.setattr("apps.mlops.views.image_classification.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_SIZE", "1")

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.image_classification.requests.post", fake_post)

    response = mlops_api_client.post(
        f"/api/v1/mlops/image_classification_servings/{serving.id}/predict/",
        {"images": ["base64img1", "base64img2"]},  # 2 > limit 1
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0


def test_image_classification_predict_rejects_oversized_single_image(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("image_classification-Predict")
    train_job = create_train_job(ImageClassificationTrainJob, team=1)
    serving = _create_serving(ImageClassificationServing, train_job)

    monkeypatch.setattr("apps.mlops.views.image_classification.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_SIZE", "10")
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BYTES", "5")  # 5 bytes limit

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.image_classification.requests.post", fake_post)

    big_image = "x" * 6  # 6 bytes > limit 5
    response = mlops_api_client.post(
        f"/api/v1/mlops/image_classification_servings/{serving.id}/predict/",
        {"images": [big_image]},
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0


# ---------------------------------------------------------------------------
# object_detection — images list
# ---------------------------------------------------------------------------


def test_object_detection_predict_rejects_oversized_batch(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("object_detection-Predict")
    train_job = create_train_job(ObjectDetectionTrainJob, team=1)
    from .conftest import create_object_detection_serving

    serving = create_object_detection_serving(train_job, team=1, container_info=CONTAINER_INFO)

    monkeypatch.setattr("apps.mlops.views.object_detection.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_IMAGE_BATCH_SIZE", "1")

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.object_detection.requests.post", fake_post)

    response = mlops_api_client.post(
        f"/api/v1/mlops/object_detection_servings/{serving.id}/predict/",
        {"images": ["img1", "img2"]},  # 2 > limit 1
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0


# ---------------------------------------------------------------------------
# timeseries_predict — data list
# ---------------------------------------------------------------------------


def test_timeseries_predict_rejects_oversized_batch(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("timeseries_predict-Predict")
    train_job = create_train_job(TimeSeriesPredictTrainJob, team=1)
    serving = _create_serving(TimeSeriesPredictServing, train_job)

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_BATCH_SIZE", "2")

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.timeseries_predict.requests.post", fake_post)

    data = [{"timestamp": "2024-01-01", "value": i} for i in range(3)]  # 3 > limit 2
    response = mlops_api_client.post(
        f"/api/v1/mlops/timeseries_predict_servings/{serving.id}/predict/",
        {"data": data},
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0


# ---------------------------------------------------------------------------
# log_clustering — data list
# ---------------------------------------------------------------------------


def test_log_clustering_predict_rejects_oversized_batch(mlops_api_client, mlops_user, monkeypatch):
    mlops_user.permission["mlops"].add("log_clustering-Predict")
    train_job = create_train_job(LogClusteringTrainJob, team=1)
    serving = _create_serving(LogClusteringServing, train_job)

    monkeypatch.setattr("apps.mlops.views.log_clustering.build_predict_url", _fake_build_predict_url)
    monkeypatch.setenv("MLOPS_PREDICT_MAX_BATCH_SIZE", "2")

    post_called = {"count": 0}

    def fake_post(*args, **kwargs):
        post_called["count"] += 1

    monkeypatch.setattr("apps.mlops.views.log_clustering.requests.post", fake_post)

    response = mlops_api_client.post(
        f"/api/v1/mlops/log_clustering_servings/{serving.id}/predict/",
        {"data": ["log1", "log2", "log3"]},  # 3 > limit 2
        format="json",
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert post_called["count"] == 0
