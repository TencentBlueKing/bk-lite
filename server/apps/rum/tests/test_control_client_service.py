"""NatsControlClient: one process-level connection, lazy reconnect, transport → unavailable."""

from __future__ import annotations

import json

import pytest

from apps.rum.services.control import ControlError, NatsControlClient


class _Msg:
    def __init__(self, body: dict):
        self.data = json.dumps(body).encode("utf-8")


class _FakeNC:
    def __init__(self, responder):
        self.is_connected = True
        self.closed = False
        self.requests: list[tuple[str, dict]] = []
        self._responder = responder

    async def request(self, subject, data, timeout):
        envelope = json.loads(data.decode("utf-8"))
        self.requests.append((subject, envelope))
        return _Msg(self._responder(subject, envelope))

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_nats(monkeypatch):
    import nats

    state = {"connects": 0, "clients": [], "fail": False}

    def responder(subject, envelope):
        return {"requestId": envelope["requestId"], "revision": 7, "data": {"echo": subject}}

    async def connect(url, **kwargs):
        state["connects"] += 1
        if state["fail"]:
            raise OSError("connection refused")
        client = _FakeNC(responder)
        state["clients"].append(client)
        return client

    monkeypatch.setattr(nats, "connect", connect)
    return state


def test_requests_reuse_one_connection(fake_nats):
    client = NatsControlClient("nats://ctl:pw@127.0.0.1:4222", timeout_seconds=2)

    revision, data = client.request("rum.v1.control.application.list", "tester", {})
    client.request("rum.v1.control.application.get", "tester", {"application": "a"}, expected_revision=3)

    assert (revision, data) == (7, {"echo": "rum.v1.control.application.list"})
    assert fake_nats["connects"] == 1
    nc = fake_nats["clients"][0]
    assert [subject for subject, _ in nc.requests] == [
        "rum.v1.control.application.list",
        "rum.v1.control.application.get",
    ]
    envelope = nc.requests[1][1]
    assert envelope["apiVersion"] == "rum.control/v1"
    assert envelope["actor"] == "tester"
    assert envelope["expectedRevision"] == 3
    assert envelope["requestId"] and envelope["idempotencyKey"]
    assert nc.requests[0][1]["requestId"] != envelope["requestId"]


def test_reconnects_after_connection_drops(fake_nats):
    client = NatsControlClient("nats://127.0.0.1:4222", timeout_seconds=2)
    client.request("rum.v1.control.application.list", "tester", {})
    first = fake_nats["clients"][0]
    first.is_connected = False

    client.request("rum.v1.control.application.list", "tester", {})

    assert fake_nats["connects"] == 2
    assert first.closed is True
    assert fake_nats["clients"][1].requests


def test_transport_failure_maps_to_unavailable_and_recovers(fake_nats):
    client = NatsControlClient("nats://127.0.0.1:4222", timeout_seconds=1)
    fake_nats["fail"] = True
    with pytest.raises(ControlError) as excinfo:
        client.request("rum.v1.control.application.list", "tester", {})
    assert excinfo.value.code == "unavailable"

    fake_nats["fail"] = False
    revision, _ = client.request("rum.v1.control.application.list", "tester", {})
    assert revision == 7


def test_stuck_connection_is_replaced_on_the_same_request(monkeypatch):
    import nats

    connects = {"n": 0}

    async def connect(url, **kwargs):
        connects["n"] += 1
        if connects["n"] == 1:
            stuck = _FakeNC(lambda subject, envelope: {})

            async def request(subject, data, timeout):
                raise TimeoutError("nats: timeout")

            stuck.request = request
            return stuck
        return _FakeNC(lambda subject, envelope: {"requestId": envelope["requestId"], "revision": 7, "data": {"ok": True}})

    monkeypatch.setattr(nats, "connect", connect)
    client = NatsControlClient("nats://127.0.0.1:4222", timeout_seconds=1)
    revision, data = client.request("rum.v1.control.application.list", "tester", {})
    assert revision == 7
    assert data == {"ok": True}
    assert connects["n"] == 2


def test_controller_error_envelope_is_surfaced(monkeypatch):
    import nats

    def responder(subject, envelope):
        return {
            "requestId": envelope["requestId"],
            "error": {"code": "revision_conflict", "message": "expected revision does not match"},
        }

    async def connect(url, **kwargs):
        return _FakeNC(responder)

    monkeypatch.setattr(nats, "connect", connect)
    client = NatsControlClient("nats://127.0.0.1:4222", timeout_seconds=1)
    with pytest.raises(ControlError) as excinfo:
        client.request("rum.v1.control.application.apply", "tester", {}, expected_revision=1)
    assert excinfo.value.code == "revision_conflict"
