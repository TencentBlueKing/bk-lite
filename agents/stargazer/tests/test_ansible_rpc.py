# -*- coding: utf-8 -*-
"""ansible_adhoc 不能把 Executor 的入队回执当成命令输出。"""

import json
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
