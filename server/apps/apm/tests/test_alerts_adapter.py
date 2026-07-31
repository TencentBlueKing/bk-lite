import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

from apps.apm.adapters.alerts import (
    APM_ALERT_PUSHER,
    APM_ALERT_SOURCE_ID,
    AlertsNatsPublisher,
    reconcile_apm_alert_source,
)
from apps.apm.services.contracts import ApmAlertEvent

class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def run(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return self.response


def _event():
    return ApmAlertEvent(
        event_key="event-1",
        external_id="alert-1",
        status="created",
        severity="error",
        title="APM 告警",
        occurred_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        payload={"title": "APM 告警", "action": "created"},
    )


def test_nats_publisher_uses_dedicated_source_and_pusher():
    client = FakeClient(
        {
            "result": True,
            "data": {"ingestion": {"accepted": 1, "skipped": 0, "errored": 0}},
        }
    )

    result = AlertsNatsPublisher(client=client).publish([_event()])

    assert result.accepted == 1
    assert client.calls == [
        (
            "receive_alert_events",
            {
                "source_id": APM_ALERT_SOURCE_ID,
                "pusher": APM_ALERT_PUSHER,
                "events": [{"title": "APM 告警", "action": "created"}],
            },
        )
    ]


def test_nats_publisher_treats_clean_ingress_skip_as_idempotent_duplicate():
    client = FakeClient(
        {
            "result": False,
            "data": {"ingestion": {"accepted": 0, "skipped": 1, "errored": 0}},
        }
    )

    result = AlertsNatsPublisher(client=client).publish([_event()])

    assert result.duplicates == 1
    assert result.failed == 0


def test_runtime_source_reconciliation_is_idempotent_and_reactivates_source(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.source = None

        def update_or_create(self, *, source_id, defaults):
            created = self.source is None
            if created:
                self.source = SimpleNamespace(pk=1, source_id=source_id)
            for key, value in defaults.items():
                setattr(self.source, key, value)
            return self.source, created

    manager = FakeManager()
    source_module = ModuleType("apps.alerts.common.source_adapter.constants")
    source_module.DEFAULT_SOURCE_CONFIG = {"event_fields_mapping": {"title": "title"}}
    constants_module = ModuleType("apps.alerts.constants.constants")
    constants_module.AlertAccessType = SimpleNamespace(BUILT_IN="built_in")
    constants_module.AlertsSourceTypes = SimpleNamespace(NATS="nats")
    model_module = ModuleType("apps.alerts.models.alert_source")
    model_module.AlertSource = SimpleNamespace(all_objects=manager)
    monkeypatch.setitem(sys.modules, source_module.__name__, source_module)
    monkeypatch.setitem(sys.modules, constants_module.__name__, constants_module)
    monkeypatch.setitem(sys.modules, model_module.__name__, model_module)

    source, created = reconcile_apm_alert_source()
    assert created is True
    assert source.source_id == APM_ALERT_SOURCE_ID
    assert source.source_type == "nats"

    source.is_active = False
    source.is_effective = False
    source.is_delete = True
    reconciled, created_again = reconcile_apm_alert_source()

    assert created_again is False
    assert reconciled.pk == source.pk
    assert reconciled.is_active is True
    assert reconciled.is_effective is True
    assert reconciled.is_delete is False
    assert manager.source is reconciled
