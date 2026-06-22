import asyncio
import importlib
import sys
from pathlib import Path

from sanic import Sanic


sys.path.insert(0, str(Path(__file__).parent.parent))


def test_nats_server_registers_collect_credential_push_loop_on_import(monkeypatch):
    from core import nats as nats_module

    app = Sanic("Stargazer")
    registered_subjects = []

    class FakeNATS:
        def register_handler(self, subject, queue=None):
            registered_subjects.append(subject)

            def decorator(func):
                return func

            return decorator

    monkeypatch.setattr(nats_module, "_nats_instance", FakeNATS())
    monkeypatch.setattr(Sanic, "get_app", classmethod(lambda cls, name, *args, **kwargs: app))
    sys.modules.pop("service.nats_server", None)

    importlib.import_module("service.nats_server")

    listener_events = {
        future_listener.event: future_listener.listener.__name__
        for future_listener in app._future_listeners
        if future_listener.listener.__name__
        in {"start_collect_credential_result_push_loop", "stop_collect_credential_result_push_loop"}
    }

    assert listener_events == {}
    assert "list_collect_credential_results" not in registered_subjects


def test_collect_credential_push_loop_registers_on_dedicated_module(monkeypatch):
    app = Sanic("StargazerPushLoop")

    sys.modules.pop("service.collect_credential_result_push_task", None)
    push_task_module = importlib.import_module("service.collect_credential_result_push_task")

    push_task_module.register_collect_credential_result_push_loop(app)

    listener_events = {
        future_listener.event: future_listener.listener.__name__
        for future_listener in app._future_listeners
        if future_listener.listener.__name__
        in {"start_collect_credential_result_push_loop", "stop_collect_credential_result_push_loop"}
    }

    assert listener_events == {
        "before_server_start": "start_collect_credential_result_push_loop",
        "after_server_stop": "stop_collect_credential_result_push_loop",
    }


def test_push_cycle_logs_when_no_results(monkeypatch):
    push_task_module = importlib.import_module("service.collect_credential_result_push_task")

    async def fake_push_once():
        return {"pushed": 0, "next_since": "2026-06-04T10:05:00+00:00"}

    info_logs = []

    def fake_info(message, *args, **kwargs):
        info_logs.append(message % args if args else message)

    monkeypatch.setattr(
        "service.collect_credential_result_push_task.CollectCredentialResultPushService.push_once",
        fake_push_once,
    )
    monkeypatch.setattr("service.collect_credential_result_push_task.logger.info", fake_info)

    asyncio.run(push_task_module.push_collect_credential_results_once())

    assert info_logs == [
        "No collect credential results ready for CMDB push, next_since=2026-06-04T10:05:00+00:00"
    ]


def test_list_collect_credential_results_returns_bounded_payload(monkeypatch):
    from service.collect_credential_result_push_service import CollectCredentialResultPushService

    events = [
        {
            "collect_task_id": 1,
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "success": True,
            "finished_at": "2026-06-04T10:00:00+00:00",
        },
        {
            "collect_task_id": 1,
            "host": "10.0.0.2",
            "credential_id": "cred-1",
            "success": False,
            "finished_at": "2026-06-04T10:05:00+00:00",
        },
    ]

    async def fake_list_result_events(since, limit):
        assert since == "2026-06-04T09:00:00+00:00"
        assert limit == 2000
        return events

    monkeypatch.setattr(
        "service.collect_credential_result_push_service.CredentialStateCache.list_result_events", fake_list_result_events
    )

    result = asyncio.run(
        CollectCredentialResultPushService.list_results(
            since="2026-06-04T09:00:00+00:00",
            limit=99999,
        )
    )

    assert result == {
        "results": events,
        "next_since": "2026-06-04T10:05:00+00:00",
    }


def test_push_collect_credential_results_once_publishes_batch_and_updates_cursor(monkeypatch):
    from service.collect_credential_result_push_service import CollectCredentialResultPushService

    published = {}
    cursor_updates = []
    events = [
        {
            "collect_task_id": 1,
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "success": True,
            "finished_at": "2026-06-04T10:00:00+00:00",
        },
        {
            "collect_task_id": 1,
            "host": "10.0.0.2",
            "credential_id": "cred-1",
            "success": False,
            "finished_at": "2026-06-04T10:05:00+00:00",
        },
    ]

    async def fake_get_push_cursor():
        return "2026-06-04T09:00:00+00:00"

    async def fake_list_result_events(since, limit):
        assert since == "2026-06-04T09:00:00+00:00"
        assert limit == 1000
        return events

    async def fake_publish(subject, payload):
        published["subject"] = subject
        published["payload"] = payload

    async def fake_set_push_cursor(since):
        cursor_updates.append(since)

    monkeypatch.setattr(
        "service.collect_credential_result_push_service.CredentialStateCache.get_push_cursor", fake_get_push_cursor
    )
    monkeypatch.setattr(
        "service.collect_credential_result_push_service.CredentialStateCache.list_result_events", fake_list_result_events
    )
    monkeypatch.setattr(
        "service.collect_credential_result_push_service.CredentialStateCache.set_push_cursor", fake_set_push_cursor
    )
    monkeypatch.setattr("service.collect_credential_result_push_service.nats_publish", fake_publish)

    result = asyncio.run(CollectCredentialResultPushService.push_once())

    assert result == {"pushed": 2, "next_since": "2026-06-04T10:05:00+00:00"}
    assert published["subject"] == "bklite.receive_collect_credential_result"
    assert published["payload"]["kwargs"]["data"]["events"] == events
    assert published["payload"]["kwargs"]["data"]["next_since"] == "2026-06-04T10:05:00+00:00"
    assert cursor_updates == ["2026-06-04T10:05:00+00:00"]