import pytest

from apps.rum.services.settings import load_rum_settings, normalize_nats_url


def test_production_keeps_tls_without_userinfo():
    assert normalize_nats_url("tls://nats.internal:4222", insecure=False) == "tls://nats.internal:4222"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "nats://127.0.0.1:4222",
        "nats://rum_ctl:secret@127.0.0.1:4222",
        "tls://rum_ctl:secret@nats.internal:4222",
        "http://nats.internal:4222",
    ],
)
def test_production_drops_plain_or_credentialed_urls(value):
    assert normalize_nats_url(value, insecure=False) == ""


def test_insecure_keeps_local_nats_url_with_password():
    raw = "nats://rum_ctl:secret@127.0.0.1:14222"
    assert normalize_nats_url(raw, insecure=True) == raw


def test_insecure_still_rejects_tls_userinfo():
    assert normalize_nats_url("tls://rum_ctl:secret@nats.internal:4222", insecure=True) == ""


def test_load_drops_credentialed_url_unless_insecure(monkeypatch):
    monkeypatch.setenv("RUM_NATS_URL", "nats://rum_ctl:secret@127.0.0.1:14222")
    monkeypatch.delenv("RUM_NATS_INSECURE", raising=False)

    assert load_rum_settings().nats_url == ""

    monkeypatch.setenv("RUM_NATS_INSECURE", "true")
    assert load_rum_settings().nats_url == "nats://rum_ctl:secret@127.0.0.1:14222"


def test_empty_nats_url_stays_unconfigured(monkeypatch):
    monkeypatch.setenv("RUM_NATS_URL", "")
    monkeypatch.delenv("RUM_NATS_INSECURE", raising=False)

    assert load_rum_settings().nats_url == ""
