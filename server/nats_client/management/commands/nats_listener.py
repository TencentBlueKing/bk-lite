import asyncio
import json
from dataclasses import dataclass

import jsonpickle
import nats.errors
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import autoreload
from nats.aio.client import Client
from nats.aio.errors import ErrNoServers, ErrTimeout
from nats.aio.msg import Msg

from apps.core.logger import nats_logger as logger

from ...clients import get_nc_client
from ...handlers import nats_handler
from ...registry import default_registry


@dataclass
class _QueuedMessage:
    func_name: str
    data: str
    reply: str | None = None
    jetstream_message: Msg | None = None
    progress_task: asyncio.Task | None = None


class _ListenerOverloadedError(RuntimeError):
    pass


class Command(BaseCommand):
    help = "Starts a NATS listener."

    def __init__(self, *args, **kwargs):
        self.nats = Client()
        self.js = None
        self._message_queue = None
        self._worker_tasks = set()
        self._fetch_tasks = set()
        self._progress_tasks = set()
        self._core_subscriptions = []
        self._stopping = False

        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--reload",
            action="store_true",
            dest="reload",
            help="Enable autoreload in development environment.",
        )

    def handle(self, *args, **options):
        reload = options.get("reload", False)
        print("** Starting NATS listener" + (" with reload enabled" if reload else ""))
        if reload:
            autoreload.run_with_reloader(self.inner_run, *args, **options)
        else:
            self.inner_run(*args, **options)

    def inner_run(self, *args, **options):
        print("** Initializing Loop")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            self._start_listener_setup(loop)
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            loop.run_until_complete(self.shutdown())
            loop.run_until_complete(self.nats.close())
            loop.close()

    def _start_listener_setup(self, loop):
        task = loop.create_task(self.nats_coroutine())

        def setup_done(completed_task):
            if completed_task.cancelled():
                return
            error = completed_task.exception()
            if error is not None:
                logger.error(
                    "NATS listener setup failed",
                    exc_info=(type(error), error, error.__traceback__),
                )
                loop.stop()

        task.add_done_callback(setup_done)
        return task

    def _create_tracked_task(self, coroutine, tasks, description):
        task = asyncio.create_task(coroutine)
        tasks.add(task)

        def task_done(completed_task):
            tasks.discard(completed_task)
            if completed_task.cancelled():
                return
            error = completed_task.exception()
            if error is not None:
                logger.error(
                    "NATS %s task stopped unexpectedly",
                    description,
                    exc_info=(type(error), error, error.__traceback__),
                )

        task.add_done_callback(task_done)
        return task

    def _start_workers(self):
        if self._worker_tasks:
            return

        concurrency = settings.NATS_HANDLER_CONCURRENCY
        queue_size = settings.NATS_HANDLER_QUEUE_SIZE
        self._message_queue = asyncio.Queue(maxsize=queue_size)
        for _ in range(concurrency):
            self._create_tracked_task(self._worker(), self._worker_tasks, "worker")

    async def _worker(self):
        while True:
            message = await self._message_queue.get()
            try:
                await self.handler(message.func_name, message.data, reply=message.reply)
            except asyncio.CancelledError:
                raise
            except Exception:  # pylint: disable=broad-except
                if message.jetstream_message is not None:
                    logger.exception("JetStream handler failed; message left unacked: %s", message.func_name)
                else:
                    logger.exception("NATS handler failed: %s", message.func_name)
            else:
                if message.jetstream_message is not None:
                    try:
                        await message.jetstream_message.ack()
                    except Exception:  # pylint: disable=broad-except
                        logger.exception("JetStream ack failed; message will be redelivered: %s", message.func_name)
            finally:
                if message.progress_task is not None:
                    message.progress_task.cancel()
                    await asyncio.gather(message.progress_task, return_exceptions=True)
                self._message_queue.task_done()

    async def _enqueue(self, func_name, data, reply=None, jetstream_message=None, progress_task=None):
        await self._message_queue.put(
            _QueuedMessage(
                func_name=func_name,
                data=data,
                reply=reply,
                jetstream_message=jetstream_message,
                progress_task=progress_task,
            )
        )

    async def _send_in_progress(self, message, interval):
        while True:
            try:
                await message.in_progress()
            except asyncio.CancelledError:
                raise
            except Exception:  # pylint: disable=broad-except
                logger.exception("JetStream in-progress heartbeat failed: %s", message.subject)
            await asyncio.sleep(interval)

    async def _enqueue_jetstream(self, message, data, func_name, progress_interval):
        progress_task = self._create_tracked_task(
            self._send_in_progress(message, progress_interval),
            self._progress_tasks,
            "in-progress heartbeat",
        )
        try:
            await self._enqueue(
                func_name,
                data,
                jetstream_message=message,
                progress_task=progress_task,
            )
        except BaseException:
            progress_task.cancel()
            await asyncio.gather(progress_task, return_exceptions=True)
            raise

    async def _fetch(self, psub, progress_interval):
        retry_delay = settings.NATS_FETCH_RETRY_DELAY
        while not self._stopping:
            try:
                msgs = await psub.fetch(timeout=1)
            except asyncio.CancelledError:
                raise
            except nats.errors.TimeoutError:
                continue
            except Exception:  # pylint: disable=broad-except
                logger.exception("JetStream fetch failed; retrying")
                await asyncio.sleep(retry_delay)
                continue

            for msg in msgs:
                data = msg.data.decode()
                func_name = msg.subject
                print(f"Received a message on JetStream function `{func_name}`: {data}")
                await self._enqueue_jetstream(msg, data, func_name, progress_interval)

    async def _jetstream_progress_interval(self, psub, subject):
        configured_interval = settings.NATS_JETSTREAM_IN_PROGRESS_INTERVAL
        try:
            consumer_info = await psub.consumer_info()
        except AttributeError:
            return configured_interval
        except Exception:  # pylint: disable=broad-except
            logger.exception("Unable to read JetStream consumer ack_wait: %s", subject)
            return configured_interval

        config = consumer_info.config
        ack_wait = config.backoff[0] if config.backoff else config.ack_wait
        if not ack_wait:
            return configured_interval
        safe_interval = max(0.01, ack_wait / 3)
        if configured_interval > safe_interval:
            logger.warning(
                "NATS_JETSTREAM_IN_PROGRESS_INTERVAL %.3fs exceeds one-third of ack_wait %.3fs; using %.3fs",
                configured_interval,
                ack_wait,
                safe_interval,
            )
        return min(configured_interval, safe_interval)

    async def shutdown(self):
        if self._message_queue is None:
            return

        self._stopping = True
        shutdown_timeout = settings.NATS_HANDLER_SHUTDOWN_TIMEOUT

        async def drain_accepted_messages():
            drain_results = await asyncio.gather(
                *(subscription.drain() for subscription in self._core_subscriptions),
                *tuple(self._fetch_tasks),
                return_exceptions=True,
            )
            for result in drain_results:
                if isinstance(result, Exception):
                    logger.error(
                        "NATS listener input drain failed",
                        exc_info=(type(result), result, result.__traceback__),
                    )
            await self._message_queue.join()

        try:
            await asyncio.wait_for(drain_accepted_messages(), timeout=shutdown_timeout)
        except asyncio.TimeoutError:
            logger.error("NATS listener graceful shutdown timed out after %.1fs", shutdown_timeout)

        tasks = [*self._fetch_tasks, *self._worker_tasks, *self._progress_tasks]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._fetch_tasks.clear()
        self._worker_tasks.clear()
        self._progress_tasks.clear()
        self._core_subscriptions.clear()
        self._message_queue = None

    async def _publish_failure(self, reply, error):
        message = error.message_dict if isinstance(error, ValidationError) else str(error)
        if not isinstance(error, ValidationError):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                pass
        await self.nats.publish(
            reply,
            json.dumps(
                {
                    "success": False,
                    "error": error.__class__.__name__,
                    "message": message,
                    "pickled_exc": jsonpickle.encode(error),
                }
            ).encode(),
        )

    async def nats_coroutine(self):
        self._stopping = False
        namespace = getattr(settings, "NATS_NAMESPACE", "default")
        durable_name = getattr(settings, "NATS_JETSTREAM_DURABLE_NAME", namespace)
        create_stream = getattr(settings, "NATS_JETSTREAM_CRATE_STREAM", True)
        stream_config = getattr(settings, "NATS_JETSTREAM_CONFIG", {})

        try:
            await get_nc_client(self.nats)
            print("** Connected to NATS server")

            if getattr(settings, "NATS_JETSTREAM_ENABLED", True):
                self.js = self.nats.jetstream()
                print("** Initialized JetStream")
        except (ErrNoServers, ErrTimeout) as e:
            raise e

        if not default_registry.registry:
            print("** No function found!")
            return

        if self.js is not None and create_stream:
            print("** Creating stream")
            stream_config.pop("name", None)
            stream_config.pop("subjects", None)
            await self.js.add_stream(
                name=namespace,
                subjects=[f"{namespace}.js.>"],
                **stream_config,
            )

        self._start_workers()

        async def callback(msg: Msg):
            data = msg.data.decode()
            reply = msg.reply
            func_name = msg.subject
            print(f"Received a message on function `{func_name}`")
            try:
                await asyncio.wait_for(
                    self._enqueue(func_name, data, reply=reply),
                    timeout=settings.NATS_HANDLER_ENQUEUE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                error = _ListenerOverloadedError("NATS listener handler queue is full")
                logger.warning("NATS handler queue full; rejecting message: %s", func_name)
                if reply:
                    await self._publish_failure(reply, error)

        print("** Listened on:")
        for data in default_registry.registry.values():
            if data["js"]:
                full_name = f'{data["namespace"]}.js.{data["name"]}'
                if self.js is None:
                    continue

                full_name_no_dot = full_name.replace(".", "-")
                psub = await self.js.pull_subscribe(
                    full_name,
                    f"{durable_name}-{full_name_no_dot}",
                )
                progress_interval = await self._jetstream_progress_interval(psub, full_name)
                self._create_tracked_task(
                    self._fetch(psub, progress_interval),
                    self._fetch_tasks,
                    f"JetStream fetch {full_name}",
                )
            else:
                full_name = f'{data["namespace"]}.{data["name"]}'

                # 默认使用消息组模式,支持负载均衡，以后可以考虑根据注册参数来决定是否使用消息组模式
                subscription = await self.nats.subscribe(
                    full_name,
                    full_name,
                    cb=callback,
                    pending_msgs_limit=settings.NATS_CORE_PENDING_MSGS_LIMIT,
                    pending_bytes_limit=settings.NATS_CORE_PENDING_BYTES_LIMIT,
                )
                if subscription is not None:
                    self._core_subscriptions.append(subscription)
            print(f"     - {full_name}" + (" (JetStream)" if data["js"] else ""))

    async def handler(self, func_name: str, body, reply=None):
        try:
            data = json.loads(body)
            r = await nats_handler(func_name, data)
        except Exception as e:  # pylint: disable=broad-except
            if reply:
                await self._publish_failure(reply, e)
            raise e

        if reply:
            await self.nats.publish(reply, json.dumps({"success": True, "result": r}, cls=DjangoJSONEncoder).encode())
