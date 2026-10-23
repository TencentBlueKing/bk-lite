"""飞书官方 SDK 适配。连接、心跳和重连仍由 lark.ws.Client 完成。"""

from __future__ import annotations

import asyncio
import io
import json
import queue
import threading

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateFileRequest,
    CreateFileRequestBody,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    UpdateMessageRequest,
    UpdateMessageRequestBody,
)
from lark_oapi.core.enum import AccessTokenType
from lark_oapi.core.model import BaseRequest
from lark_oapi.ws import client as ws_client

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.skill_channel_feishu_long_connection import FeishuDeliveryError, FeishuInbound

_LOOP_READY = threading.Lock()
_LOOP: asyncio.AbstractEventLoop | None = None


def inbound_from_event(event: P2ImMessageReceiveV1) -> FeishuInbound | None:
    payload = getattr(event, "event", None)
    message = getattr(payload, "message", None)
    sender = getattr(payload, "sender", None)
    if message is None:
        return None
    message_id = message.message_id or ""
    if not message_id:
        return None
    mentions = []
    for item in message.mentions or []:
        identity = getattr(item, "id", None)
        mentions.append(
            {
                "key": item.key or "",
                "open_id": getattr(identity, "open_id", None) or "",
            }
        )
    sender_id = getattr(sender, "sender_id", None)
    return FeishuInbound(
        message_id=message_id,
        chat_id=message.chat_id or "",
        chat_type=message.chat_type or "",
        message_type=message.message_type or "",
        text=_text_content(message.content, message.message_type),
        mentions=mentions,
        sender_open_id=getattr(sender_id, "open_id", None) or "",
        sender_type=getattr(sender, "sender_type", None) or "user",
    )


def _text_content(content: str | None, message_type: str | None) -> str:
    if message_type != "text" or not content:
        return ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return ""
    text = payload.get("text") if isinstance(payload, dict) else ""
    return text if isinstance(text, str) else ""


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """官方 Client.start 会独占导入时的事件循环。多应用共用一个循环，才能在同一进程里各连一条。"""
    global _LOOP
    with _LOOP_READY:
        if _LOOP is not None:
            return _LOOP
        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            ws_client.loop = loop
            loop.run_forever()

        threading.Thread(target=_run, name="feishu-long-connection-loop", daemon=True).start()
        _LOOP = loop
        return loop


def _boot(client: lark.ws.Client) -> None:
    try:
        loop = _ensure_loop()

        async def start() -> None:
            try:
                await client._connect()
            except Exception:
                await client._disconnect()
                if client._auto_reconnect:
                    await client._reconnect()
                else:
                    raise
            loop.create_task(client._ping_loop())

        asyncio.run_coroutine_threadsafe(start(), loop).result(timeout=30)
    except Exception as exc:
        logger.warning("event=feishu_long_connection_sdk_connect_failed failed_stage=connect error_type=%s", type(exc).__name__)
        raise


def _shutdown(client: lark.ws.Client) -> None:
    loop = _LOOP
    if loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(client._disconnect(), loop).result(timeout=5)
    except Exception as exc:
        logger.warning("event=feishu_long_connection_sdk_disconnect_failed failed_stage=disconnect error_type=%s", type(exc).__name__)


class LarkFeishuTransport:
    """一个飞书应用的长连接和开放接口。事件回调只入队。"""

    def __init__(self, app_id: str, app_secret: str):
        self._events: queue.Queue[FeishuInbound] = queue.Queue()
        handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(self._on_message).build()
        self._ws = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.WARNING,
            domain=lark.FEISHU_DOMAIN,
        )
        self._api = lark.Client.builder().app_id(app_id).app_secret(app_secret).domain(lark.FEISHU_DOMAIN).build()
        self._bot_open_id = ""
        _boot(self._ws)

    def poll(self, timeout: float) -> FeishuInbound | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        _shutdown(self._ws)

    def bot_open_id(self) -> str:
        if self._bot_open_id:
            return self._bot_open_id
        request = BaseRequest.builder().http_method(lark.HttpMethod.GET).uri("/open-apis/bot/v3/info").token_types({AccessTokenType.TENANT}).build()
        response = self._api.request(request)
        if not response.success():
            raise FeishuDeliveryError("bot info rejected")
        try:
            payload = json.loads(response.raw.content.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FeishuDeliveryError("bot info unreadable") from exc
        open_id = ((payload.get("bot") or {}).get("open_id")) or ""
        if not isinstance(open_id, str) or not open_id:
            raise FeishuDeliveryError("bot info missing open_id")
        self._bot_open_id = open_id
        return open_id

    def reply_text(self, message_id: str, text: str) -> str:
        response = self._api.im.v1.message.reply(_text_reply(message_id, text))
        if not response.success() or response.data is None or not response.data.message_id:
            raise FeishuDeliveryError("reply rejected")
        return response.data.message_id

    def update_text(self, message_id: str, text: str) -> None:
        body = UpdateMessageRequestBody.builder().msg_type("text").content(_text_body(text)).build()
        request = UpdateMessageRequest.builder().message_id(message_id).request_body(body).build()
        response = self._api.im.v1.message.update(request)
        if not response.success():
            raise FeishuDeliveryError("update rejected")

    def reply_file(self, message_id: str, filename: str, content: bytes) -> None:
        file_key = self._upload(filename, content)
        body = ReplyMessageRequestBody.builder().msg_type("file").content(json.dumps({"file_key": file_key})).build()
        request = ReplyMessageRequest.builder().message_id(message_id).request_body(body).build()
        response = self._api.im.v1.message.reply(request)
        if not response.success():
            _reject(response, "file_reply")

    def _upload(self, filename: str, content: bytes) -> str:
        response = self._api.im.v1.file.create(upload_file_request(filename, content))
        if not response.success() or response.data is None or not response.data.file_key:
            _reject(response, "upload")
        return response.data.file_key

    def _on_message(self, event: P2ImMessageReceiveV1) -> None:
        try:
            inbound = inbound_from_event(event)
        except Exception as exc:
            logger.warning("event=feishu_long_connection_event_ignored failed_stage=parse error_type=%s", type(exc).__name__)
            return
        if inbound is not None:
            self._events.put(inbound)


def _safe_filename(filename: str) -> str:
    name = (filename or "file").replace("\\", "/").rsplit("/", 1)[-1].strip() or "file"
    name = "".join(ch for ch in name if ch not in '\\/:*?"<>|')
    return name or "file.txt"


def upload_file_request(filename: str, content: bytes) -> CreateFileRequest:
    """文件分段必须带文件名。只传 BytesIO 时官方 SDK 不会写 filename，飞书会拒收。"""
    safe_name = _safe_filename(filename)
    payload = (safe_name, io.BytesIO(content), "application/octet-stream")
    body = CreateFileRequestBody.builder().file_type("stream").file_name(safe_name).file(payload).build()
    return CreateFileRequest.builder().request_body(body).build()


def _reject(response, stage: str) -> None:
    code = getattr(response, "code", None)
    detail = getattr(response, "msg", None) or ""
    if not isinstance(detail, str):
        detail = ""
    raise FeishuDeliveryError(stage, code=str(code if code is not None else "-"), detail=detail)


def _text_body(text: str) -> str:
    return json.dumps({"text": text}, ensure_ascii=False)


def _text_reply(message_id: str, text: str) -> ReplyMessageRequest:
    body = ReplyMessageRequestBody.builder().msg_type("text").content(_text_body(text)).build()
    return ReplyMessageRequest.builder().message_id(message_id).request_body(body).build()


def open_feishu_sdk_transport(app_id: str, app_secret: str) -> LarkFeishuTransport:
    return LarkFeishuTransport(app_id, app_secret)
