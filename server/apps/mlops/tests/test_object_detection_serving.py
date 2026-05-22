import pytest
from rest_framework import status

from apps.mlops.models.object_detection import ObjectDetectionTrainJob
from .conftest import create_object_detection_serving, create_train_job


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_object_detection_predict_uses_container_info_even_when_serving_status_is_inactive(
    mlops_api_client,
    mlops_user,
    monkeypatch,
):
    mlops_user.permission["mlops"].add("object_detection-Predict")
    train_job = create_train_job(ObjectDetectionTrainJob, team=1)
    serving = create_object_detection_serving(
        train_job,
        team=1,
        status_value="inactive",
        container_info={"port": 3000, "state": "running", "status": "success"},
    )

    build_predict_url_calls = {"count": 0}
    requests_post_calls = {"count": 0}

    def fake_build_predict_url(serving_id, container_info):
        build_predict_url_calls["count"] += 1
        assert serving_id == f"ObjectDetection_Serving_{serving.id}"
        assert container_info["port"] == 3000
        return "http://fake-service/predict"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "predictions": []}

    def fake_post(url, json, timeout):
        requests_post_calls["count"] += 1
        assert url == "http://fake-service/predict"
        assert json == {"images": ["base64-image"]}
        assert timeout == 60
        return FakeResponse()

    monkeypatch.setattr("apps.mlops.views.object_detection.build_predict_url", fake_build_predict_url)
    monkeypatch.setattr("apps.mlops.views.object_detection.requests.post", fake_post)

    response = mlops_api_client.post(
        f"/api/v1/mlops/object_detection_servings/{serving.id}/predict/",
        {"images": ["base64-image"]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"success": True, "predictions": []}
    assert build_predict_url_calls["count"] == 1
    assert requests_post_calls["count"] == 1
