import asyncio
import importlib
import json
import logging
import os
import ssl
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import nats.errors
from core.config import ServiceConfig
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, RetentionPolicy, StorageType, StreamConfig
from nats.js.errors import NotFoundError
from service.ansible_runner import (
    cleanup_workspace,
    parse_ansible_output_per_host,
    prepare_adhoc_execution,
    prepare_playbook_execution,
    run_command,
    to_adhoc_request,
    to_playbook_request,
)
from service.task_store import TaskStore

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [ansible-executor] %(message)s",
)
logger = logging.getLogger(__name__)


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


class AnsibleNATSService:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.workers: list[asyncio.Task] = []
        self.task_store = TaskStore(config.state_db_path)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

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

    async def _ensure_stream_and_consumer(self):
        subject_pattern = f"{self.config.js_subject_prefix}.>"
        retry_subject = f"ansible_executor.callback.retry.{self.config.nats_instance_id}"

        owner_stream = None
        try:
            owner_stream = await self.js.find_stream_name_by_subject(subject_pattern)
        except NotFoundError:
            owner_stream = None

        if owner_stream and owner_stream != self.config.js_stream:
            logger.warning(
                "subject '%s' already belongs to stream '%s'; reuse this stream for restart compatibility",
                subject_pattern,
                owner_stream,
            )
            self.config.js_stream = owner_stream

        try:
            retry_owner_stream = await self.js.find_stream_name_by_subject(retry_subject)
            expected_retry_stream = f"{self.config.js_stream}_CALLBACK_RETRY"
            if retry_owner_stream != expected_retry_stream:
                raise ValueError(
                    f"retry subject '{retry_subject}' is already owned by stream '{retry_owner_stream}'. "
                    "Please change NATS_INSTANCE_ID or callback retry subject prefix."
                )
        except NotFoundError:
            pass

        stream_config = StreamConfig(
            name=self.config.js_stream,
            subjects=[subject_pattern],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.FILE,
            max_msgs=-1,
            max_age=0,
        )

        try:
            await self.js.stream_info(self.config.js_stream)
            await self.js.update_stream(stream_config)
        except NotFoundError:
            await self.js.add_stream(stream_config)
        except Exception as err:
            # Stream create/update may fail with overlap when another stream already owns this subject.
            # Surface a clearer startup error for operators.
            if "overlap" in str(err).lower():
                owner_stream = await self.js.find_stream_name_by_subject(subject_pattern)
                raise ValueError(
                    f"stream subject conflict: '{subject_pattern}' is already owned by '{owner_stream}'. "
                    f"Set a unique ANSIBLE_JS_NAMESPACE or ANSIBLE_JS_SUBJECT_PREFIX."
                ) from err
            raise

        durable_name = f"{self.config.js_durable}-{self.config.nats_instance_id}"
        ack_wait_seconds = float(self.config.js_ack_wait)
        backoff_seconds = [float(x) for x in (self.config.js_backoff or [])]
        consumer_config = ConsumerConfig(
            durable_name=durable_name,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            filter_subject=subject_pattern,
            ack_wait=ack_wait_seconds,
            max_deliver=self.config.js_max_deliver,
            backoff=backoff_seconds or None,
        )
        # WorkQueue stream requires one unique filtered consumer per subject pattern.
        # Reuse existing filtered consumer when stream is reused across restarts.
        existing_main_consumer = None
        main_consumers = await self.js.consumers_info(self.config.js_stream)
        for info in main_consumers:
            cfg = info.config
            if cfg and getattr(cfg, "filter_subject", "") == subject_pattern:
                existing_main_consumer = info.name
                break

        if existing_main_consumer and existing_main_consumer != durable_name:
            logger.warning(
                "reuse existing main consumer '%s' for filter '%s' on stream '%s'",
                existing_main_consumer,
                subject_pattern,
                self.config.js_stream,
            )
            durable_name = existing_main_consumer
            consumer_config.durable_name = durable_name

        try:
            await self.js.consumer_info(self.config.js_stream, durable_name)
            await self.js.delete_consumer(self.config.js_stream, durable_name)
            await self.js.add_consumer(self.config.js_stream, consumer_config)
        except NotFoundError:
            await self.js.add_consumer(self.config.js_stream, consumer_config)

        self.psub = await self.js.pull_subscribe(
            subject_pattern,
            durable=durable_name,
            stream=self.config.js_stream,
        )

        retry_stream = f"{self.config.js_stream}_CALLBACK_RETRY"
        retry_stream_config = StreamConfig(
            name=retry_stream,
            subjects=[retry_subject],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.FILE,
            max_msgs=-1,
            max_age=0,
        )
        try:
            await self.js.stream_info(retry_stream)
            await self.js.update_stream(retry_stream_config)
        except NotFoundError:
            await self.js.add_stream(retry_stream_config)
        except Exception as err:
            if "overlap" in str(err).lower():
                owner_stream = await self.js.find_stream_name_by_subject(retry_subject)
                raise ValueError(
                    f"retry stream subject conflict: '{retry_subject}' is already owned by '{owner_stream}'. "
                    "Change NATS_INSTANCE_ID or callback retry subject prefix."
                ) from err
            raise

        retry_durable = f"{self.config.js_durable}-callback-retry-{self.config.nats_instance_id}"
        retry_consumer_config = ConsumerConfig(
            durable_name=retry_durable,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            filter_subject=retry_subject,
            ack_wait=float(self.config.js_ack_wait),
            max_deliver=self.config.js_max_deliver,
            backoff=[float(x) for x in (self.config.js_backoff or [])] or None,
        )

        existing_retry_consumer = None
        retry_consumers = await self.js.consumers_info(retry_stream)
        for info in retry_consumers:
            cfg = info.config
            if cfg and getattr(cfg, "filter_subject", "") == retry_subject:
                existing_retry_consumer = info.name
                break

        if existing_retry_consumer and existing_retry_consumer != retry_durable:
            logger.warning(
                "reuse existing callback retry consumer '%s' for filter '%s' on stream '%s'",
                existing_retry_consumer,
                retry_subject,
                retry_stream,
            )
            retry_durable = existing_retry_consumer
            retry_consumer_config.durable_name = retry_durable

        try:
            await self.js.consumer_info(retry_stream, retry_durable)
            await self.js.delete_consumer(retry_stream, retry_durable)
            await self.js.add_consumer(retry_stream, retry_consumer_config)
        except NotFoundError:
            await self.js.add_consumer(retry_stream, retry_consumer_config)

        self.retry_subject = retry_subject
        self.retry_psub = await self.js.pull_subscribe(
            retry_subject,
            durable=retry_durable,
            stream=retry_stream,
        )

    async def _invoke_callback(self, callback: dict[str, Any] | None, payload: dict[str, Any]):
        if not callback or not isinstance(callback, dict):
            return

        subject = str(callback.get("subject", "")).strip()
        namespace = str(callback.get("namespace", "")).strip()
        method_name = str(callback.get("method_name", "")).strip()
        instance_id = str(callback.get("instance_id", "")).strip()
        if not subject and (not namespace or not method_name):
            logger.warning("skip invalid callback config: %s", callback)
            return
        if not subject:
            subject = f"{namespace}.{method_name}.{instance_id}" if instance_id else f"{namespace}.{method_name}"

        timeout = int(callback.get("timeout", self.config.callback_timeout))
        request_payload = json.dumps({"args": [payload], "kwargs": {}}, ensure_ascii=False).encode("utf-8")

        await self.nc.request(subject, request_payload, timeout=timeout)
        logger.info("callback sent: subject=%s task_id=%s", subject, payload.get("task_id"))

    async def _enqueue_callback_retry(self, callback: dict[str, Any], payload: dict[str, Any], reason: str):
        retry_payload = {
            "callback": callback,
            "payload": payload,
            "reason": reason,
            "task_id": payload.get("task_id"),
            "enqueued_at": self._now_iso(),
        }
        await self.js.publish(
            self.retry_subject,
            json.dumps(retry_payload, ensure_ascii=False).encode("utf-8"),
        )

    async def _run_task(self, task: "QueuedTask") -> dict[str, Any]:
        workspace = None
        code = -1
        output = ""
        error = ""
        callback = task.callback
        started_at = self._now_iso()
        self.task_store.update_status(task.task_id, "running", {"started_at": started_at}, self._now_iso())

        try:
            if task.task_type == "adhoc":
                request = to_adhoc_request(task.payload)
                cmd, workspace = prepare_adhoc_execution(request)
                code, output = await run_command(cmd, request.execute_timeout)
            else:
                request = to_playbook_request(task.payload)
                cmd, workspace = await prepare_playbook_execution(request)
                code, output = await run_command(cmd, request.execute_timeout)
        except Exception as err:
            error = str(err)
        finally:
            cleanup_workspace(workspace)

        success = code == 0 and not error
        if not success and not error:
            error = f"ansible {task.task_type} failed with exit code {code}"

        parsed_results = parse_ansible_output_per_host(output) if output else []

        result = {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": "success" if success else "failed",
            "success": success,
            "result": parsed_results if parsed_results else output,
            "result_summary": {
                "stdout_combined": output,
                "host_count": len(parsed_results),
            },
            "error": error,
            "started_at": started_at,
            "finished_at": self._now_iso(),
        }
        final_status = "success" if success else "failed"
        self.task_store.update_status(task.task_id, final_status, result, self._now_iso())

        if callback:
            try:
                await self._invoke_callback(callback, result)
            except Exception as callback_err:
                result["callback_error"] = str(callback_err)
                self.task_store.update_status(task.task_id, "callback_failed", result, self._now_iso())
                await self._enqueue_callback_retry(callback, result, str(callback_err))

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
            try:
                data = json.loads(msg.data.decode("utf-8"))
                task = QueuedTask.from_json(data)
                status = self.task_store.get_status(task.task_id)
                if status in {"success", "failed", "callback_failed"}:
                    await msg.ack()
                    continue

                await self._run_task(task)
                await msg.ack()
            except Exception as err:
                logger.exception("worker task failed worker=%s error=%s", worker_id, err)
                meta = msg.metadata
                if meta and meta.num_delivered >= self.config.js_max_deliver:
                    dlq_payload = {
                        "subject": msg.subject,
                        "task": msg.data.decode("utf-8", errors="replace"),
                        "error": str(err),
                        "delivered": meta.num_delivered,
                        "timestamp": self._now_iso(),
                    }
                    await self.nc.publish(
                        self.config.dlq_subject,
                        json.dumps(dlq_payload, ensure_ascii=False).encode("utf-8"),
                    )
                    await msg.ack()
                else:
                    await msg.nak()

    async def _callback_retry_loop(self):
        while True:
            try:
                msgs = await self.retry_psub.fetch(batch=1, timeout=1)
            except nats.errors.TimeoutError:
                continue
            if not msgs:
                await asyncio.sleep(0.05)
                continue

            msg = msgs[0]
            try:
                data = json.loads(msg.data.decode("utf-8"))
                callback = data.get("callback") or {}
                payload = data.get("payload") or {}
                task_id = str(data.get("task_id", ""))
                await self._invoke_callback(callback, payload)
                self.task_store.update_status(
                    task_id,
                    "success",
                    payload,
                    self._now_iso(),
                )
                await msg.ack()
            except Exception as err:
                meta = msg.metadata
                if meta and meta.num_delivered >= self.config.js_max_deliver:
                    await self.nc.publish(
                        self.config.dlq_subject,
                        json.dumps(
                            {
                                "type": "callback_retry",
                                "task": msg.data.decode("utf-8", errors="replace"),
                                "error": str(err),
                                "delivered": meta.num_delivered,
                                "timestamp": self._now_iso(),
                            },
                            ensure_ascii=False,
                        ).encode("utf-8"),
                    )
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
            payload=payload,
            callback=callback,
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
