# -*- coding: utf-8 -*-
"""ansible_adhoc 不能把 Executor 的入队回执当成命令输出。"""

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.infra import ansible_rpc  # noqa: E402


def _queued_ack(task_id):
    return {
        "success": True,
        "result": {
            "accepted": True,
            "status": "queued",
            "task_id": task_id,
        },
    }


def _query(status, stored):
    return {
        "success": True,
        "result": {
            "task_id": "task-1",
            "status": status,
            "execution_status": status,
            "result": stored,
        },
    }


@pytest.mark.asyncio
async def test_callback_caller_returns_queued_ack_without_waiting(monkeypatch):
    calls = []

    async def fake_request(subject, payload, timeout):
        calls.append(subject)
        return _queued_ack("task-1")

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)

    result = await ansible_rpc.ansible_adhoc(
        "node-1",
        [{"host": "10.0.0.8"}],
        module="win_shell",
        callback={"subject": "callback.pc"},
        task_id="task-1",
        execute_timeout=5,
    )

    assert result["result"]["status"] == "queued"
    assert calls == ["ansible.adhoc.node-1"]


@pytest.mark.asyncio
async def test_sync_caller_waits_until_execution_result(monkeypatch):
    calls = []
    queries = [
        _query("running", {}),
        _query(
            "success",
            {
                "success": True,
                "status": "success",
                "result": [{"host": "10.0.0.8", "stdout": '{"pc": []}'}],
                "error": "",
                "task_id": "task-1",
            },
        ),
    ]

    async def fake_request(subject, payload, timeout):
        calls.append((subject, json.loads(payload)))
        if subject.startswith("ansible.adhoc."):
            return _queued_ack("task-1")
        return queries.pop(0)

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)
    monkeypatch.setattr(ansible_rpc.asyncio, "sleep", fake_sleep)

    result = await ansible_rpc.ansible_adhoc(
        "node-1",
        [{"host": "10.0.0.8"}],
        module="win_shell",
        task_id="task-1",
        execute_timeout=5,
    )

    assert result["success"] is True
    assert result["result"] == [{"host": "10.0.0.8", "stdout": '{"pc": []}'}]
    assert calls[0][0] == "ansible.adhoc.node-1"
    assert calls[1][0] == "ansible.task.query.node-1"
    assert calls[1][1]["args"][0]["task_id"] == "task-1"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_sync_caller_times_out_while_task_still_running(monkeypatch):
    async def fake_request(subject, payload, timeout):
        if subject.startswith("ansible.adhoc."):
            return _queued_ack("task-1")
        return _query("running", {})

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)
    monkeypatch.setattr(ansible_rpc.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ansible_rpc.time, "monotonic", lambda: 0)
    original_deadline_check = ansible_rpc._wait_for_adhoc_result

    async def expire_immediately(node_id, task_id, deadline):
        return await original_deadline_check(node_id, task_id, deadline=0)

    monkeypatch.setattr(ansible_rpc, "_wait_for_adhoc_result", expire_immediately)

    with pytest.raises(TimeoutError, match="task-1"):
        await ansible_rpc.ansible_adhoc(
            "node-1",
            [{"host": "10.0.0.8"}],
            task_id="task-1",
            execute_timeout=5,
        )


def _success_body():
    return {
        "success": True,
        "status": "success",
        "result": [{"host": "10.0.0.8", "stdout": "{}"}],
        "error": "",
        "task_id": "task-1",
    }


@pytest.mark.asyncio
async def test_callback_caller_keeps_full_accept_budget(monkeypatch):
    seen = {}

    async def fake_request(subject, payload, timeout):
        seen["timeout"] = timeout
        return _queued_ack("task-1")

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)

    await ansible_rpc.ansible_adhoc(
        "node-1",
        [{"host": "10.0.0.8"}],
        callback={"subject": "callback.host"},
        task_id="task-1",
        execute_timeout=60,
    )

    assert seen["timeout"] == 90


@pytest.mark.asyncio
async def test_sync_accept_timeout_is_capped(monkeypatch):
    timeouts = []

    async def fake_request(subject, payload, timeout):
        timeouts.append(timeout)
        if subject.startswith("ansible.adhoc."):
            return _queued_ack("task-1")
        return _query("success", _success_body())

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)
    monkeypatch.setattr(ansible_rpc.asyncio, "sleep", fake_sleep)

    await ansible_rpc.ansible_adhoc(
        "node-1",
        [{"host": "10.0.0.8"}],
        task_id="task-1",
        execute_timeout=60,
    )

    assert timeouts[0] == 30


@pytest.mark.asyncio
async def test_inline_result_is_returned_without_query(monkeypatch):
    calls = []
    inline = {"success": True, "result": [{"stdout": "ok"}]}

    async def fake_request(subject, payload, timeout):
        calls.append(subject)
        return inline

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)

    result = await ansible_rpc.ansible_adhoc(
        "node-1",
        [{"host": "10.0.0.8"}],
        task_id="task-1",
        execute_timeout=5,
    )

    assert result == inline
    assert calls == ["ansible.adhoc.node-1"]


@pytest.mark.asyncio
async def test_query_not_found_fails_without_polling(monkeypatch, caplog):
    secret = "password=SENTINEL-QUERY-SECRET"
    sleeps = []
    test_logger = logging.getLogger("test.stargazer.ansible_rpc.not_found")

    async def fake_request(subject, payload, timeout):
        if subject.startswith("ansible.adhoc."):
            return _queued_ack("task-1")
        return {"success": False, "result": "", "error": f"task not found: task-1 {secret}"}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)
    monkeypatch.setattr(ansible_rpc.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ansible_rpc, "logger", test_logger)

    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        with pytest.raises(RuntimeError, match="task not found"):
            await ansible_rpc.ansible_adhoc(
                "node-1",
                [{"host": "10.0.0.8"}],
                task_id="task-1",
                execute_timeout=60,
            )

    assert sleeps == []
    record = next(item for item in caplog.records if item.msg == ansible_rpc._ADHOC_QUERY_FAILED_LOG)
    assert record.args == ("task-1",)
    assert record.exc_info is None
    assert record.getMessage() == "event=ansible_adhoc_query_failed task_id=task-1 failed_stage=adhoc_query error_type=RuntimeError"
    joined = "\n".join(item.getMessage() for item in caplog.records)
    assert secret not in joined


@pytest.mark.asyncio
async def test_query_timeout_keeps_cause_and_log_template(monkeypatch, caplog):
    secret = "password=SENTINEL-TIMEOUT-SECRET"
    test_logger = logging.getLogger("test.stargazer.ansible_rpc.timeout")
    clock = {"now": 1000.0}
    original = TimeoutError(secret)

    async def fake_request(subject, payload, timeout):
        if subject.startswith("ansible.adhoc."):
            return _queued_ack("task-1")
        clock["now"] = 2000.0
        raise original

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)
    monkeypatch.setattr(ansible_rpc.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(ansible_rpc, "logger", test_logger)

    with caplog.at_level(logging.WARNING, logger=test_logger.name):
        with pytest.raises(TimeoutError, match="task-1") as caught:
            await ansible_rpc.ansible_adhoc(
                "node-1",
                [{"host": "10.0.0.8"}],
                task_id="task-1",
                execute_timeout=5,
            )

    assert caught.value.__cause__ is original
    record = next(item for item in caplog.records if item.msg == ansible_rpc._ADHOC_QUERY_TIMEOUT_LOG)
    assert record.args == ("task-1", "TimeoutError")
    assert record.exc_info is None
    assert record.getMessage() == ("event=ansible_adhoc_query_timeout task_id=task-1 failed_stage=adhoc_query error_type=TimeoutError")
    joined = "\n".join(item.getMessage() for item in caplog.records)
    assert secret not in joined


@pytest.mark.asyncio
async def test_poll_uses_backoff(monkeypatch):
    sleeps = []
    queries = [
        _query("running", {}),
        _query("running", {}),
        _query("running", {}),
        _query("success", _success_body()),
    ]

    async def fake_request(subject, payload, timeout):
        if subject.startswith("ansible.adhoc."):
            return _queued_ack("task-1")
        return queries.pop(0)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(ansible_rpc, "nats_request", fake_request)
    monkeypatch.setattr(ansible_rpc.asyncio, "sleep", fake_sleep)

    result = await ansible_rpc.ansible_adhoc(
        "node-1",
        [{"host": "10.0.0.8"}],
        task_id="task-1",
        execute_timeout=60,
    )

    assert result["success"] is True
    assert sleeps == [0.5, 1.0, 2.0]
