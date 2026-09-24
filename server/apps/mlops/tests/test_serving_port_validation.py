import importlib
from types import SimpleNamespace

import pydantic.root_model  # noqa
import pytest
from rest_framework import serializers as drf_serializers

from apps.mlops.utils.webhook_client import WebhookClient, WebhookError

pytestmark = pytest.mark.unit


SERVING_SERIALIZERS = [
    ("anomaly_detection", "AnomalyDetectionServingSerializer"),
    ("classification", "ClassificationServingSerializer"),
    ("log_clustering", "LogClusteringServingSerializer"),
    ("timeseries_predict", "TimeSeriesPredictServingSerializer"),
    ("image_classification", "ImageClassificationServingSerializer"),
    ("object_detection", "ObjectDetectionServingSerializer"),
]
SERIALIZER_IDS = [item[0] for item in SERVING_SERIALIZERS]

ALLOWED_PORTS = [None, 9000, 3042]
REJECTED_PORTS = [22, 80, 8080, 65536]


def _serving_serializer(monkeypatch, module_name, class_name, data):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )
    serializer_cls = getattr(importlib.import_module(f"apps.mlops.serializers.{module_name}"), class_name)
    request = SimpleNamespace(user=SimpleNamespace(locale="zh-Hans"), COOKIES={"current_team": "1"})
    return serializer_cls(data=data, partial=True, context={"request": request})


def _port_error_text(errors):
    return "".join(str(item) for item in errors["port"])


@pytest.mark.parametrize("module_name,class_name", SERVING_SERIALIZERS, ids=SERIALIZER_IDS)
@pytest.mark.parametrize("port", REJECTED_PORTS, ids=["22", "80", "8080", "65536"])
def test_serving_serializer_rejects_sensitive_and_out_of_range_ports(monkeypatch, module_name, class_name, port):
    serializer = _serving_serializer(monkeypatch, module_name, class_name, {"port": port})
    assert not serializer.is_valid()
    assert "port" in serializer.errors
    with pytest.raises(drf_serializers.ValidationError):
        serializer.validate_port(port)


def test_serving_serializer_rejects_port_22_with_localized_copy(monkeypatch):
    serializer = _serving_serializer(monkeypatch, "anomaly_detection", "AnomalyDetectionServingSerializer", {"port": 22})
    assert not serializer.is_valid()
    text = _port_error_text(serializer.errors)
    assert "error.serving_port_invalid" not in text
    assert any(
        phrase in text
        for phrase in (
            "端口须在 1024-65535 且不能是系统或数据库常用端口",
            "Port must be in 1024-65535 and cannot be a common system or database port",
        )
    )


@pytest.mark.parametrize("module_name,class_name", SERVING_SERIALIZERS, ids=SERIALIZER_IDS)
@pytest.mark.parametrize("port", ALLOWED_PORTS, ids=["none", "9000", "3042"])
def test_serving_serializer_allows_empty_and_high_ports(monkeypatch, module_name, class_name, port):
    serializer = _serving_serializer(monkeypatch, module_name, class_name, {"port": port})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data.get("port") == port


def test_webhook_serve_rejects_illegal_port_without_http(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    monkeypatch.delenv("MLOPS_DOCKER_NETWORK", raising=False)
    called = []

    def fake_request(endpoint, payload, timeout=30):
        called.append((endpoint, payload, timeout))
        return {"status": "success"}

    monkeypatch.setattr(WebhookClient, "_request", staticmethod(fake_request))

    with pytest.raises(WebhookError, match="error.serving_port_invalid"):
        WebhookClient.serve("Svc_1", "http://mlflow", "models:/m/1", port=22)

    assert called == []


@pytest.mark.parametrize("value", [None, ""])
def test_parse_serving_port_empty_returns_none(value):
    from apps.mlops.utils.serving_port import parse_serving_port

    assert parse_serving_port(value) is None


@pytest.mark.parametrize("value", [9000, 3042, 1024, 65535])
def test_parse_serving_port_allows_high_ports(value):
    from apps.mlops.utils.serving_port import parse_serving_port

    assert parse_serving_port(value) == value


@pytest.mark.parametrize("value", [22, 80, 443, 3306, 5432, 6379, 27017, 8080, 1023, 65536])
def test_parse_serving_port_rejects_illegal_ports(value):
    from apps.mlops.utils.serving_port import parse_serving_port

    with pytest.raises(ValueError, match="error.serving_port_invalid"):
        parse_serving_port(value)
