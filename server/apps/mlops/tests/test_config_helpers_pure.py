import pydantic.root_model  # noqa

import pytest

from apps.mlops.services import config_helpers as ch

pytestmark = pytest.mark.unit


def _set_all(monkeypatch):
    monkeypatch.setenv("MLFLOW_S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("MLFLOW_TRACKER_URL", "http://mlflow:5000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "ak")
    monkeypatch.setenv("MINIO_SECRET_KEY", "sk")


def test_get_mlflow_train_config_success(monkeypatch):
    _set_all(monkeypatch)
    cfg = ch.get_mlflow_train_config()
    assert isinstance(cfg, ch.MLflowTrainConfig)
    assert cfg.bucket == "munchkin-public"
    assert cfg.minio_endpoint == "http://minio:9000"
    assert cfg.mlflow_tracking_uri == "http://mlflow:5000"
    assert cfg.minio_access_key == "ak"
    assert cfg.minio_secret_key == "sk"


def test_get_mlflow_train_config_missing_endpoint(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("MLFLOW_S3_ENDPOINT_URL", raising=False)
    with pytest.raises(ch.ConfigurationError) as exc:
        ch.get_mlflow_train_config()
    assert "MinIO endpoint" in str(exc.value)


def test_get_mlflow_train_config_missing_tracking_uri(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("MLFLOW_TRACKER_URL", raising=False)
    with pytest.raises(ch.ConfigurationError) as exc:
        ch.get_mlflow_train_config()
    assert "tracking URI" in str(exc.value)


def test_get_mlflow_train_config_missing_access_key(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    with pytest.raises(ch.ConfigurationError) as exc:
        ch.get_mlflow_train_config()
    assert "credentials" in str(exc.value)


def test_get_mlflow_train_config_missing_secret_key(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    with pytest.raises(ch.ConfigurationError):
        ch.get_mlflow_train_config()


def test_get_mlflow_tracking_uri_success(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKER_URL", "http://mlflow:5000")
    assert ch.get_mlflow_tracking_uri() == "http://mlflow:5000"


def test_get_mlflow_tracking_uri_missing(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKER_URL", raising=False)
    with pytest.raises(ch.ConfigurationError):
        ch.get_mlflow_tracking_uri()


def test_config_helpers_get_host_address_parses(monkeypatch):
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://10.10.41.149:443")
    assert ch.get_host_address() == "10.10.41.149"


def test_config_helpers_get_host_address_domain(monkeypatch):
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://bklite.example.com:443")
    assert ch.get_host_address() == "bklite.example.com"


def test_config_helpers_get_host_address_empty(monkeypatch):
    monkeypatch.delenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", raising=False)
    assert ch.get_host_address() == ""


def test_config_helpers_get_host_address_no_hostname(monkeypatch):
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "garbage")
    assert ch.get_host_address() == ""
