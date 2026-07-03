import pydantic.root_model  # noqa

import pytest

from apps.mlops import predict_url_builder as pub

pytestmark = pytest.mark.unit


def test_sanitize_k8s_name_lowercases_and_replaces_underscore():
    assert pub.sanitize_k8s_name("Anomaly_Detection_01") == "anomaly-detection-01"


def test_get_host_address_empty_env_returns_empty(monkeypatch):
    monkeypatch.delenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", raising=False)
    assert pub.get_host_address() == ""


def test_get_host_address_parses_hostname(monkeypatch):
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://host.example.com:443")
    assert pub.get_host_address() == "host.example.com"


def test_get_host_address_no_hostname_returns_empty(monkeypatch):
    # urlparse on a bare path has no hostname
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "not-a-url")
    assert pub.get_host_address() == ""


def test_build_predict_url_missing_port_raises(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    with pytest.raises(ValueError) as exc:
        pub.build_predict_url("svc-1", {})
    assert "服务端口未配置" in str(exc.value)


def test_build_predict_url_none_container_info_raises(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    with pytest.raises(ValueError):
        pub.build_predict_url("svc-1", None)


def test_build_predict_url_kubernetes_uses_svc_dns(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "kubernetes")
    monkeypatch.setenv("MLOPS_KUBERNETES_NAMESPACE", "ml-ns")
    url = pub.build_predict_url("Serving_AB", {"port": 8080})
    assert url == "http://serving-ab-svc.ml-ns.svc.cluster.local:3000/predict"


def test_build_predict_url_kubernetes_default_namespace(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "kubernetes")
    monkeypatch.delenv("MLOPS_KUBERNETES_NAMESPACE", raising=False)
    url = pub.build_predict_url("svc", {"port": 1})
    assert url == "http://svc-svc.mlops.svc.cluster.local:3000/predict"


def test_build_predict_url_docker_uses_serving_id(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "docker")
    url = pub.build_predict_url("my-serving", {"port": 9000})
    assert url == "http://my-serving:3000/predict"


def test_build_predict_url_runtime_defaults_to_docker(monkeypatch):
    monkeypatch.delenv("MLOPS_RUNTIME", raising=False)
    url = pub.build_predict_url("svc-default", {"port": 9000})
    assert url == "http://svc-default:3000/predict"


def test_build_predict_url_other_runtime_uses_host_port(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "host")
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://10.0.0.5:443")
    url = pub.build_predict_url("svc", {"port": 32000})
    assert url == "http://10.0.0.5:32000/predict"


def test_build_predict_url_other_runtime_no_host_raises(monkeypatch):
    monkeypatch.setenv("MLOPS_RUNTIME", "host")
    monkeypatch.delenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", raising=False)
    with pytest.raises(ValueError) as exc:
        pub.build_predict_url("svc", {"port": 32000})
    assert "服务地址未配置" in str(exc.value)
