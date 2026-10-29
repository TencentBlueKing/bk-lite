"""网关回调 URL 缺省值与 Compose / K8s 回写。"""

from apps.core.openapi.async_callback import rewrite_gateway_callback_url

CALLBACK = "https://10.11.10.182/openapi/v1/itsm/openapi/v1/action_components/callback/"


def _clear_callback_env(monkeypatch):
    for key in (
        "OPENAPI_PUBLIC_ORIGIN",
        "OPENAPI_CALLBACK_INTERNAL_BASE",
        "DEFAULT_ZONE_VAR_NODE_SERVER_URL",
        "NEXTAUTH_URL",
        "TRAEFIK_WEB_PORT",
        "KUBERNETES_SERVICE_HOST",
        "HOST_IP",
    ):
        monkeypatch.delenv(key, raising=False)


def test_compose_defaults_rewrite_public_https_to_traefik(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://10.11.10.182:443")

    assert rewrite_gateway_callback_url(CALLBACK) == "https://traefik/openapi/v1/itsm/openapi/v1/action_components/callback/"


def test_compose_defaults_match_http_callback_on_same_host(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://10.11.10.182:443")

    http_cb = "http://10.11.10.182/openapi/v1/itsm/openapi/v1/action_components/callback/"
    assert rewrite_gateway_callback_url(http_cb) == "https://traefik/openapi/v1/itsm/openapi/v1/action_components/callback/"


def test_compose_nonstandard_traefik_port(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://10.11.10.182:8443")
    monkeypatch.setenv("TRAEFIK_WEB_PORT", "8443")

    url = "https://10.11.10.182:8443/openapi/v1/itsm/cb"
    assert rewrite_gateway_callback_url(url) == "https://traefik:8443/openapi/v1/itsm/cb"


def test_explicit_http_compose_traefik_is_upgraded_to_https(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("OPENAPI_PUBLIC_ORIGIN", "https://10.11.10.182")
    monkeypatch.setenv("OPENAPI_CALLBACK_INTERNAL_BASE", "http://compose-traefik-1")

    assert rewrite_gateway_callback_url(CALLBACK) == "https://compose-traefik-1/openapi/v1/itsm/openapi/v1/action_components/callback/"


def test_k8s_default_does_not_rewrite_to_compose_traefik(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
    monkeypatch.setenv("NEXTAUTH_URL", "http://weopsx.example.com")

    url = "http://weopsx.example.com/openapi/v1/itsm/openapi/v1/action_components/callback/"
    assert rewrite_gateway_callback_url(url) == url


def test_k8s_explicit_internal_http_is_kept(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
    monkeypatch.setenv("OPENAPI_PUBLIC_ORIGIN", "https://weopsx.example.com")
    monkeypatch.setenv("OPENAPI_CALLBACK_INTERNAL_BASE", "http://traefik.kube-system.svc")

    url = "https://weopsx.example.com/openapi/v1/itsm/cb"
    assert rewrite_gateway_callback_url(url) == "http://traefik.kube-system.svc/openapi/v1/itsm/cb"


def test_unrelated_callback_host_is_unchanged(monkeypatch):
    _clear_callback_env(monkeypatch)
    monkeypatch.setenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "https://10.11.10.182:443")

    url = "https://example.com/openapi/v1/itsm/cb"
    assert rewrite_gateway_callback_url(url) == url
