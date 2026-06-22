import asyncio
import json

import pytest
from core.config import ServiceConfig
from service.nats_service import AnsibleNATSService, QueuedTask


class DummyMessage:
    def __init__(self):
        self.in_progress_calls = 0

    async def in_progress(self):
        self.in_progress_calls += 1


class DummyEnqueueMessage:
    def __init__(self, payload):
        self.data = json.dumps({"args": [payload], "kwargs": {}}).encode("utf-8")
        self.responses = []

    async def respond(self, payload):
        self.responses.append(json.loads(payload.decode("utf-8")))


class DummyJetStream:
    def __init__(self):
        self.published = []

    async def publish(self, subject, payload):
        self.published.append((subject, json.loads(payload.decode("utf-8"))))


class DummyNATSResponse:
    def __init__(self, payload):
        if isinstance(payload, bytes):
            self.data = payload
        else:
            self.data = json.dumps(payload).encode("utf-8")


class DummyNATSClient:
    def __init__(self, payload, max_payload=1024 * 1024):
        self.payload = payload
        self.max_payload = max_payload

    async def request(self, subject, request_payload, timeout):
        return DummyNATSResponse(self.payload)


class DummyMetadata:
    def __init__(self, num_delivered):
        self.num_delivered = num_delivered


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


@pytest.mark.asyncio
async def test_invoke_callback_rejects_handler_failure(tmp_path):
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
    service.nc = DummyNATSClient({"success": True, "result": {"success": False, "message": "invalid result"}})

    with pytest.raises(RuntimeError, match="invalid result"):
        await service._invoke_callback({"subject": "job.ansible_task_callback"}, {"task_id": "task-3"})


@pytest.mark.asyncio
async def test_invoke_callback_rejects_transport_failure(tmp_path):
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
    service.nc = DummyNATSClient({"success": False, "message": "callback exception"})

    with pytest.raises(RuntimeError, match="callback exception"):
        await service._invoke_callback({"subject": "job.ansible_task_callback"}, {"task_id": "task-4"})


@pytest.mark.asyncio
async def test_invoke_callback_rejects_invalid_json_response(tmp_path):
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
    service.nc = DummyNATSClient(b"not-json")

    with pytest.raises(ValueError, match="invalid JSON"):
        await service._invoke_callback({"subject": "job.ansible_task_callback"}, {"task_id": "task-5"})


@pytest.mark.asyncio
async def test_invoke_callback_rejects_non_object_response(tmp_path):
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
    service.nc = DummyNATSClient(["ok"])

    with pytest.raises(ValueError, match="non-object"):
        await service._invoke_callback({"subject": "job.ansible_task_callback"}, {"task_id": "task-6"})


@pytest.mark.asyncio
async def test_enqueue_task_publishes_sanitized_queue_payload(tmp_path):
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
    service.js = DummyJetStream()
    message = DummyEnqueueMessage(
        {
            "task_id": "task-queue-safe",
            "inventory_content": "[all]\n10.0.0.1 ansible_user=root ansible_password=secret\n",
            "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": "secret"}],
            "private_key_content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
        }
    )

    await service._enqueue_task(message, "adhoc", "default")

    subject, published = service.js.published[0]
    assert subject == "bk.ans_exec.tasks.adhoc.default"
    assert published["payload"]["host_credentials"][0]["_redacted"] is True
    assert "password" not in published["payload"]["host_credentials"][0]
    assert "private_key_content" not in published["payload"]
    assert "inventory_content" not in published["payload"]

    execution_payload = service.task_store.get_execution_payload("task-queue-safe")
    assert execution_payload["private_key_content"].startswith("-----BEGIN RSA PRIVATE KEY-----")
    assert execution_payload["host_credentials"][0]["password"] == "secret"


def test_build_task_dlq_payload_uses_sanitized_snapshot():
    task = QueuedTask(
        task_id="task-dlq",
        task_type="adhoc",
        payload={
            "task_id": "task-dlq",
            "inventory_content": "[all]\n10.0.0.1 ansible_user=root ansible_password=secret\n",
            "host_credentials": [{"host": "10.0.0.1", "user": "root", "password": "secret"}],
        },
        callback={},
        instance_id="default",
    )

    dlq_payload = AnsibleNATSService._build_task_dlq_payload(
        task,
        "bk.ans_exec.tasks.adhoc.default",
        "boom",
        5,
        "2026-06-02T00:00:00+00:00",
    )

    assert dlq_payload["task_id"] == "task-dlq"
    assert "inventory_content" not in dlq_payload["payload"]
    assert "password" not in dlq_payload["payload"]["host_credentials"][0]
    assert dlq_payload["payload"]["host_credentials"][0]["_redacted"] is True


def test_build_callback_retry_dlq_payload_keeps_structured_summary_only():
    dlq_payload = AnsibleNATSService._build_callback_retry_dlq_payload(
        {
            "task_id": "task-callback",
            "reason": "request-failed",
            "callback": {"subject": "job.ansible_task_callback"},
            "payload": {"task_id": "task-callback", "success": False, "output_truncated": True},
        },
        "callback failed",
        5,
        "2026-06-02T00:00:00+00:00",
    )

    assert dlq_payload["type"] == "callback_retry"
    assert dlq_payload["payload"]["output_truncated"] is True
    assert "task" not in dlq_payload


@pytest.mark.asyncio
async def test_prepare_callback_payload_shrinks_oversized_output_for_retry(tmp_path):
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
    service.nc = DummyNATSClient({"success": True}, max_payload=20 * 1024)

    payload = {
        "task_id": "task-big-output",
        "success": False,
        "error": "",
        "result": [
            {
                "host": "10.0.0.1",
                "status": "failed",
                "stdout": "x" * 20000,
                "stderr": "",
                "exit_code": 1,
                "error_message": "",
            }
        ],
        "result_summary": {
            "stdout_combined": "x" * 20000,
            "host_count": 1,
            "output_truncated": True,
            "output_bytes_total": 20000,
            "output_bytes_retained": 20000,
            "output_max_bytes": 20000,
        },
    }

    callback_payload = service._prepare_callback_payload(payload)

    assert service._callback_request_size_bytes(callback_payload) < service.nc.max_payload
    assert callback_payload["result_summary"]["callback_payload_truncated"] is True
    assert "stdout_combined" not in callback_payload["result_summary"]
    assert callback_payload["result"][0]["stdout"].endswith("...[truncated for callback]")


@pytest.mark.asyncio
async def test_enqueue_callback_retry_uses_compact_payload(tmp_path):
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
    service.js = DummyJetStream()
    service.nc = DummyNATSClient({"success": True}, max_payload=10 * 1024)
    service.retry_subject = "ansible_executor.callback.retry.default"

    payload = service._prepare_callback_payload(
        {
            "task_id": "task-big-output",
            "success": False,
            "result": "x" * 20000,
            "result_summary": {
                "stdout_combined": "x" * 20000,
                "host_count": 1,
                "output_truncated": True,
                "output_bytes_total": 20000,
                "output_bytes_retained": 20000,
                "output_max_bytes": 20000,
            },
        }
    )

    await service._enqueue_callback_retry({"subject": "job.ansible_task_callback"}, payload, "callback failed")

    subject, published = service.js.published[0]
    assert subject == "ansible_executor.callback.retry.default"
    assert len(json.dumps(published, ensure_ascii=False).encode("utf-8")) < service.nc.max_payload
    assert published["payload"]["callback_payload_truncated"] is True
    assert published["payload"]["result"] == ""


def test_build_task_result_keeps_structured_results_when_output_is_truncated(monkeypatch):
    monkeypatch.setattr(
        "service.nats_service.parse_ansible_output_per_host",
        lambda output, output_truncated=False: [{"host": "10.10.41.149", "output_truncated": output_truncated}],
    )
    monkeypatch.setattr("service.nats_service.parse_playbook_recap", lambda output: [{"host": "should-not-be-used"}])

    task = QueuedTask(task_id="task-output", task_type="adhoc", payload={"task_id": "task-output"}, callback={}, instance_id="default")
    result = AnsibleNATSService._build_task_result(
        task,
        "owner-a",
        "2026-06-02T00:00:00+00:00",
        0,
        "x" * 32,
        {
            "truncated": True,
            "output_bytes_total": 1024,
            "output_bytes_retained": 32,
            "output_max_bytes": 32,
        },
        "",
    )

    assert result["success"] is True
    assert result["output_truncated"] is True
    assert result["result"] == [{"host": "10.10.41.149", "output_truncated": True}]
    assert result["result_summary"]["output_bytes_total"] == 1024
    assert result["result_summary"]["output_bytes_retained"] == 32
    assert result["result_summary"]["output_max_bytes"] == 32


class RecordingNATSClient(DummyNATSClient):
    def __init__(self):
        super().__init__({"success": True})
        self.published = []

    async def publish(self, subject, data):
        self.published.append((subject, data))


def _make_service(tmp_path):
    return AnsibleNATSService(
        ServiceConfig(
            nats_servers=["nats://127.0.0.1:4222"],
            nats_instance_id="default",
            js_stream="BK_ANS_EXEC_TASKS",
            js_subject_prefix="bk.ans_exec.tasks",
            js_durable="ansible-executor",
            state_db_path=str(tmp_path / "task.db"),
        )
    )


@pytest.mark.asyncio
async def test_run_task_forwards_stream_context_to_run_command(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()

    captured = {}

    monkeypatch.setattr("service.nats_service.to_adhoc_request", lambda payload: type("R", (), {"execute_timeout": 60})())
    monkeypatch.setattr("service.nats_service.prepare_adhoc_execution", lambda request: (["echo", "hi"], None))
    monkeypatch.setattr("service.nats_service.cleanup_workspace", lambda workspace: None)

    async def fake_run_command(cmd, timeout, **kwargs):
        captured.update(kwargs)
        # Simulate the executor publishing one streamed line through the wrapper.
        if kwargs.get("stream_publish") and kwargs.get("stream_log_topic"):
            await kwargs["stream_publish"](kwargs["stream_log_topic"], b'{"line": "hi"}')
        return 0, "hi", {"truncated": False, "output_bytes_total": 2, "output_bytes_retained": 2, "output_max_bytes": 0}

    monkeypatch.setattr("service.nats_service.run_command", fake_run_command)
    monkeypatch.setattr(service.task_store, "update_execution_result", lambda *a, **k: True)
    monkeypatch.setattr(service.task_store, "update_callback_status", lambda *a, **k: True)

    task = QueuedTask(
        task_id="task-stream",
        task_type="adhoc",
        payload={
            "task_id": "task-stream",
            "stream_log_topic": "bk.ans_exec.stream.exec-9",
            "execution_id": "exec-9",
        },
        callback=None,
        instance_id="default",
    )

    await service._run_task(task, "owner-a")

    assert captured["stream_log_topic"] == "bk.ans_exec.stream.exec-9"
    assert captured["execution_id"] == "exec-9"
    assert callable(captured["stream_publish"])
    # The publisher wrapper routes to the core NATS publish on self.nc.
    assert service.nc.published == [("bk.ans_exec.stream.exec-9", b'{"line": "hi"}')]


@pytest.mark.asyncio
async def test_run_task_skips_stream_context_when_fields_absent(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()

    captured = {}

    monkeypatch.setattr("service.nats_service.to_adhoc_request", lambda payload: type("R", (), {"execute_timeout": 60})())
    monkeypatch.setattr("service.nats_service.prepare_adhoc_execution", lambda request: (["echo", "hi"], None))
    monkeypatch.setattr("service.nats_service.cleanup_workspace", lambda workspace: None)

    async def fake_run_command(cmd, timeout, **kwargs):
        captured["kwargs"] = kwargs
        return 0, "hi", {"truncated": False, "output_bytes_total": 2, "output_bytes_retained": 2, "output_max_bytes": 0}

    monkeypatch.setattr("service.nats_service.run_command", fake_run_command)
    monkeypatch.setattr(service.task_store, "update_execution_result", lambda *a, **k: True)
    monkeypatch.setattr(service.task_store, "update_callback_status", lambda *a, **k: True)

    task = QueuedTask(
        task_id="task-no-stream",
        task_type="adhoc",
        payload={"task_id": "task-no-stream"},
        callback=None,
        instance_id="default",
    )

    await service._run_task(task, "owner-a")

    assert captured["kwargs"] == {}
    assert service.nc.published == []
