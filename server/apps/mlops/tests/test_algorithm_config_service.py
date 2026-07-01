import pydantic.root_model  # noqa

import pytest

from apps.mlops.models import AlgorithmConfig
from apps.mlops.services import algorithm_config_service as svc

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _mk(algorithm_type="anomaly_detection", name="ECOD", image="repo/ecod:1", is_active=True):
    return AlgorithmConfig.objects.update_or_create(
        algorithm_type=algorithm_type,
        name=name,
        defaults={
            "display_name": name,
            "image": image,
            "is_active": is_active,
            "form_config": {},
        },
    )[0]


def test_get_algorithm_image_returns_db_image():
    _mk(image="repo/custom-ecod:9")
    assert svc.get_algorithm_image("anomaly_detection", "ECOD") == "repo/custom-ecod:9"


def test_get_algorithm_image_inactive_falls_back():
    _mk(name="IForest", image="repo/ignored:1", is_active=False)
    # inactive -> not found -> fallback default
    result = svc.get_algorithm_image("anomaly_detection", "IForest")
    assert result == svc.DEFAULT_IMAGES["anomaly_detection"]


def test_get_algorithm_image_missing_with_fallback_returns_default():
    result = svc.get_algorithm_image("timeseries_predict", "NoSuch")
    assert result == svc.DEFAULT_IMAGES["timeseries_predict"]


def test_get_algorithm_image_missing_no_fallback_returns_none():
    assert svc.get_algorithm_image("log_clustering", "NoSuch", fallback=False) is None


def test_get_algorithm_image_unknown_type_no_default_returns_none():
    # unknown algorithm_type has no DEFAULT_IMAGES entry -> None even with fallback
    assert svc.get_algorithm_image("unknown_type", "X") is None


def test_get_image_by_prefix_maps_prefix_to_type():
    _mk(algorithm_type="classification", name="XGBoost", image="repo/xgb:2")
    assert svc.get_image_by_prefix("Classification", "XGBoost") == "repo/xgb:2"


def test_get_image_by_prefix_unknown_prefix_returns_none():
    assert svc.get_image_by_prefix("BadPrefix", "X") is None


def test_get_image_by_prefix_fallback_default():
    assert (
        svc.get_image_by_prefix("ObjectDetection", "NoSuch")
        == svc.DEFAULT_IMAGES["object_detection"]
    )
