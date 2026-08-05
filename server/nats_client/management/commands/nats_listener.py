import asyncio
import json

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


class Command(BaseCommand):
    help = "Starts a NATS listener."

    def __init__(self, *args, **kwargs):
        self.nats = Client()
        self.js = None
        self._message_queue = None
        self._worker_tasks = set()
        self._fetch_tasks = set()

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
            asyncio.ensure_future(self.nats_coroutine())
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            loop.run_until_complete(self.shutdown())
            loop.run_until_complete(self.nats.close())
            loop.close()

    def _create_tracked_task(self, coroutine, tasks):
        task = asyncio.create_task(coroutine)
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return task

    def _start_workers(self):
        if self._worker_tasks:
            return

        concurrency = max(1, getattr(settings, "NATS_HANDLER_CONCURRENCY", 64))
        queue_size = max(1, getattr(settings, "NATS_HANDLER_QUEUE_SIZE", 1024))
        self._message_queue = asyncio.Queue(maxsize=queue_size)
        for _ in range(concurrency):
            self._create_tracked_task(self._worker(), self._worker_tasks)

    async def _worker(self):
        while True:
            func_name, data, reply, completion = await self._message_queue.get()
            try:
                await self.handler(func_name, data, reply=reply)
            except asyncio.CancelledError:
                if completion is not None and not completion.done():
                    completion.cancel()
                raise
            except Exception as error:  # pylint: disable=broad-except
                if completion is not None and not completion.done():
                    completion.set_exception(error)
                else:
                    logger.exception("NATS handler failed: %s", func_name)
            else:
                if completion is not None and not completion.done():
                    completion.set_result(None)
            finally:
                self._message_queue.task_done()

    async def _enqueue(self, func_name, data, reply=None, completion=None):
        await self._message_queue.put((func_name, data, reply, completion))

    async def _fetch(self, psub):
        while True:
            try:
                msgs = await psub.fetch(timeout=1)
            except nats.errors.TimeoutError:
                continue

            for msg in msgs:
                data = msg.data.decode()
                func_name = msg.subject
                print(f"Received a message on JetStream function `{func_name}`: {data}")
                completion = asyncio.get_running_loop().create_future()
                await self._enqueue(func_name, data, completion=completion)
                try:
                    await completion
                except Exception:  # pylint: disable=broad-except
                    logger.exception("JetStream handler failed; message left unacked: %s", func_name)
                    continue
                await msg.ack()

    async def shutdown(self):
        tasks = [*self._fetch_tasks, *self._worker_tasks]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._fetch_tasks.clear()
        self._worker_tasks.clear()

    async def nats_coroutine(self):
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
            await self._enqueue(func_name, data, reply=reply)

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
                self._create_tracked_task(self._fetch(psub), self._fetch_tasks)
            else:
                full_name = f'{data["namespace"]}.{data["name"]}'

                # 默认使用消息组模式,支持负载均衡，以后可以考虑根据注册参数来决定是否使用消息组模式
                await self.nats.subscribe(full_name, full_name, cb=callback)
            print(f"     - {full_name}" + (" (JetStream)" if data["js"] else ""))

    async def handler(self, func_name: str, body, reply=None):
        try:
            data = json.loads(body)
            r = await nats_handler(func_name, data)
        except Exception as e:  # pylint: disable=broad-except
            if reply:
                if isinstance(e, ValidationError):
                    message = e.message_dict
                else:
                    message = str(e)
                    try:
                        message = json.loads(message)
                    except json.JSONDecodeError:
                        pass

                await self.nats.publish(
                    reply,
                    json.dumps(
                        {
                            "success": False,
                            "error": e.__class__.__name__,
                            "message": message,
                            "pickled_exc": jsonpickle.encode(e),
                        }
                    ).encode(),
                )
            raise e

        if reply:
            await self.nats.publish(reply, json.dumps({"success": True, "result": r}, cls=DjangoJSONEncoder).encode())
