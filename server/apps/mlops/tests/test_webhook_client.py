import pydantic.root_model  # noqa

import pytest
import requests

from apps.mlops.utils.webhook_client import (
    WebhookClient,
    WebhookConnectionError,
    WebhookError,
    WebhookTimeoutError,
)

pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", raise_json=False):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._json_data


# ---------------- get_runtime ----------------


def test_get_runtime_default_docker(monkeypatch):
    monkeypatch.delenv("MLOPS_RUNTIME", raising=False)
    assert WebhookClient.get_runtime() == "docker"


def test_get_runtime_kubernetes(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "Kubernetes")
    assert WebhookClient.get_runtime() == "kubernetes"


def test_get_runtime_invalid_falls_back_to_docker(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "podman")
    assert WebhookClient.get_runtime() == "docker"


# ---------------- get_base_url ----------------


def test_get_base_url_none_when_unset(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_URL", raising=False)
    assert WebhookClient.get_base_url() is None


def test_get_base_url_appends_trailing_slash(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    assert WebhookClient.get_base_url() == "http://hook:8080/"


def test_get_base_url_keeps_existing_slash(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080/")
    assert WebhookClient.get_base_url() == "http://hook:8080/"


# ---------------- build_url ----------------


def test_build_url_docker(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    assert WebhookClient.build_url("train") == "http://hook:8080/mlops/docker/train"


def test_build_url_kubernetes(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    monkeypatch.setenv("MLOPS_RUNTIME", "kubernetes")
    assert WebhookClient.build_url("status") == "http://hook:8080/mlops/kubernetes/status"


def test_build_url_none_when_base_missing(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_URL", raising=False)
    assert WebhookClient.build_url("train") is None


# ---------------- validate_config ----------------


def test_validate_config_invalid(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_URL", raising=False)
    ok, msg = WebhookClient.validate_config()
    assert ok is False
    assert "WEBHOOK_SERVER_URL" in msg


def test_validate_config_valid(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    ok, msg = WebhookClient.validate_config()
    assert ok is True
    assert msg == ""


# ---------------- get_all_endpoints ----------------


def test_get_all_endpoints_maps_all_names(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    endpoints = WebhookClient.get_all_endpoints()
    assert set(endpoints.keys()) == {"train", "status", "stop", "logs", "serve", "remove"}
    assert endpoints["serve"] == "http://hook:8080/mlops/docker/serve"


# ---------------- _add_runtime_params ----------------


def test_add_runtime_params_kubernetes_uses_namespace(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "kubernetes")
    monkeypatch.setenv("MLOPS_KUBERNETES_NAMESPACE", "ml-ns")
    payload = {}
    WebhookClient._add_runtime_params(payload)
    assert payload == {"namespace": "ml-ns"}


def test_add_runtime_params_kubernetes_default_namespace(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "kubernetes")
    monkeypatch.delenv("MLOPS_KUBERNETES_NAMESPACE", raising=False)
    payload = {}
    WebhookClient._add_runtime_params(payload)
    assert payload == {"namespace": "mlops"}


def test_add_runtime_params_docker_with_network(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    monkeypatch.setenv("MLOPS_DOCKER_NETWORK", "host")
    payload = {}
    WebhookClient._add_runtime_params(payload)
    assert payload == {"network_mode": "host"}


def test_add_runtime_params_docker_without_network(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    monkeypatch.delenv("MLOPS_DOCKER_NETWORK", raising=False)
    payload = {}
    WebhookClient._add_runtime_params(payload)
    assert payload == {}


# ---------------- _request ----------------


def _setup_hook(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SERVER_URL", "http://hook:8080")
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    monkeypatch.delenv("MLOPS_DOCKER_NETWORK", raising=False)


def test_request_no_url_raises(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SERVER_URL", raising=False)
    with pytest.raises(WebhookError) as exc:
        WebhookClient._request("train", {})
    assert "WEBHOOK_SERVER_URL" in str(exc.value)


def test_request_success_returns_json(monkeypatch):
    _setup_hook(monkeypatch)
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(200, {"status": "success", "id": "x"})

    monkeypatch.setattr(requests, "post", fake_post)
    result = WebhookClient._request("train", {"id": "job1"}, timeout=15)
    assert result == {"status": "success", "id": "x"}
    assert captured["url"] == "http://hook:8080/mlops/docker/train"
    assert captured["json"] == {"id": "job1"}
    assert captured["timeout"] == 15


def test_request_non200_json_error_with_code_and_detail(monkeypatch):
    _setup_hook(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        return FakeResponse(
            500,
            {"message": "boom", "code": "ERR_X", "detail": "deep cause"},
        )

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(WebhookError) as exc:
        WebhookClient._request("train", {})
    assert exc.value.code == "ERR_X"
    assert "boom" in str(exc.value)
    assert "deep cause" in str(exc.value)


def test_request_non200_non_json_uses_text(monkeypatch):
    _setup_hook(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        return FakeResponse(502, raise_json=True, text="gateway down")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(WebhookError) as exc:
        WebhookClient._request("train", {})
    assert "502" in str(exc.value)
    assert "gateway down" in str(exc.value)


def test_request_timeout_raises_timeout_error(monkeypatch):
    _setup_hook(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(WebhookTimeoutError):
        WebhookClient._request("train", {})


def test_request_connection_error(monkeypatch):
    _setup_hook(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(WebhookConnectionError):
        WebhookClient._request("train", {})


def test_request_generic_request_exception(monkeypatch):
    _setup_hook(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        raise requests.exceptions.RequestException("weird")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(WebhookError):
        WebhookClient._request("train", {})


# ---------------- high level wrappers ----------------


def test_serve_builds_payload_and_returns_result(monkeypatch):
    _setup_hook(monkeypatch)
    captured = {}

    def fake_request(endpoint, payload, timeout=30):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"status": "success", "port": "3042"}

    monkeypatch.setattr(WebhookClient, "_request", staticmethod(fake_request))
    result = WebhookClient.serve(
        "Svc_1", "http://mlflow", "models:/m/1", port=3042, train_image="img", device="gpu"
    )
    assert result["port"] == "3042"
    assert captured["endpoint"] == "serve"
    p = captured["payload"]
    assert p["id"] == "Svc_1"
    assert p["mlflow_model_uri"] == "models:/m/1"
    assert p["port"] == 3042
    assert p["train_image"] == "img"
    assert p["device"] == "gpu"


def test_serve_error_status_raises(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda *a, **k: {"status": "error", "message": "fail", "code": "C1"}),
    )
    with pytest.raises(WebhookError) as exc:
        WebhookClient.serve("Svc_1", "http://mlflow", "models:/m/1")
    assert exc.value.code == "C1"


def test_serve_omits_optional_params(monkeypatch):
    _setup_hook(monkeypatch)
    captured = {}
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload, timeout=30: captured.update(payload) or {"status": "success"}),
    )
    WebhookClient.serve("Svc_1", "http://mlflow", "models:/m/1")
    assert "port" not in captured
    assert "train_image" not in captured
    assert "device" not in captured


def test_train_builds_payload(monkeypatch):
    _setup_hook(monkeypatch)
    captured = {}

    def fake_request(endpoint, payload, timeout=30):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"status": "success"}

    monkeypatch.setattr(WebhookClient, "_request", staticmethod(fake_request))
    WebhookClient.train(
        "job1", "bucket", "ds.zip", "cfg.yaml",
        "http://minio", "http://mlflow", "ak", "sk",
        train_image="img", device="cpu",
    )
    assert captured["endpoint"] == "train"
    p = captured["payload"]
    assert p["id"] == "job1"
    assert p["bucket"] == "bucket"
    assert p["minio_access_key"] == "ak"
    assert p["train_image"] == "img"
    assert p["device"] == "cpu"


def test_train_error_status_raises(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda *a, **k: {"status": "error", "message": "nope"}),
    )
    with pytest.raises(WebhookError):
        WebhookClient.train("job1", "b", "d", "c", "e", "m", "ak", "sk")


def test_stop_returns_result(monkeypatch):
    _setup_hook(monkeypatch)
    captured = {}
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload, timeout=30: captured.update(endpoint=endpoint, payload=payload) or {"status": "success"}),
    )
    res = WebhookClient.stop("job1")
    assert res["status"] == "success"
    assert captured["endpoint"] == "stop"
    assert captured["payload"]["id"] == "job1"


def test_stop_error_raises(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient, "_request", staticmethod(lambda *a, **k: {"status": "error", "message": "x"})
    )
    with pytest.raises(WebhookError):
        WebhookClient.stop("job1")


def test_remove_returns_result(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient, "_request", staticmethod(lambda endpoint, payload, timeout=30: {"status": "success", "id": payload["id"]})
    )
    res = WebhookClient.remove("c1")
    assert res["id"] == "c1"


def test_remove_error_raises(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient, "_request", staticmethod(lambda *a, **k: {"status": "error", "message": "x", "code": "RM"})
    )
    with pytest.raises(WebhookError) as exc:
        WebhookClient.remove("c1")
    assert exc.value.code == "RM"


def test_get_status_returns_results_list(monkeypatch):
    _setup_hook(monkeypatch)
    captured = {}
    monkeypatch.setattr(
        WebhookClient,
        "_request",
        staticmethod(lambda endpoint, payload, timeout=30: captured.update(endpoint=endpoint, payload=payload) or {"status": "success", "results": [{"id": "a"}]}),
    )
    res = WebhookClient.get_status(["a", "b"])
    assert res == [{"id": "a"}]
    assert captured["endpoint"] == "status"
    assert captured["payload"]["ids"] == ["a", "b"]


def test_get_status_error_raises(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient, "_request", staticmethod(lambda *a, **k: {"status": "error", "message": "x"})
    )
    with pytest.raises(WebhookError):
        WebhookClient.get_status(["a"])


def test_get_status_missing_results_returns_empty(monkeypatch):
    _setup_hook(monkeypatch)
    monkeypatch.setattr(
        WebhookClient, "_request", staticmethod(lambda *a, **k: {"status": "success"})
    )
    assert WebhookClient.get_status(["a"]) == []
