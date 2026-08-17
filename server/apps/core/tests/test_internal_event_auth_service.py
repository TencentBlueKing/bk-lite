import time

import pytest

pytestmark = pytest.mark.unit


def test_internal_event_auth_rejects_tampering_and_expiry(settings):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "test-secret"
    payload = {"source_id": "nats", "pusher": "lite-monitor", "events": [{"organizations": [3]}]}
    now = int(time.time())

    auth = sign_internal_event("alerts.receive_alert_events", payload, now=now)

    assert verify_internal_event("alerts.receive_alert_events", payload, auth, now=now) is True
    assert (
        verify_internal_event(
            "alerts.receive_alert_events",
            {**payload, "events": [{"organizations": [99]}]},
            auth,
            now=now,
        )
        is False
    )
    assert verify_internal_event("alerts.receive_alert_events", payload, auth, now=now + 301) is False


def test_internal_event_auth_accepts_previous_rotation_key(settings, monkeypatch):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "new-secret"
    payload = {"channel_id": 7, "content": {"events": []}}
    now = int(time.time())
    auth = sign_internal_event(
        "system_mgmt.send_msg_with_channel",
        payload,
        now=now,
        key="old-secret",
    )
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_PREVIOUS_KEY", "old-secret")

    assert (
        verify_internal_event(
            "system_mgmt.send_msg_with_channel",
            payload,
            auth,
            now=now,
        )
        is True
    )


def test_legacy_internal_event_auth_requires_explicit_rollback_switch(monkeypatch):
    from apps.core.utils.internal_event_auth import legacy_internal_event_auth_allowed

    monkeypatch.delenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", raising=False)
    assert legacy_internal_event_auth_allowed() is False

    monkeypatch.setenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", "true")
    assert legacy_internal_event_auth_allowed() is True
