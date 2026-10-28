"""用企微官方 SDK 维持长连接。心跳、重连和回复回执由 SDK 负责。"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, Callable

from apps.core.logger import opspilot_logger as logger

_SDK_HEARTBEAT_MS = 30_000
_AUTH_TIMEOUT_SECONDS = 10
_REPLY_TIMEOUT_SECONDS = 15
_REPLY_ACK_TIMEOUT_SECONDS = 15

_IGNORED_COMMANDS = frozenset({"aibot_subscribe", "ping"})


class _SdkLogger:
    """SDK 要求 warn，而项目日志用 warning。"""

    def debug(self, message: str, *args: Any) -> None:
        logger.debug(message, *args)

    def info(self, message: str, *args: Any) -> None:
        logger.info(message, *args)

    def warn(self, message: str, *args: Any) -> None:
        logger.warning(message, *args)

    def error(self, message: str, *args: Any) -> None:
        logger.error(message, *args)


class WecomSdkTransport:
    """把官方 WSClient 收成现有会话循环使用的收发接口。"""

    owns_heartbeat = True

    def __init__(self, url: str, bot_id: str, secret: str, client_factory: Callable[[Any], Any] | None = None):
        self.url = url
        self.bot_id = bot_id
        self.secret = secret
        self._client_factory = client_factory or _default_client_factory
        self._frames: queue.Queue[dict] = queue.Queue()
        self._ready = threading.Event()
        self._authenticated = threading.Event()
        self._error: BaseException | None = None
        self._closed = threading.Event()
        self._post_auth_error_pending = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self._stopped: asyncio.Event | None = None
        self._thread = threading.Thread(target=self._run, name=f"wecom-sdk-{bot_id}", daemon=True)
        self._thread.start()
        if not self._ready.wait(_AUTH_TIMEOUT_SECONDS + 5):
            self.close()
            raise TimeoutError("WecomSdkConnectTimeout")
        if self._error is not None:
            self.close()
            raise self._error

    def send_json(self, payload: dict) -> None:
        cmd = payload.get("cmd")
        if cmd in _IGNORED_COMMANDS:
            return
        if cmd != "aibot_respond_msg":
            return
        if self._loop is None or self._client is None:
            raise RuntimeError("WecomSdkNotConnected")
        body = payload.get("body") or {}
        stream = body.get("stream") or {}
        frame = {"headers": payload.get("headers") or {}}
        reply_kwargs = {}
        msg_item = stream.get("msg_item")
        if msg_item:
            reply_kwargs["msg_item"] = msg_item
        future = asyncio.run_coroutine_threadsafe(
            self._client.reply_stream(
                frame,
                stream.get("id") or "",
                stream.get("content") or "",
                bool(stream.get("finish")),
                **reply_kwargs,
            ),
            self._loop,
        )
        future.result(timeout=_REPLY_TIMEOUT_SECONDS)

    def exchange(self, payload: dict) -> dict:
        """发送一帧并等待回执。上传素材和文件回复都走这里。"""
        if self._loop is None or self._client is None:
            raise RuntimeError("WecomSdkNotConnected")
        frame = {"headers": payload.get("headers") or {}}
        future = asyncio.run_coroutine_threadsafe(
            self._client.reply(frame, payload.get("body") or {}, payload.get("cmd") or "aibot_respond_msg"),
            self._loop,
        )
        ack = future.result(timeout=_REPLY_TIMEOUT_SECONDS)
        return ack if isinstance(ack, dict) else {}

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def _raise_if_unusable(self) -> None:
        if self._closed.is_set():
            raise ConnectionError("WecomSdkClosed")
        if self._authenticated.is_set() and not self._thread.is_alive():
            raise ConnectionError("WecomSdkThreadStopped")

    def recv_json(self, timeout: float):
        self._raise_if_unusable()
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            self._raise_if_unusable()
            raise TimeoutError()

    def close(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        if self._stopped is not None:
            loop.call_soon_threadsafe(self._stopped.set)
        if self._client is not None:
            loop.call_soon_threadsafe(self._client.disconnect)

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            self._error = exc
            self._ready.set()

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stopped = asyncio.Event()
        client = self._client_factory(_client_options(self.url, self.bot_id, self.secret))
        self._client = client
        ws_manager = getattr(client, "_ws_manager", None)
        if ws_manager is not None:
            ws_manager._reply_ack_timeout = max(
                float(getattr(ws_manager, "_reply_ack_timeout", 5.0)),
                _REPLY_ACK_TIMEOUT_SECONDS,
            )

        def enqueue(frame):
            if isinstance(frame, dict):
                self._frames.put(frame)

        def on_authenticated():
            self._authenticated.set()

        def on_disconnected(reason):
            # 常规断线走 SDK disconnected + 内置重连（max_reconnect_attempts=-1），勿置 closed。
            logger.info(
                "WecomSdkDisconnected bot_id=%s reason=%s",
                self.bot_id,
                str(reason)[:200],
            )

        def on_reconnecting(attempt):
            # connect() 失败会先 error 再 _schedule_reconnect。清掉待关闭，避免拆掉 SDK 退避。
            self._post_auth_error_pending = False
            logger.info("WecomSdkReconnecting bot_id=%s attempt=%s", self.bot_id, attempt)

        def on_error(error):
            if self._authenticated.is_set():
                logger.warning(
                    "WecomSdkErrorAfterAuth bot_id=%s error_type=%s",
                    self.bot_id,
                    type(error).__name__ if isinstance(error, BaseException) else "RuntimeError",
                )
                self._post_auth_error_pending = True
                if self._loop is not None:
                    self._loop.call_soon(self._close_if_reconnect_not_scheduled)
                return
            self._error = error if isinstance(error, BaseException) else RuntimeError(str(error))
            self._authenticated.set()

        client.on("message", enqueue)
        client.on("event", enqueue)
        client.on("authenticated", on_authenticated)
        client.on("disconnected", on_disconnected)
        client.on("reconnecting", on_reconnecting)
        client.on("error", on_error)
        try:
            await client.connect()
            await asyncio.wait_for(self._wait_authenticated(), _AUTH_TIMEOUT_SECONDS)
        except Exception as exc:
            self._error = self._error or exc
        self._ready.set()
        if self._error is not None:
            self._closed.set()
            return
        try:
            await self._stopped.wait()
        finally:
            self._closed.set()

    def _close_if_reconnect_not_scheduled(self) -> None:
        """error 之后若同一轮没有 reconnecting，SDK 不会再连，交给 Leader 重建。"""
        if not self._post_auth_error_pending:
            return
        self._post_auth_error_pending = False
        logger.warning("WecomSdkUnrecoverable bot_id=%s", self.bot_id)
        self._closed.set()

    async def _wait_authenticated(self) -> None:
        while not self._authenticated.is_set():
            await asyncio.sleep(0.01)


def open_wecom_sdk_transport(url: str, bot_id: str, secret: str) -> WecomSdkTransport:
    return WecomSdkTransport(url, bot_id, secret)


def _client_options(url: str, bot_id: str, secret: str):
    from aibot import WSClientOptions

    return WSClientOptions(
        bot_id=bot_id,
        secret=secret,
        ws_url=url,
        heartbeat_interval=_SDK_HEARTBEAT_MS,
        max_reconnect_attempts=-1,
        logger=_SdkLogger(),
    )


def _default_client_factory(options):
    # 官方 SDK 只在常驻进程里用，避免 API 进程导入时拉起 aiohttp。
    from aibot import WSClient

    return WSClient(options)
