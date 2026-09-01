import asyncio
import json

import pytest
from core.config import ServiceConfig
from service.nats_service import AnsibleNATSService, QueuedTask


@pytest.fixture(autouse=True)
def payload_encryption_key(monkeypatch):
    monkeypatch.setenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", "unit-test-payload-encryption-key")


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
        self.requests = []

    async def request(self, subject, request_payload, timeout):
        self.requests.append((subject, request_payload, timeout))
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
async def test_invoke_callback_rejects_untrusted_subject_before_request(tmp_path):
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
    service.nc = DummyNATSClient({"success": True})

    with pytest.raises(ValueError, match="callback subject is not allowed"):
        await service._invoke_callback({"subject": "system_mgmt.delete_user"}, {"task_id": "task-bad"})

    assert service.nc.requests == []


@pytest.mark.asyncio
async def test_invoke_callback_allows_configured_subject_pattern(tmp_path):
    service = AnsibleNATSService(
        ServiceConfig(
            nats_servers=["nats://127.0.0.1:4222"],
            nats_instance_id="default",
            js_stream="BK_ANS_EXEC_TASKS",
            js_subject_prefix="bk.ans_exec.tasks",
            js_durable="ansible-executor",
            state_db_path=str(tmp_path / "task.db"),
            allowed_callback_subjects=["job.ansible_task_callback", "bklite.safe_callback.>"],
        )
    )
    service.nc = DummyNATSClient({"success": True})

    await service._invoke_callback({"subject": "bklite.safe_callback.result"}, {"task_id": "task-safe"})

    assert service.nc.requests[0][0] == "bklite.safe_callback.result"


@pytest.mark.asyncio
async def test_invoke_callback_forwards_trusted_callback_context(tmp_path):
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
    service.nc = DummyNATSClient({"success": True})
    callback = {
        "subject": "job.ansible_task_callback",
        "context": {
            "caller": "ansible-executor",
            "execution_id": 42,
            "attempt_id": "attempt-1",
            "token": "secret",
        },
    }

    await service._invoke_callback(callback, {"task_id": "42", "result": []})

    request_payload = json.loads(service.nc.requests[0][1].decode("utf-8"))
    assert request_payload["args"][0]["callback_context"] == callback["context"]


@pytest.mark.asyncio
async def test_invoke_callback_allows_default_host_remote_callback_subject(tmp_path):
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
    service.nc = DummyNATSClient({"success": True})

    await service._invoke_callback(
        {"subject": "default_stargazer.host_remote.callback"},
        {"task_id": "collect_host_safe"},
    )

    assert service.nc.requests[0][0] == "default_stargazer.host_remote.callback"


@pytest.mark.asyncio
async def test_invalid_callback_log_does_not_expose_context_token(tmp_path):
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

    with pytest.MonkeyPatch.context() as monkeypatch:
        warning = []
        monkeypatch.setattr("service.nats_service.logger.warning", lambda *args: warning.append(args))
        await service._invoke_callback({"context": {"token": "must-not-leak"}}, {"task_id": "task-invalid"})

    assert "must-not-leak" not in repr(warning)


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
            "callback": {
                "subject": "job.ansible_task_callback",
                "context": {"execution_id": 1, "attempt_id": "a1", "token": "callback-secret"},
            },
        }
    )

    await service._enqueue_task(message, "adhoc", "default")

    subject, published = service.js.published[0]
    assert subject == "bk.ans_exec.tasks.adhoc.default"
    assert published["payload"]["host_credentials"][0]["_redacted"] is True
    assert "password" not in published["payload"]["host_credentials"][0]
    assert "private_key_content" not in published["payload"]
    assert "inventory_content" not in published["payload"]
    assert published["callback"]["context"]["token"] == "***"
    assert published["payload"]["callback"]["context"]["token"] == "***"

    execution_payload = service.task_store.get_execution_payload("task-queue-safe")
    assert execution_payload["private_key_content"].startswith("-----BEGIN RSA PRIVATE KEY-----")
    assert execution_payload["host_credentials"][0]["password"] == "secret"
    assert execution_payload["callback"]["context"]["token"] == "***"


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

    await service._enqueue_callback_retry(
        {"subject": "job.ansible_task_callback", "context": {"attempt_id": "a1", "token": "callback-secret"}},
        payload,
        "callback failed",
    )

    subject, published = service.js.published[0]
    assert subject == "ansible_executor.callback.retry.default"
    assert len(json.dumps(published, ensure_ascii=False).encode("utf-8")) < service.nc.max_payload
    assert published["payload"]["callback_payload_truncated"] is True
    assert published["payload"]["result"] == ""
    assert published["callback"]["context"]["token"] == "***"


def test_callback_retry_reloads_token_from_encrypted_callback_secret(tmp_path):
    service = _make_service(tmp_path)
    callback = {
        "subject": "job.ansible_task_callback",
        "context": {"execution_id": 1, "attempt_id": "a1", "token": "callback-secret"},
    }
    service.task_store.create_if_absent(
        "task-callback-ref",
        "queued",
        {"task_id": "task-callback-ref", "callback": callback},
        callback,
        service._now_iso(),
    )
    service.task_store.update_execution_result(
        "task-callback-ref",
        "success",
        {"task_id": "task-callback-ref", "success": True},
        service._now_iso(),
    )
    assert service.task_store.get_execution_payload("task-callback-ref") is None

    loaded = service._load_callback(
        "task-callback-ref",
        {"subject": "job.ansible_task_callback", "context": {"token": "***"}},
    )

    assert loaded["context"]["token"] == "callback-secret"


@pytest.mark.asyncio
async def test_retry_publish_failure_remains_pending_and_is_recoverable(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = DummyNATSClient({"success": True})
    callback = {
        "subject": "job.ansible_task_callback",
        "context": {"execution_id": 1, "attempt_id": "a1", "token": "callback-secret"},
    }
    result = {"task_id": "task-retry-publish", "success": True}
    service.task_store.create_if_absent(
        result["task_id"],
        "queued",
        {**result, "callback": callback},
        callback,
        service._now_iso(),
    )
    service.task_store.update_execution_result(
        result["task_id"],
        "success",
        result,
        service._now_iso(),
    )

    async def callback_fails(callback_config, callback_payload):
        raise RuntimeError("server unavailable")

    async def retry_publish_fails(callback_config, callback_payload, reason):
        raise RuntimeError("jetstream unavailable")

    monkeypatch.setattr(service, "_invoke_callback", callback_fails)
    monkeypatch.setattr(service, "_enqueue_callback_retry", retry_publish_fails)

    with pytest.raises(RuntimeError, match="jetstream unavailable"):
        await service._deliver_callback_result(result["task_id"], callback, result, "success")

    assert service.task_store.get_task(result["task_id"])["callback_status"] == "pending"

    published = []

    async def retry_publish_succeeds(callback_config, callback_payload, reason):
        published.append((callback_config, callback_payload, reason))

    monkeypatch.setattr(service, "_enqueue_callback_retry", retry_publish_succeeds)
    await service._resume_pending_callback(result["task_id"])

    assert published
    assert service.task_store.get_task(result["task_id"])["callback_status"] == "failed"


@pytest.mark.asyncio
async def test_retry_consumer_sent_state_fences_late_failed_write(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = DummyNATSClient({"success": True})
    callback = {"subject": "job.ansible_task_callback", "context": {"token": "callback-secret"}}
    result = {"task_id": "task-retry-race", "success": True}
    service.task_store.create_if_absent(
        result["task_id"],
        "queued",
        {**result, "callback": callback},
        callback,
        service._now_iso(),
    )
    service.task_store.update_execution_result(
        result["task_id"],
        "success",
        result,
        service._now_iso(),
    )

    async def callback_fails(callback_config, callback_payload):
        raise RuntimeError("response lost")

    async def retry_is_consumed_before_publish_returns(callback_config, callback_payload, reason):
        service.task_store.update_callback_status(
            result["task_id"],
            "sent",
            result,
            service._now_iso(),
            preserve_status="success",
        )

    monkeypatch.setattr(service, "_invoke_callback", callback_fails)
    monkeypatch.setattr(
        service,
        "_enqueue_callback_retry",
        retry_is_consumed_before_publish_returns,
    )

    await service._deliver_callback_result(result["task_id"], callback, result, "success")

    stored = service.task_store.get_task(result["task_id"])
    assert stored["status"] == "success"
    assert stored["callback_status"] == "sent"
    assert service.task_store.get_callback_config(result["task_id"]) is None


@pytest.mark.asyncio
async def test_worker_final_dlq_clears_all_callback_material(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()
    callback = {
        "subject": "job.ansible_task_callback",
        "context": {"execution_id": 1, "attempt_id": "a1", "token": "callback-secret"},
    }
    service.task_store.create_if_absent(
        "task-main-dlq",
        "queued",
        {"task_id": "task-main-dlq", "callback": callback},
        callback,
        service._now_iso(),
    )
    task = QueuedTask(
        task_id="task-main-dlq",
        task_type="adhoc",
        payload={"task_id": "task-main-dlq", "callback": {"context": {"token": "***"}}},
        callback={"subject": callback["subject"], "context": {"token": "***"}},
        instance_id="default",
    )

    class TaskMessage:
        data = json.dumps(task.to_json()).encode("utf-8")
        metadata = DummyMetadata(service.config.js_max_deliver)
        subject = "bk.ans_exec.tasks.adhoc.default"
        acked = False

        async def ack(self):
            self.acked = True

        async def nak(self):
            raise AssertionError("最终投递不应 NAK")

        async def in_progress(self):
            return None

    message = TaskMessage()

    class TaskSubscription:
        calls = 0

        async def fetch(self, batch, timeout):
            self.calls += 1
            if self.calls == 1:
                return [message]
            raise asyncio.CancelledError

    async def execution_fails(message_arg, task_arg, owner_id):
        raise RuntimeError("execution failed")

    service.psub = TaskSubscription()
    monkeypatch.setattr(service, "_run_task_with_ack_progress", execution_fails)

    with pytest.raises(asyncio.CancelledError):
        await service._worker_loop(1)

    assert message.acked is True
    assert service.task_store.get_callback_config(task.task_id) is None
    assert service.task_store.get_execution_payload(task.task_id) is None
    assert service.nc.published[0][0] == service.config.dlq_subject


@pytest.mark.asyncio
async def test_claim_observing_terminal_resumes_pending_callback_before_ack(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    task = QueuedTask(
        task_id="task-claim-terminal",
        task_type="adhoc",
        payload={"task_id": "task-claim-terminal"},
        callback={},
        instance_id="default",
    )

    class TaskMessage:
        data = json.dumps(task.to_json()).encode("utf-8")
        metadata = DummyMetadata(1)
        subject = "bk.ans_exec.tasks.adhoc.default"
        acked = False

        async def ack(self):
            self.acked = True

        async def nak(self):
            raise AssertionError("terminal task 不应 NAK")

    message = TaskMessage()

    class TaskSubscription:
        calls = 0

        async def fetch(self, batch, timeout):
            self.calls += 1
            if self.calls == 1:
                return [message]
            raise asyncio.CancelledError

    resumed = []

    async def resume_pending(task_id):
        resumed.append(task_id)

    service.psub = TaskSubscription()
    monkeypatch.setattr(service.task_store, "get_status", lambda task_id: "queued")
    monkeypatch.setattr(
        service.task_store,
        "claim_task",
        lambda *args, **kwargs: {"claimed": False, "reason": "terminal"},
    )
    monkeypatch.setattr(service, "_resume_pending_callback", resume_pending)

    with pytest.raises(asyncio.CancelledError):
        await service._worker_loop(1)

    assert resumed == [task.task_id]
    assert message.acked is True


@pytest.mark.asyncio
async def test_callback_retry_exhaustion_clears_encrypted_callback(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()
    callback = {
        "subject": "job.ansible_task_callback",
        "context": {"execution_id": 1, "attempt_id": "a1", "token": "callback-secret"},
    }
    service.task_store.create_if_absent(
        "task-callback-dlq",
        "queued",
        {"task_id": "task-callback-dlq", "callback": callback},
        callback,
        service._now_iso(),
    )

    class RetryMessage:
        def __init__(self):
            self.data = json.dumps(
                {
                    "task_id": "task-callback-dlq",
                    "callback": {"subject": callback["subject"], "context": {"token": "***"}},
                    "payload": {"task_id": "task-callback-dlq", "success": True},
                }
            ).encode("utf-8")
            self.metadata = DummyMetadata(service.config.js_max_deliver)
            self.acked = False

        async def ack(self):
            self.acked = True

        async def nak(self):
            raise AssertionError("最终重试不应 NAK")

    message = RetryMessage()

    class RetrySubscription:
        def __init__(self):
            self.calls = 0

        async def fetch(self, batch, timeout):
            self.calls += 1
            if self.calls == 1:
                return [message]
            raise asyncio.CancelledError

    async def fail_callback(callback_config, payload):
        raise RuntimeError("callback unavailable")

    service.retry_psub = RetrySubscription()
    monkeypatch.setattr(service, "_invoke_callback", fail_callback)

    with pytest.raises(asyncio.CancelledError):
        await service._callback_retry_loop()

    assert message.acked is True
    assert service.task_store.get_callback_config("task-callback-dlq") is None
    assert service.nc.published[0][0] == service.config.dlq_subject


@pytest.mark.asyncio
async def test_malformed_callback_retry_exhaustion_is_acked(tmp_path):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()

    class MalformedMessage:
        data = b"not-json"
        metadata = DummyMetadata(service.config.js_max_deliver)
        acked = False

        async def ack(self):
            self.acked = True

        async def nak(self):
            raise AssertionError("最终重试不应 NAK")

    message = MalformedMessage()

    class RetrySubscription:
        calls = 0

        async def fetch(self, batch, timeout):
            self.calls += 1
            if self.calls == 1:
                return [message]
            raise asyncio.CancelledError

    service.retry_psub = RetrySubscription()

    with pytest.raises(asyncio.CancelledError):
        await service._callback_retry_loop()

    assert message.acked is True
    assert service.nc.published[0][0] == service.config.dlq_subject


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
            "stream_lines_dropped": 17,
            "stream_publish_failures": 2,
            "stream_flush_timed_out": True,
            "stream_line_chunks": 3,
        },
        "",
    )

    assert result["success"] is True
    assert result["output_truncated"] is True
    assert result["result"] == [{"host": "10.10.41.149", "output_truncated": True}]
    assert result["result_summary"]["output_bytes_total"] == 1024
    assert result["result_summary"]["output_bytes_retained"] == 32
    assert result["result_summary"]["output_max_bytes"] == 32
    assert result["result_summary"]["stream_lines_dropped"] == 17
    assert result["result_summary"]["stream_publish_failures"] == 2
    assert result["result_summary"]["stream_flush_timed_out"] is True
    assert result["result_summary"]["stream_line_chunks"] == 3


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
async def test_run_task_uses_remote_shell_stream_for_job_script(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()
    captured = {}

    request = type(
        "R",
        (),
        {
            "execute_timeout": 90,
            "stream_remote_output": True,
            "module": "shell",
            "module_args": "echo first; sleep 20; echo second",
            "extra_vars": {"ansible_shell_executable": "/bin/bash"},
        },
    )()
    monkeypatch.setattr("service.nats_service.to_adhoc_request", lambda payload: request)
    monkeypatch.setattr("service.nats_service.prepare_adhoc_execution", lambda prepared: (["ansible", "all"], None))
    monkeypatch.setattr("service.nats_service.cleanup_workspace", lambda workspace: None)

    async def fake_remote_stream(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return (
            0,
            "host | CHANGED | rc=0 >>\nfirst\nsecond",
            {
                "truncated": False,
                "output_bytes_total": 13,
                "output_bytes_retained": 13,
                "output_max_bytes": 262144,
            },
        )

    async def fail_run_command(*args, **kwargs):
        raise AssertionError("buffered ansible CLI path must not be used")

    monkeypatch.setattr("service.nats_service.run_remote_shell_stream", fake_remote_stream)
    monkeypatch.setattr("service.nats_service.run_command", fail_run_command)
    monkeypatch.setattr(service.task_store, "update_execution_result", lambda *a, **k: True)
    monkeypatch.setattr(service.task_store, "update_callback_status", lambda *a, **k: True)

    task = QueuedTask(
        task_id="task-remote-stream",
        task_type="adhoc",
        payload={
            "task_id": "task-remote-stream",
            "stream_log_topic": "job.stream.23.ansible",
            "execution_id": "23",
        },
        callback=None,
        instance_id="default",
    )

    result = await service._run_task(task, "owner-a")

    assert result["success"] is True
    assert captured["script_content"] == request.module_args
    assert captured["shell_executable"] == "/bin/bash"
    assert captured["stream_log_topic"] == "job.stream.23.ansible"
    assert captured["execution_id"] == "23"
    assert callable(captured["stream_publish"])


@pytest.mark.asyncio
async def test_run_task_uses_remote_windows_stream_for_job_script(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()
    captured = {}

    request = type(
        "R",
        (),
        {
            "execute_timeout": 90,
            "stream_remote_output": True,
            "stream_remote_type": "powershell",
            "module": "win_shell",
            "module_args": "Write-Output first; Start-Sleep 5; Write-Output second",
            "host_credentials": [{"host": "10.10.90.120"}],
        },
    )()
    monkeypatch.setattr("service.nats_service.to_adhoc_request", lambda payload: request)
    monkeypatch.setattr("service.nats_service.prepare_adhoc_execution", lambda prepared: (["ansible", "all"], None))
    monkeypatch.setattr("service.nats_service.cleanup_workspace", lambda workspace: None)

    async def fake_remote_stream(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return (
            0,
            "host | CHANGED | rc=0 >>\nfirst\nsecond",
            {
                "truncated": False,
                "output_bytes_total": 13,
                "output_bytes_retained": 13,
                "output_max_bytes": 262144,
            },
        )

    async def fail_run_command(*args, **kwargs):
        raise AssertionError("buffered ansible CLI path must not be used")

    monkeypatch.setattr("service.nats_service.run_winrm_stream", fake_remote_stream)
    monkeypatch.setattr("service.nats_service.run_command", fail_run_command)
    monkeypatch.setattr(service.task_store, "update_execution_result", lambda *a, **k: True)
    monkeypatch.setattr(service.task_store, "update_callback_status", lambda *a, **k: True)

    task = QueuedTask(
        task_id="task-windows-stream",
        task_type="adhoc",
        payload={
            "task_id": "task-windows-stream",
            "stream_log_topic": "job.stream.31.ansible",
            "execution_id": "31",
        },
        callback=None,
        instance_id="default",
    )

    result = await service._run_task(task, "owner-a")

    assert result["success"] is True
    assert captured["command"] == request.host_credentials
    assert captured["script_content"] == request.module_args
    assert captured["script_type"] == "powershell"
    assert captured["stream_log_topic"] == "job.stream.31.ansible"
    assert captured["execution_id"] == "31"


@pytest.mark.asyncio
async def test_run_task_rejects_untrusted_stream_topic_before_publish(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()

    calls = {"run": 0}

    monkeypatch.setattr("service.nats_service.to_adhoc_request", lambda payload: type("R", (), {"execute_timeout": 60})())
    monkeypatch.setattr("service.nats_service.prepare_adhoc_execution", lambda request: (["echo", "hi"], None))
    monkeypatch.setattr("service.nats_service.cleanup_workspace", lambda workspace: None)

    async def fake_run_command(cmd, timeout, **kwargs):
        calls["run"] += 1
        return 0, "hi", {"truncated": False, "output_bytes_total": 2, "output_bytes_retained": 2, "output_max_bytes": 0}

    monkeypatch.setattr("service.nats_service.run_command", fake_run_command)
    monkeypatch.setattr(service.task_store, "update_execution_result", lambda *a, **k: True)
    monkeypatch.setattr(service.task_store, "update_callback_status", lambda *a, **k: True)

    task = QueuedTask(
        task_id="task-stream-bad",
        task_type="adhoc",
        payload={
            "task_id": "task-stream-bad",
            "stream_log_topic": "system_mgmt.delete_user",
            "execution_id": "exec-bad",
        },
        callback=None,
        instance_id="default",
    )

    result = await service._run_task(task, "owner-a")

    assert calls["run"] == 0
    assert service.nc.published == []
    assert result["success"] is False
    assert "stream subject is not allowed" in result["error"]


@pytest.mark.asyncio
async def test_run_task_allows_executor_stream_topic(tmp_path, monkeypatch):
    service = _make_service(tmp_path)
    service.nc = RecordingNATSClient()

    captured = {}

    monkeypatch.setattr("service.nats_service.to_adhoc_request", lambda payload: type("R", (), {"execute_timeout": 60})())
    monkeypatch.setattr("service.nats_service.prepare_adhoc_execution", lambda request: (["echo", "hi"], None))
    monkeypatch.setattr("service.nats_service.cleanup_workspace", lambda workspace: None)

    async def fake_run_command(cmd, timeout, **kwargs):
        captured.update(kwargs)
        if kwargs.get("stream_publish") and kwargs.get("stream_log_topic"):
            await kwargs["stream_publish"](kwargs["stream_log_topic"], b'{"line": "ok"}')
        return 0, "ok", {"truncated": False, "output_bytes_total": 2, "output_bytes_retained": 2, "output_max_bytes": 0}

    monkeypatch.setattr("service.nats_service.run_command", fake_run_command)
    monkeypatch.setattr(service.task_store, "update_execution_result", lambda *a, **k: True)
    monkeypatch.setattr(service.task_store, "update_callback_status", lambda *a, **k: True)

    task = QueuedTask(
        task_id="task-stream-executor",
        task_type="adhoc",
        payload={
            "task_id": "task-stream-executor",
            "stream_log_topic": "executor.stream.exec-9",
            "execution_id": "exec-9",
        },
        callback=None,
        instance_id="default",
    )

    await service._run_task(task, "owner-a")

    assert captured["stream_log_topic"] == "executor.stream.exec-9"
    assert service.nc.published == [("executor.stream.exec-9", b'{"line": "ok"}')]


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
