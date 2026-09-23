"""CI sourcemap ingest is unauthenticated; it must be throttled per source IP."""

from __future__ import annotations

from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIRequestFactory

from apps.rum.views.releases import RumSourcemapIngestThrottle, RumSourcemapIngestView


def test_ingest_is_throttled_per_ip(monkeypatch):
    monkeypatch.setattr(RumSourcemapIngestThrottle, "THROTTLE_RATES", {"rum_sourcemap_ingest": "2/minute"})
    monkeypatch.setattr(RumSourcemapIngestThrottle, "cache", LocMemCache("rum-ingest-test", {}))
    view = RumSourcemapIngestView.as_view()
    factory = APIRequestFactory()

    def post(ip: str):
        request = factory.post("/api/v1/rum/sourcemaps/ingest/", data=b"{}", content_type="application/json")
        request.META["REMOTE_ADDR"] = ip
        return view(request)

    # Missing params → 400 from the service, never 500; the throttle counts each attempt.
    assert post("10.0.0.1").status_code == 400
    assert post("10.0.0.1").status_code == 400
    throttled = post("10.0.0.1")
    assert throttled.status_code == 429
    assert "Retry-After" in throttled

    # A different client is not affected.
    assert post("10.0.0.2").status_code == 400
