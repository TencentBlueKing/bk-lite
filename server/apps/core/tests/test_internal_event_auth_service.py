import time

import pytest

pytestmark = pytest.mark.unit


def test_internal_event_auth_rejects_tampering_and_expiry(settings):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "test-secret"
    payload = {"source_id": "nats", "pusher": "lite-monitor", "events": [{"organizations": [3]}]}
    now = int(time.time())

    auth = sign_internal_event("alerts.receive_alert_events", payload, caller="lite-monitor", now=now)

    assert verify_internal_event("alerts.receive_alert_events", payload, auth, caller="lite-monitor", now=now) is True
    assert verify_internal_event("alerts.receive_alert_events", payload, auth, caller="lite-log", now=now) is False
    assert (
        verify_internal_event(
            "alerts.receive_alert_events",
            {**payload, "events": [{"organizations": [99]}]},
            auth,
            caller="lite-monitor",
            now=now,
        )
        is False
    )
    assert verify_internal_event("alerts.receive_alert_events", payload, auth, caller="lite-monitor", now=now + 301) is False


def test_internal_event_auth_accepts_previous_rotation_key(settings, monkeypatch):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "new-secret"
    payload = {"channel_id": 7, "content": {"events": []}}
    now = int(time.time())
    auth = sign_internal_event(
        "system_mgmt.send_msg_with_channel",
        payload,
        caller="lite-log",
        now=now,
        key="old-secret",
    )
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_PREVIOUS_KEY", "old-secret")

    assert (
        verify_internal_event(
            "system_mgmt.send_msg_with_channel",
            payload,
            auth,
            caller="lite-log",
            now=now,
        )
        is True
    )


def test_internal_event_auth_caller_keys_prevent_cross_service_impersonation(settings, monkeypatch):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "shared-fallback"
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_KEY", "monitor-secret")
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_LOG_KEY", "log-secret")
    payload = {"events": [{"organizations": [3]}]}
    now = int(time.time())
    monitor_auth = sign_internal_event("alerts.receive_alert_events", payload, caller="lite-monitor", now=now)
    forged_log_auth = {**monitor_auth, "caller": "lite-log"}
    log_key_claiming_monitor = sign_internal_event(
        "alerts.receive_alert_events",
        payload,
        caller="lite-monitor",
        now=now,
        key="log-secret",
    )

    assert verify_internal_event(
        "alerts.receive_alert_events", payload, monitor_auth, caller="lite-monitor", now=now
    ) is True
    assert verify_internal_event(
        "alerts.receive_alert_events", payload, forged_log_auth, caller="lite-log", now=now
    ) is False
    assert verify_internal_event(
        "alerts.receive_alert_events", payload, log_key_claiming_monitor, caller="lite-monitor", now=now
    ) is False


def test_internal_event_auth_accepts_caller_previous_rotation_key(settings, monkeypatch):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "unrelated-fallback"
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_KEY", "monitor-current")
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_PREVIOUS_KEY", "monitor-previous")
    payload = {"events": [{"organizations": [3]}]}
    now = int(time.time())
    previous_auth = sign_internal_event(
        "alerts.receive_alert_events",
        payload,
        caller="lite-monitor",
        now=now,
        key="monitor-previous",
    )

    assert verify_internal_event(
        "alerts.receive_alert_events", payload, previous_auth, caller="lite-monitor", now=now
    ) is True


def test_internal_event_auth_caller_key_receiver_accepts_global_key_during_migration(settings, monkeypatch):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "global-old-key"
    monkeypatch.delenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", raising=False)
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_KEY", "monitor-new-key")
    payload = {"events": [{"organizations": [3]}]}
    now = int(time.time())
    old_producer_auth = sign_internal_event(
        "alerts.receive_alert_events",
        payload,
        caller="lite-monitor",
        now=now,
        key="global-old-key",
    )

    assert verify_internal_event(
        "alerts.receive_alert_events", payload, old_producer_auth, caller="lite-monitor", now=now
    ) is True


def test_internal_event_auth_rejects_shared_keys_after_strict_caller_key_cutover(settings, monkeypatch):
    from apps.core.utils.internal_event_auth import sign_internal_event, verify_internal_event

    settings.SECRET_KEY = "django-still-nonempty"
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_KEY", "global-old-key")
    monkeypatch.setenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", "false")
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_KEY", "monitor-new-key")
    payload = {"events": [{"organizations": [3]}]}
    now = int(time.time())
    old_global_auth = sign_internal_event(
        "alerts.receive_alert_events",
        payload,
        caller="lite-monitor",
        now=now,
        key="global-old-key",
    )
    old_django_auth = sign_internal_event(
        "alerts.receive_alert_events",
        payload,
        caller="lite-monitor",
        now=now,
        key="django-still-nonempty",
    )

    assert verify_internal_event(
        "alerts.receive_alert_events", payload, old_global_auth, caller="lite-monitor", now=now
    ) is False
    assert verify_internal_event(
        "alerts.receive_alert_events", payload, old_django_auth, caller="lite-monitor", now=now
    ) is False


def test_internal_event_auth_rejects_empty_key(monkeypatch):
    from types import SimpleNamespace

    from apps.core.utils import internal_event_auth

    monkeypatch.setattr(internal_event_auth, "settings", SimpleNamespace(SECRET_KEY=""))
    monkeypatch.delenv("ALERTS_INTERNAL_EVENT_AUTH_KEY", raising=False)
    monkeypatch.delenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_KEY", raising=False)

    with pytest.raises(ValueError, match="key is not configured"):
        internal_event_auth.sign_internal_event("alerts.receive_alert_events", {}, caller="lite-monitor")
    assert internal_event_auth.verify_internal_event("alerts.receive_alert_events", {}, {}, caller="lite-monitor") is False


def test_legacy_internal_event_auth_defaults_to_rolling_compatibility(monkeypatch):
    from apps.core.utils.internal_event_auth import legacy_internal_event_auth_allowed

    monkeypatch.delenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", raising=False)
    assert legacy_internal_event_auth_allowed() is True

    monkeypatch.setenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", "false")
    assert legacy_internal_event_auth_allowed() is False
