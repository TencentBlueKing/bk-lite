"""get_analytics must not pin UnavailableAnalytics forever after a brief outage."""

from apps.rum.services import analytics as analytics_mod
from apps.rum.services.analytics import UnavailableAnalytics, get_analytics, set_analytics


class _Ready:
    def available(self):
        return True


def test_get_analytics_retries_after_unavailable(monkeypatch):
    set_analytics(None)
    calls = {"n": 0}

    def fake_build():
        calls["n"] += 1
        if calls["n"] == 1:
            return UnavailableAnalytics()
        return _Ready()

    monkeypatch.setattr(analytics_mod, "_build_analytics", fake_build)
    monkeypatch.setattr(analytics_mod, "_UNAVAILABLE_RETRY_SECONDS", 0.0)

    first = get_analytics()
    assert isinstance(first, UnavailableAnalytics)
    second = get_analytics()
    assert second.available() is True
    assert calls["n"] == 2
    set_analytics(None)
