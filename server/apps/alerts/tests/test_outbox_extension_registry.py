from types import SimpleNamespace

import pytest

from apps.alerts.extensions.outbox import outbox_handlers
from apps.alerts.service.outbox import _deliver_payload


@pytest.fixture(autouse=True)
def preserve_outbox_extension_registry():
    original_handlers = dict(outbox_handlers._handlers)
    original_observers = dict(outbox_handlers._observers)
    try:
        yield
    finally:
        outbox_handlers.clear()
        outbox_handlers._handlers.update(original_handlers)
        outbox_handlers._observers.update(original_observers)


def test_outbox_extension_dispatches_delivery_with_claim():
    calls = []
    handler = SimpleNamespace(
        deliver=lambda payload, delivery_claim=None: calls.append((payload, delivery_claim)),
    )
    outbox_handlers.clear()
    outbox_handlers.register("enterprise.example", handler)

    assert outbox_handlers.deliver(
        "enterprise.example",
        {"value": 1},
        delivery_claim={"record_id": 7, "generation": 2},
    )
    assert calls == [
        ({"value": 1}, {"record_id": 7, "generation": 2}),
    ]


def test_outbox_extension_uses_handler_scheduler_when_present():
    calls = []
    handler = SimpleNamespace(
        deliver=lambda payload, delivery_claim=None: None,
        schedule=lambda record_id: calls.append(record_id),
    )
    outbox_handlers.clear()
    outbox_handlers.register("enterprise.example", handler)

    assert outbox_handlers.schedule("enterprise.example", 17)
    assert calls == [17]
    assert not outbox_handlers.schedule("community.unknown", 18)


def test_outbox_extension_notifies_exhaustion_without_leaking_handler_failure(caplog):
    handler = SimpleNamespace(
        deliver=lambda payload, delivery_claim=None: None,
        exhausted=lambda payload, error: (_ for _ in ()).throw(RuntimeError("secret")),
    )
    outbox_handlers.clear()
    outbox_handlers.register("enterprise.example", handler)

    assert outbox_handlers.notify_exhausted(
        "enterprise.example",
        {"token": "must-not-log"},
        "credential-error",
        record_id=19,
    )
    assert "outbox extension exhausted hook failed" in caplog.text
    assert "must-not-log" not in caplog.text
    assert "credential-error" not in caplog.text


def test_alert_outbox_dispatches_registered_extension_without_knowing_its_kind():
    calls = []
    handler = SimpleNamespace(
        deliver=lambda payload, delivery_claim=None: calls.append((payload, delivery_claim)),
    )
    outbox_handlers.clear()
    outbox_handlers.register("enterprise.example", handler)

    _deliver_payload(
        "enterprise.example",
        {"group_id": 11},
        delivery_claim={"record_id": 23, "generation": 4},
    )

    assert calls == [
        ({"group_id": 11}, {"record_id": 23, "generation": 4}),
    ]
