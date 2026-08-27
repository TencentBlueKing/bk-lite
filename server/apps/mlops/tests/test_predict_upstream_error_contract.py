"""算法预测端点的新旧错误契约兼容测试（Issue #4009）。"""

import pytest
import requests
from rest_framework import status

from apps.mlops.models.anomaly_detection import AnomalyDetectionServing, AnomalyDetectionTrainJob
from apps.mlops.models.classification import ClassificationServing, ClassificationTrainJob
from apps.mlops.models.image_classification import ImageClassificationServing, ImageClassificationTrainJob
from apps.mlops.models.log_clustering import LogClusteringServing, LogClusteringTrainJob
from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing, TimeSeriesPredictTrainJob

from .conftest import create_object_detection_serving, create_train_job

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

CONTAINER_INFO = {"port": 3000, "state": "running", "status": "success"}


def _create_serving(serving_model, train_job, team=1):
    return serving_model.objects.create(
        name=f"typed-error-contract-{team}",
        description="",
        team=[team],
        train_job=train_job,
        model_version="latest",
        status="inactive",
        container_info=CONTAINER_INFO,
    )


PREDICT_CASES = [
    pytest.param(
        "anomaly_detection",
        "anomaly_detection-Predict",
        AnomalyDetectionTrainJob,
        AnomalyDetectionServing,
        {"data": [{"value": 1}]},
        status.HTTP_400_BAD_REQUEST,
        id="anomaly-400",
    ),
    pytest.param(
        "classification",
        "classification-Predict",
        ClassificationTrainJob,
        ClassificationServing,
        {"texts": ["sample"]},
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        id="text-413",
    ),
    pytest.param(
        "image_classification",
        "image_classification-Predict",
        ImageClassificationTrainJob,
        ImageClassificationServing,
        {"images": ["base64-image"]},
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        id="image-422",
    ),
    pytest.param(
        "log_clustering",
        "log_clustering-Predict",
        LogClusteringTrainJob,
        LogClusteringServing,
        {"data": ["log line"]},
        status.HTTP_400_BAD_REQUEST,
        id="log-400",
    ),
    pytest.param(
        "timeseries_predict",
        "timeseries_predict-Predict",
        TimeSeriesPredictTrainJob,
        TimeSeriesPredictServing,
        {"data": [{"timestamp": "2024-01-01T00:00:00Z", "value": 1}], "steps": 1},
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        id="timeseries-413",
    ),
    pytest.param(
        "object_detection",
        "object_detection-Predict",
        ObjectDetectionTrainJob,
        None,
        {"images": ["base64-image"]},
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        id="object-422",
    ),
]


@pytest.mark.parametrize(
    ("route", "permission", "train_job_model", "serving_model", "payload", "upstream_status"),
    PREDICT_CASES,
)
def test_predict_preserves_upstream_client_error_status(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    route,
    permission,
    train_job_model,
    serving_model,
    payload,
    upstream_status,
):
    """算法侧 400/413/422 是客户端输入错误，Server 不应放大成 500。"""
    mlops_user.permission["mlops"].add(permission)
    train_job = create_train_job(train_job_model, team=1)
    if route == "object_detection":
        serving = create_object_detection_serving(train_job, team=1, container_info=CONTAINER_INFO)
    else:
        serving = _create_serving(serving_model, train_job)

    module_path = f"apps.mlops.views.{route}"
    monkeypatch.setattr(f"{module_path}.build_predict_url", lambda **_kwargs: "http://fake-predict/predict")

    class FakeResponse:
        status_code = upstream_status
        text = '{"detail":[{"type":"request_validation"}]}'

        def json(self):
            return {"detail": [{"type": "request_validation"}]}

        def raise_for_status(self):
            raise AssertionError("已识别的客户端输入错误不应进入 HTTPError 分支")

    monkeypatch.setattr(f"{module_path}.requests.post", lambda *_args, **_kwargs: FakeResponse())

    response = mlops_api_client.post(
        f"/api/v1/mlops/{route}_servings/{serving.id}/predict/",
        payload,
        format="json",
    )

    assert response.status_code == upstream_status
    assert "error" in response.data


LEGACY_ENVELOPE_CASES = [
    pytest.param(
        "anomaly_detection",
        "anomaly_detection-Predict",
        AnomalyDetectionTrainJob,
        AnomalyDetectionServing,
        {"data": [{"value": 1}]},
        id="anomaly",
    ),
    pytest.param(
        "classification",
        "classification-Predict",
        ClassificationTrainJob,
        ClassificationServing,
        {"texts": ["sample"]},
        id="text",
    ),
    pytest.param(
        "log_clustering",
        "log_clustering-Predict",
        LogClusteringTrainJob,
        LogClusteringServing,
        {"data": ["log line"]},
        id="log",
    ),
    pytest.param(
        "timeseries_predict",
        "timeseries_predict-Predict",
        TimeSeriesPredictTrainJob,
        TimeSeriesPredictServing,
        {"data": [{"timestamp": "2024-01-01T00:00:00Z", "value": 1}], "steps": 1},
        id="timeseries",
    ),
]


@pytest.mark.parametrize(
    ("route", "permission", "train_job_model", "serving_model", "payload"),
    LEGACY_ENVELOPE_CASES,
)
def test_predict_keeps_legacy_error_envelope_contract(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    route,
    permission,
    train_job_model,
    serving_model,
    payload,
):
    """旧镜像的 200 + error envelope 在迁移窗口内仍按既有 400 解析。"""
    mlops_user.permission["mlops"].add(permission)
    train_job = create_train_job(train_job_model, team=1)
    serving = _create_serving(serving_model, train_job)
    module_path = f"apps.mlops.views.{route}"
    monkeypatch.setattr(f"{module_path}.build_predict_url", lambda **_kwargs: "http://fake-predict/predict")

    class FakeResponse:
        status_code = status.HTTP_200_OK

        def json(self):
            return {
                "success": False,
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "legacy validation failed",
                    "details": {"field": "data"},
                },
            }

    monkeypatch.setattr(f"{module_path}.requests.post", lambda *_args, **_kwargs: FakeResponse())

    response = mlops_api_client.post(
        f"/api/v1/mlops/{route}_servings/{serving.id}/predict/",
        payload,
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error_code"] == "INVALID_INPUT"
    assert response.data["details"] == {"field": "data"}


@pytest.mark.parametrize(
    ("route", "permission", "train_job_model", "serving_model"),
    [
        pytest.param(
            "image_classification",
            "image_classification-Predict",
            ImageClassificationTrainJob,
            ImageClassificationServing,
            id="image",
        ),
        pytest.param(
            "object_detection",
            "object_detection-Predict",
            ObjectDetectionTrainJob,
            None,
            id="object",
        ),
    ],
)
def test_image_predict_keeps_partial_success_contract(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    route,
    permission,
    train_job_model,
    serving_model,
):
    """图片类旧镜像可继续返回单项失败、同批其他项成功的 200 响应。"""
    mlops_user.permission["mlops"].add(permission)
    train_job = create_train_job(train_job_model, team=1)
    if route == "object_detection":
        serving = create_object_detection_serving(train_job, team=1, container_info=CONTAINER_INFO)
    else:
        serving = _create_serving(serving_model, train_job)

    module_path = f"apps.mlops.views.{route}"
    monkeypatch.setattr(f"{module_path}.build_predict_url", lambda **_kwargs: "http://fake-predict/predict")
    partial_result = {
        "success": True,
        "results": [
            {"success": False, "error": {"code": "INVALID_IMAGE"}},
            {"success": True, "prediction": {"label": "normal"}},
        ],
    }

    class FakeResponse:
        status_code = status.HTTP_200_OK

        def json(self):
            return partial_result

        def raise_for_status(self):
            return None

    monkeypatch.setattr(f"{module_path}.requests.post", lambda *_args, **_kwargs: FakeResponse())

    response = mlops_api_client.post(
        f"/api/v1/mlops/{route}_servings/{serving.id}/predict/",
        {"images": ["invalid-image", "valid-image"]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data == partial_result


@pytest.mark.parametrize(
    ("route", "permission", "train_job_model", "serving_model", "payload"),
    [
        pytest.param(
            "anomaly_detection",
            "anomaly_detection-Predict",
            AnomalyDetectionTrainJob,
            AnomalyDetectionServing,
            {"data": [{"value": 1}]},
            id="standard-proxy",
        ),
        pytest.param(
            "object_detection",
            "object_detection-Predict",
            ObjectDetectionTrainJob,
            None,
            {"images": ["base64-image"]},
            id="raise-for-status-proxy",
        ),
    ],
)
def test_predict_keeps_upstream_service_failures_internal(
    mlops_api_client,
    mlops_user,
    monkeypatch,
    route,
    permission,
    train_job_model,
    serving_model,
    payload,
):
    """算法服务自身失败仍收敛为 500，不能被输入错误映射误放大到客户端。"""
    mlops_user.permission["mlops"].add(permission)
    train_job = create_train_job(train_job_model, team=1)
    if route == "object_detection":
        serving = create_object_detection_serving(train_job, team=1, container_info=CONTAINER_INFO)
    else:
        serving = _create_serving(serving_model, train_job)

    module_path = f"apps.mlops.views.{route}"
    monkeypatch.setattr(f"{module_path}.build_predict_url", lambda **_kwargs: "http://fake-predict/predict")

    class FakeResponse:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        text = "serving unavailable"

        def json(self):
            return {"error": "serving unavailable"}

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("503 Server Error")

    monkeypatch.setattr(f"{module_path}.requests.post", lambda *_args, **_kwargs: FakeResponse())

    response = mlops_api_client.post(
        f"/api/v1/mlops/{route}_servings/{serving.id}/predict/",
        payload,
        format="json",
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
