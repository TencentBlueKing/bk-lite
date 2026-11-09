import requests

from apps.itsm.flowable.client import FlowableClient, FlowableError


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self._payload


def test_client_retries_then_returns_json(monkeypatch):
    calls = {"count": 0}

    def fake_request(self, method, url, timeout, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.ConnectionError("down")
        return FakeResponse(200, {"data": []})

    monkeypatch.setattr(requests.Session, "request", fake_request)
    assert FlowableClient("http://flowable", "admin", "secret").list_deployments() == {"data": []}
    assert calls["count"] == 2


def test_client_raises_flowable_error(monkeypatch):
    monkeypatch.setattr(requests.Session, "request", lambda *args, **kwargs: FakeResponse(404, text="missing"))
    try:
        FlowableClient("http://flowable", "admin", "secret").list_tasks("1")
    except FlowableError as exc:
        assert exc.status == 404
    else:
        raise AssertionError("should fail")
