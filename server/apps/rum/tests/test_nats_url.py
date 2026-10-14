import pytest
from django.conf import settings

from apps.rum.services.settings import load_rum_settings, normalize_nats_endpoint, platform_nats_endpoint


def test_nats_endpoint_keeps_host_for_plain_and_tls():
    assert normalize_nats_endpoint("tls://NATS.internal:4222", "rum_ctl", "secret") == (
        "tls://nats.internal:4222",
        "rum_ctl",
        "secret",
    )
    assert normalize_nats_endpoint("nats://127.0.0.1:4222", "", "") == (
        "nats://127.0.0.1:4222",
        "",
        "",
    )


@pytest.mark.parametrize(
    ("url", "user", "password"),
    [
        ("", "rum_ctl", "secret"),
        ("nats://rum_ctl:secret@127.0.0.1:4222", "rum_ctl", "secret"),
        ("http://nats.internal:4222", "rum_ctl", "secret"),
        ("nats://127.0.0.1:4222", "rum_ctl", ""),
        ("tls://nats.internal:4222", "", "secret"),
    ],
)
def test_nats_endpoint_rejects_userinfo_and_half_credentials(url, user, password):
    assert normalize_nats_endpoint(url, user, password) == ("", "", "")


def test_platform_nats_endpoint_drops_embedded_account():
    assert platform_nats_endpoint("nats://admin:secret@127.0.0.1:4222") == "nats://127.0.0.1:4222"
    assert platform_nats_endpoint("tls://10.1.2.3:4422") == "tls://10.1.2.3:4422"
    assert platform_nats_endpoint("nats.internal:4222") == "nats://nats.internal:4222"
    assert platform_nats_endpoint("http://nats.internal:4222") == ""


def test_load_uses_platform_host_and_rum_password(monkeypatch):
    monkeypatch.setenv("RUM_NATS_URL", "nats://rum_ctl:secret@127.0.0.1:14222")
    monkeypatch.setenv("RUM_NATS_TLS_CA_FILE", "/run/secrets/rum-only-ca.pem")
    monkeypatch.setattr(settings, "NATS_SERVERS", "nats://admin:platform-secret@127.0.0.1:4222", raising=False)
    monkeypatch.setenv("RUM_NATS_USER", "rum_ctl")
    monkeypatch.setenv("RUM_NATS_PASSWORD", "rum-secret")

    loaded = load_rum_settings()

    assert loaded.nats_url == "nats://127.0.0.1:4222"
    assert loaded.nats_user == "rum_ctl"
    assert loaded.nats_password == "rum-secret"
    assert loaded.nats_tls_ca_file == ""
    assert "platform-secret" not in loaded.nats_url
    assert "14222" not in loaded.nats_url
    assert loaded.nats_password != "platform-secret"


def test_tls_reuses_platform_ca_file(monkeypatch):
    monkeypatch.setenv("RUM_NATS_TLS_CA_FILE", "/run/secrets/rum-only-ca.pem")
    monkeypatch.setattr(settings, "NATS_SERVERS", "tls://admin:platform-secret@nats.internal:4422", raising=False)
    monkeypatch.setenv("RUM_NATS_USER", "rum_ctl")
    monkeypatch.setenv("RUM_NATS_PASSWORD", "rum-secret")
    monkeypatch.setenv("NATS_TLS_CA_FILE", "/run/secrets/platform-ca.pem")

    loaded = load_rum_settings()

    assert loaded.nats_url == "tls://nats.internal:4422"
    assert loaded.nats_tls_ca_file == "/run/secrets/platform-ca.pem"
    assert "platform-secret" not in loaded.nats_url


def test_empty_platform_nats_stays_unconfigured(monkeypatch):
    monkeypatch.delenv("RUM_NATS_USER", raising=False)
    monkeypatch.delenv("RUM_NATS_PASSWORD", raising=False)
    monkeypatch.delenv("NATS_SERVERS", raising=False)
    monkeypatch.setattr(settings, "NATS_SERVERS", "", raising=False)

    assert load_rum_settings().nats_url == ""


def test_half_rum_credentials_stay_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "NATS_SERVERS", "nats://127.0.0.1:4222", raising=False)
    monkeypatch.setenv("RUM_NATS_USER", "rum_ctl")
    monkeypatch.setenv("RUM_NATS_PASSWORD", "")

    assert load_rum_settings().nats_url == ""
