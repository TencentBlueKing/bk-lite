import pytest

from apps.rum.services.settings import browser_endpoints, load_rum_settings, normalize_public_origin


def test_public_origin_keeps_scheme_host_and_port():
    assert normalize_public_origin(" HTTPS://BKLite.Example.com:8443/ ") == "https://bklite.example.com:8443"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "bklite.example.com",
        "https://user:secret@bklite.example.com",
        "https://bklite.example.com/rum/v1/collect",
        "https://bklite.example.com?q=1",
        "ftp://bklite.example.com",
    ],
)
def test_public_origin_rejects_non_origins(value):
    assert normalize_public_origin(value) == ""


def test_browser_endpoints_use_fixed_paths():
    assert browser_endpoints("https://bklite.example.com") == {
        "collect_url": "https://bklite.example.com/rum/v1/collect",
        "replay_url": "https://bklite.example.com/rum/v1/replay",
        "sdk_cdn_url": "https://bklite.example.com/rum/bklite-rum-sdk.js",
    }


def test_unset_public_origin_does_not_invent_localhost_urls(monkeypatch):
    monkeypatch.delenv("RUM_PUBLIC_ORIGIN", raising=False)
    monkeypatch.setenv("RUM_COLLECT_URL", "http://127.0.0.1:4319/rum/v1/collect")
    monkeypatch.setenv("RUM_REPLAY_URL", "http://127.0.0.1:4320/rum/v1/replay")
    monkeypatch.setenv("RUM_SDK_CDN_URL", "http://127.0.0.1:3000/rum/bklite-rum-sdk.js")

    loaded = load_rum_settings()

    assert loaded.public_origin == ""
    assert loaded.collect_url == ""
    assert loaded.replay_url == ""
    assert loaded.sdk_cdn_url == ""


def test_public_origin_fills_browser_urls(monkeypatch):
    monkeypatch.setenv("RUM_PUBLIC_ORIGIN", "https://rum.example.com")

    loaded = load_rum_settings()

    assert loaded.public_origin == "https://rum.example.com"
    assert loaded.collect_url == "https://rum.example.com/rum/v1/collect"
    assert loaded.replay_url == "https://rum.example.com/rum/v1/replay"
    assert loaded.sdk_cdn_url == "https://rum.example.com/rum/bklite-rum-sdk.js"
