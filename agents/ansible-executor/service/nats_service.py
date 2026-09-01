import asyncio
import importlib
import json
import os
import ssl
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import nats.errors
from core.config import ServiceConfig, logger
from service.ansible_runner import (
    build_playbook_list_hosts_command,
    build_playbook_winrm_preflight_command,
    cleanup_workspace,
    parse_ansible_output_per_host,
    parse_playbook_recap,
    prepare_adhoc_execution,
    prepare_playbook_execution,
    run_command,
    to_adhoc_request,
    to_playbook_request,
)
from service.callback_delivery_service import CallbackDeliveryMixin
from service.nats_topology_service import NATSTopologyMixin
from service.remote_shell_stream import run_remote_shell_stream
from service.task_store import TERMINAL_TASK_STATUSES, TaskStore, _sanitize_callback_for_storage, _sanitize_payload_for_storage
from service.winrm_stream import run_winrm_stream


def _extract_payload(data: bytes) -> dict:
    envelope = json.loads(data.decode("utf-8"))
    args = envelope.get("args") or []
    if not args:
        raise ValueError("missing args[0] payload")
    if not isinstance(args[0], dict):
        raise ValueError("args[0] must be object")
    return args[0]


def _build_error(instance_id: str, result: str, error: str) -> bytes:
    return json.dumps(
        {
            "success": False,
            "result": result,
            "error": error,
            "instance_id": instance_id,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _build_queue_safe_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    sanitized = _sanitize_payload_for_storage(payload or {})
    return sanitized or {}


def _subject_matches(subject: str, allowed_subjects: list[str] | None) -> bool:
    if not subject or any(char.isspace() for char in subject):
        return False

    for raw_pattern in allowed_subjects or []:
        pattern = str(raw_pattern).strip()
        if not pattern:
            continue
        if pattern.endswith(".>"):
            prefix = pattern[:-1]
            if subject.startswith(prefix):
                return True
            continue
        if subject == pattern:
            return True
    return False


class AnsibleNATSService(NATSTopologyMixin, CallbackDeliveryMixin):
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.workers: list[asyncio.Task] = []
        payload_encryption_secret = os.getenv("ANSIBLE_PAYLOAD_ENCRYPTION_KEY", "") or config.nats_password
        self.task_store = TaskStore(config.state_db_path, payload_encryption_secret)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _validate_callback_subject(self, subject: str):
        if not _subject_matches(subject, self.config.allowed_callback_subjects):
            raise ValueError(f"callback subject is not allowed: {subject}")

    def _validate_stream_subject(self, subject: str):
        if not _subject_matches(subject, self.config.allowed_stream_subjects):
            raise ValueError(f"stream subject is not allowed: {subject}")

    @staticmethod
    def _build_accepted(task_id: str, duplicate: bool = False) -> bytes:
        return json.dumps(
            {
                "success": True,
                "result": {
                    "accepted": True,
                    "status": "queued",
                    "task_id": task_id,
                    "duplicate": duplicate,
                    "queued_at": AnsibleNATSService._now_iso(),
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")

    def _effective_ack_deadline_seconds(self) -> float:
        if self.config.js_backoff:
            return max(1.0, float(self.config.js_backoff[0]))
        return max(1.0, float(self.config.js_ack_wait))

    def _heartbeat_interval_seconds(self) -> float:
        return max(1.0, min(30.0, self._effective_ack_deadline_seconds() * 0.4))

    def _lease_expiry_iso(self, now: datetime | None = None) -> str:
        current = now or datetime.now(UTC)
        lease_window = max(self._effective_ack_deadline_seconds() * 1.5, self._heartbeat_interval_seconds() + 1.0)
        return (current + timedelta(seconds=lease_window)).isoformat()

    async def _keep_message_in_progress(self, msg, task_id: str, owner_id: str):
        interval = self._heartbeat_interval_seconds()
        while True:
            await asyncio.sleep(interval)
            now = datetime.now(UTC)
            lease_expires_at = self._lease_expiry_iso(now)
            renewed = self.task_store.renew_lease(task_id, owner_id, lease_expires_at, now.isoformat())
            if not renewed:
                logger.warning("stop ack keepalive without active lease: task_id=%s owner_id=%s", task_id, owner_id)
                return
            await msg.in_progress()
            logger.info(
                "ack keepalive sent: task_id=%s owner_id=%s interval=%.2fs lease_expires_at=%s",
                task_id,
                owner_id,
                interval,
                lease_expires_at,
            )

    async def _run_task_with_ack_progress(self, msg, task: "QueuedTask", owner_id: str) -> dict[str, Any]:
        keepalive_task = asyncio.create_task(self._keep_message_in_progress(msg, task.task_id, owner_id))
        try:
            return await self._run_task(task, owner_id)
        finally:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass

    def _load_execution_payload(self, task: "QueuedTask") -> dict[str, Any]:
        execution_payload = self.task_store.get_execution_payload(task.task_id)
        if execution_payload:
            return execution_payload
        return task.payload

    @staticmethod
    def _build_task_dlq_payload(task: "QueuedTask", subject: str, error: str, delivered: int, timestamp: str) -> dict[str, Any]:
        return {
            "type": "task_execution",
            "subject": subject,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "instance_id": task.instance_id,
            "payload": _build_queue_safe_payload(task.payload),
            "error": error,
            "delivered": delivered,
            "timestamp": timestamp,
        }

    @staticmethod
    def _build_task_result(
        task: "QueuedTask",
        owner_id: str,
        started_at: str,
        code: int,
        output: str,
        output_meta: dict[str, Any],
        error: str,
    ) -> dict[str, Any]:
        success = code == 0 and not error
        if not success and not error:
            error = f"ansible {task.task_type} failed with exit code {code}"

        output_truncated = bool(output_meta.get("truncated"))
        parsed_results = parse_ansible_output_per_host(output, output_truncated=output_truncated) if output else []
        if not parsed_results and output and not output_truncated:
            parsed_results = parse_playbook_recap(output)

        result_summary = {
            "stdout_combined": output,
            "host_count": len(parsed_results),
            "output_truncated": output_truncated,
            "output_bytes_total": int(output_meta.get("output_bytes_total", len(output.encode("utf-8")))),
            "output_bytes_retained": int(output_meta.get("output_bytes_retained", len(output.encode("utf-8")))),
            "output_max_bytes": int(output_meta.get("output_max_bytes", 0)),
            "stream_lines_dropped": int(output_meta.get("stream_lines_dropped", 0)),
            "stream_publish_failures": int(output_meta.get("stream_publish_failures", 0)),
            "stream_flush_timed_out": bool(output_meta.get("stream_flush_timed_out", False)),
            "stream_line_chunks": int(output_meta.get("stream_line_chunks", 0)),
        }

        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": "success" if success else "failed",
            "success": success,
            "result": parsed_results if parsed_results else output,
            "result_summary": result_summary,
            "output_truncated": output_truncated,
            "error": error,
            "started_at": started_at,
            "finished_at": AnsibleNATSService._now_iso(),
            "owner_id": owner_id,
        }

    async def _run_task(self, task: "QueuedTask", owner_id: str) -> dict[str, Any]:
        workspace = None
        code = -1
        output = ""
        output_meta = {"truncated": False, "output_bytes_total": 0, "output_bytes_retained": 0, "output_max_bytes": 0}
        error = ""
        started_at = self._now_iso()
        execution_payload = self._load_execution_payload(task)
        callback = self._load_callback(task.task_id, task.callback)

        stream_log_topic = execution_payload.get("stream_log_topic")
        execution_id = execution_payload.get("execution_id")

        try:
            stream_kwargs: dict[str, Any] = {}
            if stream_log_topic and execution_id:
                stream_subject = str(stream_log_topic).strip()
                self._validate_stream_subject(stream_subject)
                stream_kwargs = {
                    "stream_publish": lambda subject, data: self.nc.publish(subject, data),
                    "stream_log_topic": stream_subject,
                    "execution_id": str(execution_id),
                }

            if task.task_type == "adhoc":
                request = to_adhoc_request(execution_payload)
                cmd, workspace = prepare_adhoc_execution(request)
                remote_stream_enabled = getattr(request, "stream_remote_output", False) and stream_kwargs
                if remote_stream_enabled and request.module == "shell":
                    code, output, output_meta = await run_remote_shell_stream(
                        cmd,
                        script_content=request.module_args,
                        shell_executable=str((request.extra_vars or {}).get("ansible_shell_executable") or "/bin/sh"),
                        timeout=request.execute_timeout,
                        **stream_kwargs,
                    )
                elif remote_stream_enabled and request.module == "win_shell":
                    windows_stream_kwargs = {
                        "script_content": request.module_args,
                        "script_type": str(request.stream_remote_type or ""),
                        "timeout": request.execute_timeout,
                        **stream_kwargs,
                    }
                    if request.host_credentials:
                        code, output, output_meta = await run_winrm_stream(
                            request.host_credentials,
                            **windows_stream_kwargs,
                        )
                    else:
                        code, output, output_meta = await run_command(cmd, request.execute_timeout, **stream_kwargs)
                else:
                    code, output, output_meta = await run_command(cmd, request.execute_timeout, **stream_kwargs)
            else:
                request = to_playbook_request(execution_payload)
                cmd, workspace, prepared_request = await prepare_playbook_execution(self.config, request)
                preflight_cmd = build_playbook_list_hosts_command(prepared_request)
                _, _, _ = await run_command(preflight_cmd, request.execute_timeout)
                winrm_preflight_cmd = build_playbook_winrm_preflight_command(prepared_request)
                _, _, _ = await run_command(winrm_preflight_cmd, request.execute_timeout)
                code, output, output_meta = await run_command(cmd, request.execute_timeout, **stream_kwargs)
        except Exception as err:
            error = str(err)
        finally:
            cleanup_workspace(workspace)

        result = self._build_task_result(task, owner_id, started_at, code, output, output_meta, error)
        success = bool(result["success"])
        final_status = "success" if success else "failed"
        persisted = self.task_store.update_execution_result(task.task_id, final_status, result, self._now_iso(), owner_id=owner_id)
        if not persisted:
            raise RuntimeError(f"task lease lost before final update: {task.task_id}")

        if callback:
            await self._deliver_callback_result(
                task.task_id,
                callback,
                result,
                final_status,
            )
        else:
            self.task_store.update_callback_status(task.task_id, "none", result, self._now_iso(), preserve_status=final_status)

        return result

    async def _worker_loop(self, worker_id: int):
        logger.info("worker started: %s", worker_id)
        while True:
            try:
                msgs = await self.psub.fetch(batch=1, timeout=1)
            except nats.errors.TimeoutError:
                continue
            if not msgs:
                await asyncio.sleep(0.05)
                continue

            msg = msgs[0]
            task = None
            try:
                data = json.loads(msg.data.decode("utf-8"))
                task = QueuedTask.from_json(data)
                status = self.task_store.get_status(task.task_id)
                if status in TERMINAL_TASK_STATUSES:
                    await self._resume_pending_callback(task.task_id)
                    await msg.ack()
                    continue

                owner_id = f"{self.config.nats_instance_id}-worker-{worker_id}-{uuid.uuid4().hex[:8]}"
                claim = self.task_store.claim_task(
                    task.task_id,
                    owner_id,
                    self._lease_expiry_iso(),
                    self._now_iso(),
                )
                if not claim.get("claimed"):
                    reason = claim.get("reason")
                    if reason == "terminal":
                        await self._resume_pending_callback(task.task_id)
                        await msg.ack()
                    elif reason == "leased":
                        logger.warning(
                            "skip duplicate delivery for leased task: task_id=%s owner_id=%s active_owner=%s lease_expires_at=%s",
                            task.task_id,
                            owner_id,
                            claim.get("lease_owner"),
                            claim.get("lease_expires_at"),
                        )
                        await msg.in_progress()
                    else:
                        await msg.nak()
                    continue

                logger.info(
                    "claimed task execution: task_id=%s owner_id=%s execution_attempt=%s effective_ack_deadline=%.2fs heartbeat_interval=%.2fs",
                    task.task_id,
                    owner_id,
                    claim.get("execution_attempt"),
                    self._effective_ack_deadline_seconds(),
                    self._heartbeat_interval_seconds(),
                )
                await self._run_task_with_ack_progress(msg, task, owner_id)
                await msg.ack()
            except Exception as err:
                logger.exception("worker task failed worker=%s error=%s", worker_id, err)
                meta = msg.metadata
                if meta and meta.num_delivered >= self.config.js_max_deliver:
                    if task is not None:
                        dlq_payload = self._build_task_dlq_payload(task, msg.subject, str(err), meta.num_delivered, self._now_iso())
                    else:
                        dlq_payload = {
                            "type": "task_execution",
                            "subject": msg.subject,
                            "error": str(err),
                            "delivered": meta.num_delivered,
                            "timestamp": self._now_iso(),
                        }
                    await self.nc.publish(
                        self.config.dlq_subject,
                        json.dumps(dlq_payload, ensure_ascii=False).encode("utf-8"),
                    )
                    if task is not None:
                        self.task_store.clear_execution_payload(task.task_id)
                        stored_task = self.task_store.get_task(task.task_id)
                        if not stored_task or stored_task.get("callback_status") != "failed":
                            self.task_store.clear_callback_config(task.task_id)
                    await msg.ack()
                else:
                    await msg.nak()

    async def _handle_task_query(self, msg, instance_id: str):
        try:
            payload = _extract_payload(msg.data)
            task_id = str(payload.get("task_id", "")).strip()
            if not task_id:
                await msg.respond(_build_error(instance_id, "", "task_id is required"))
                return
            task = self.task_store.get_task(task_id)
            if not task:
                await msg.respond(_build_error(instance_id, "", f"task not found: {task_id}"))
                return
            await msg.respond(
                json.dumps(
                    {
                        "success": True,
                        "result": task,
                        "instance_id": instance_id,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )
        except Exception as err:
            await msg.respond(_build_error(instance_id, "", str(err)))

    async def _enqueue_task(self, msg, task_type: str, instance_id: str):
        payload = _extract_payload(msg.data)
        task_id = str(payload.get("task_id", "")).strip() or uuid.uuid4().hex
        payload["task_id"] = task_id
        callback = payload.get("callback") or {}

        inserted = self.task_store.create_if_absent(
            task_id=task_id,
            status="queued",
            payload=payload,
            callback=callback,
            now_iso=self._now_iso(),
        )

        task = QueuedTask(
            task_id=task_id,
            task_type=task_type,
            payload=_build_queue_safe_payload(payload),
            callback=_sanitize_callback_for_storage(callback),
            instance_id=instance_id,
        )

        if inserted:
            subject = f"{self.config.js_subject_prefix}.{task_type}.{instance_id}"
            await self.js.publish(subject, json.dumps(task.to_json(), ensure_ascii=False).encode("utf-8"))
            await msg.respond(self._build_accepted(task_id, duplicate=False))
        else:
            await msg.respond(self._build_accepted(task_id, duplicate=True))

    async def _handle_adhoc(self, msg, instance_id: str):
        try:
            await self._enqueue_task(msg, "adhoc", instance_id)
        except Exception as err:
            await msg.respond(_build_error(instance_id, "", str(err)))

    async def _handle_playbook(self, msg, instance_id: str):
        try:
            await self._enqueue_task(msg, "playbook", instance_id)
        except Exception as err:
            await msg.respond(_build_error(instance_id, "", str(err)))

    async def run(self) -> None:
        nats_client_module = importlib.import_module("nats.aio.client")
        nc = nats_client_module.Client()
        self.nc = nc

        connect_kwargs = {
            "servers": self.config.nats_servers,
            "connect_timeout": self.config.nats_conn_timeout,
            "name": "ansible-executor",
        }
        if self.config.nats_username:
            connect_kwargs["user"] = self.config.nats_username
        if self.config.nats_password:
            connect_kwargs["password"] = self.config.nats_password
        if self.config.nats_protocol == "tls":
            tls_context = ssl.create_default_context()
            if self.config.nats_tls_ca_file:
                tls_context.load_verify_locations(cafile=self.config.nats_tls_ca_file)
            connect_kwargs["tls"] = tls_context

        await nc.connect(**connect_kwargs)
        logger.info("connected to NATS: %s", ",".join(self.config.nats_servers))

        self.js = nc.jetstream(timeout=120)
        await self._ensure_stream_and_consumer()

        instance_id = self.config.nats_instance_id
        subjects = {
            f"ansible.adhoc.{instance_id}": self._handle_adhoc,
            f"ansible.playbook.{instance_id}": self._handle_playbook,
            f"ansible.task.query.{instance_id}": self._handle_task_query,
        }
        for subject, handler in subjects.items():

            async def callback(msg, h=handler, iid=instance_id):
                await h(msg, iid)

            await nc.subscribe(subject, cb=callback)
            logger.info("subscribed subject: %s", subject)

        worker_count = max(1, self.config.max_workers)
        self.workers = [asyncio.create_task(self._worker_loop(i + 1)) for i in range(worker_count)]
        self.workers.append(asyncio.create_task(self._callback_retry_loop()))
        logger.info("workers started: %s", worker_count)

        await asyncio.Event().wait()


@dataclass
class QueuedTask:
    task_id: str
    task_type: str
    payload: dict[str, Any]
    callback: dict[str, Any] | None
    instance_id: str

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "callback": self.callback or {},
            "instance_id": self.instance_id,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "QueuedTask":
        return cls(
            task_id=str(data.get("task_id", "")),
            task_type=str(data.get("task_type", "")),
            payload=data.get("payload") or {},
            callback=data.get("callback") or {},
            instance_id=str(data.get("instance_id", "")),
        )
