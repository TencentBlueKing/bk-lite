import importlib
import sys
from types import SimpleNamespace

import api.collect as collect_api
import pytest
from core.collection.application import CollectionApplication
from core.collection.enums import SubmissionStatus
from core.collection.runtime import Submission
from core.infra import nats as nats_module
from core.infra.control_transport import NatsControlTransport


class _FakeNatsRegistry:
    service_name = "default_stargazer"

    def register_handler(self, _subject, queue=None):
        return lambda handler: handler


_previous_nats_instance = nats_module._nats_instance
nats_module._nats_instance = _FakeNatsRegistry()
sys.modules.pop("service.nats_server", None)
access_check = importlib.import_module("service.nats_server").access_check
nats_module._nats_instance = _previous_nats_instance


class _Application:
    def __init__(self):
        self.submitted = []
        self.admitted = []

    async def submit(self, request):
        self.submitted.append(request)
        return Submission(task_id=request.task_id, status=SubmissionStatus.ACCEPTED, fence=1)

    async def admit_access_check(self, request):
        self.admitted.append(request)
        return {"status": "accepted", "error_code": ""}


@pytest.mark.asyncio
async def test_http_collect_info_cannot_switch_itself_to_access_check(monkeypatch):
    app = _Application()
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)
    request = SimpleNamespace(method="GET", path="/api/collect/collect_info", query_string="", headers={})

    await collect_api._submit_collection_run(
        request,
        {"model_id": "mysql", "hosts": "10.0.0.8", "run_purpose": "access_check"},
        "mysql",
    )

    assert app.admitted == []
    assert app.submitted[0].access_check is False


@pytest.mark.asyncio
async def test_access_check_purpose_calls_admit_not_submit(monkeypatch):
    app = _Application()
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: app)

    result = await collect_api.run_collect_info(
        {"model_id": "mysql", "hosts": "10.0.0.8", "check_id": "6", "collect_task_id": "50"},
        purpose="access_check",
        task_id="access-check-6",
    )

    assert result["status"] == "accepted"
    assert app.submitted == []
    assert app.admitted[0].access_check is True
    assert app.admitted[0].params["check_id"] == "6"


@pytest.mark.asyncio
async def test_nats_access_check_replies_without_rows(monkeypatch):
    seen = {}

    async def fake_run(params, *, purpose, task_id):
        seen["purpose"] = purpose
        seen["task_id"] = task_id
        seen["password"] = params.get("password")
        return {"status": "accepted", "error_code": ""}

    monkeypatch.setattr("api.collect.run_collect_info", fake_run)

    result = await access_check(
        {
            "model_id": "mysql",
            "check_id": "6",
            "collect_task_id": "50",
            "password": "secret-value",
        }
    )

    assert result == {"status": "accepted", "error_code": ""}
    assert "rows" not in result
    assert seen["purpose"] == "access_check"
    assert seen["task_id"] == "access-check-6"
    assert seen["password"] == "secret-value"


@pytest.mark.asyncio
async def test_nats_access_check_rejects_without_identity():
    result = await access_check({"model_id": "mysql", "password": "secret-value"})

    assert result == {"status": "rejected", "error_code": "invalid_request"}


@pytest.mark.asyncio
async def test_callback_request_uses_registered_subject():
    requested = []

    async def request(subject, envelope, timeout):
        requested.append((subject, envelope, timeout))
        return {"success": True}

    transport = NatsControlTransport(namespace="bklite", request=request)
    await transport.request_collection_callback(
        "receive_access_check_result",
        {"check_id": "6", "collect_task_id": "50", "status": "finished", "rows": []},
        timeout=10,
    )

    assert requested[0][0] == "bklite.receive_access_check_result"
    assert requested[0][1]["kwargs"]["data"]["check_id"] == "6"
    assert requested[0][2] == 10


@pytest.mark.asyncio
async def test_terminal_callback_retries_until_accepted(monkeypatch):
    calls = []

    async def request_collection_callback(subject, payload, timeout):
        calls.append(payload["check_id"])
        if len(calls) == 1:
            return {"success": False}
        return {"success": True, "result": {"accepted": True, "check_id": "6"}}

    monkeypatch.setattr(
        "core.infra.control_transport.get_control_transport",
        lambda: SimpleNamespace(request_collection_callback=request_collection_callback),
    )
    app = SimpleNamespace(settings=SimpleNamespace(publish_max_attempts=2))
    request = SimpleNamespace(params={"check_id": "6", "collect_task_id": "50"})
    row = SimpleNamespace(
        target="10.0.0.8",
        credential_id="credential-1",
        credential_name="凭据 1",
        conclusion="credential_ok",
        detail_code="",
        attempted=True,
    )

    await CollectionApplication._publish_access_check_terminal(app, request, "finished", "", [row])

    assert calls == ["6", "6"]
