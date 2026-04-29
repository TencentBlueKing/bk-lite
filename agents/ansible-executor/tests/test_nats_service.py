import asyncio

import pytest

from core.config import ServiceConfig
from service.nats_service import AnsibleNATSService, QueuedTask


class DummyMessage:
    def __init__(self):
        self.in_progress_calls = 0

    async def in_progress(self):
        self.in_progress_calls += 1


@pytest.mark.asyncio
async def test_keepalive_uses_backoff_deadline(tmp_path):
    service = AnsibleNATSService(
        ServiceConfig(
            nats_servers=["nats://127.0.0.1:4222"],
            nats_instance_id="default",
            js_stream="BK_ANS_EXEC_TASKS",
            js_subject_prefix="bk.ans_exec.tasks",
            js_durable="ansible-executor",
            js_ack_wait=300,
            js_backoff=[5, 15, 30, 60],
            state_db_path=str(tmp_path / "task.db"),
        )
    )

    assert service._effective_ack_deadline_seconds() == 5.0
    assert service._heartbeat_interval_seconds() == 2.0


@pytest.mark.asyncio
async def test_keepalive_renews_lease_and_sends_progress(tmp_path):
    service = AnsibleNATSService(
        ServiceConfig(
            nats_servers=["nats://127.0.0.1:4222"],
            nats_instance_id="default",
            js_stream="BK_ANS_EXEC_TASKS",
            js_subject_prefix="bk.ans_exec.tasks",
            js_durable="ansible-executor",
            js_ack_wait=2,
            js_backoff=None,
            state_db_path=str(tmp_path / "task.db"),
        )
    )
    service.task_store.create_if_absent("task-1", "queued", {"task_id": "task-1"}, {}, service._now_iso())
    service.task_store.claim_task("task-1", "owner-a", service._lease_expiry_iso(), service._now_iso())
    message = DummyMessage()

    keepalive = asyncio.create_task(service._keep_message_in_progress(message, "task-1", "owner-a"))
    await asyncio.sleep(1.2)
    keepalive.cancel()
    with pytest.raises(asyncio.CancelledError):
        await keepalive

    task = service.task_store.get_task("task-1")
    assert message.in_progress_calls >= 1
    assert task["lease_owner"] == "owner-a"
    assert task["heartbeat_at"] is not None


@pytest.mark.asyncio
async def test_run_task_with_ack_progress_cancels_keepalive(tmp_path, monkeypatch):
    service = AnsibleNATSService(
        ServiceConfig(
            nats_servers=["nats://127.0.0.1:4222"],
            nats_instance_id="default",
            js_stream="BK_ANS_EXEC_TASKS",
            js_subject_prefix="bk.ans_exec.tasks",
            js_durable="ansible-executor",
            state_db_path=str(tmp_path / "task.db"),
        )
    )
    service.task_store.create_if_absent("task-2", "queued", {"task_id": "task-2"}, {}, service._now_iso())
    service.task_store.claim_task("task-2", "owner-b", service._lease_expiry_iso(), service._now_iso())

    calls = {"run": 0}

    async def fake_run_task(task, owner_id):
        calls["run"] += 1
        await asyncio.sleep(0)
        return {"task_id": task.task_id, "owner_id": owner_id}

    monkeypatch.setattr(service, "_run_task", fake_run_task)

    result = await service._run_task_with_ack_progress(
        DummyMessage(),
        QueuedTask(task_id="task-2", task_type="adhoc", payload={"task_id": "task-2"}, callback={}, instance_id="default"),
        "owner-b",
    )

    assert calls["run"] == 1
    assert result == {"task_id": "task-2", "owner_id": "owner-b"}
