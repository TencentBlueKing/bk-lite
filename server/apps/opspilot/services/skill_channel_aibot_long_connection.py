"""智能体企微机器人长连接：明文帧、流式回覆、环境内单连接。"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils

DEFAULT_LONG_CONNECTION_URL = "wss://openws.work.weixin.qq.com"
LONG_CONNECTION_URL_ENV = "WECOM_AIBOT_LONG_CONNECTION_URL"
LEADER_LOCK_KEY = "opspilot:wecom-aibot-long-connection:leader"
LEADER_LOCK_TTL_SECONDS = 30

PROCESSING_TEXT = "正在处理"
TIMEOUT_TEXT = "处理超时，请再发一次"
UNSUPPORTED_TEXT = "当前仅支持文本消息"
FAILURE_TEXT = "处理失败，请稍后重试"
EMPTY_ANSWER_TEXT = "处理完成，但未产生可展示内容"

STREAM_REFRESH_SECONDS = 2
STREAM_DEADLINE_SECONDS = 10 * 60
# 企微约 10 分钟关掉这条流。提前结束，结束帧才发得出去。
STREAM_FINISH_LEAD_SECONDS = 30
HEARTBEAT_SECONDS = 30

NON_TEXT_MSGTYPES = frozenset({"image", "file", "voice", "video", "mixed"})

SUBSCRIBE_LOG_TEMPLATE = "event=wecom_aibot_long_connection_subscribed channel_id=%s"
CONNECT_FAILED_LOG_TEMPLATE = "event=wecom_aibot_long_connection_connect_failed channel_id=%s failed_stage=connect error_type=%s"
TRANSPORT_FAILED_LOG_TEMPLATE = "event=wecom_aibot_long_connection_transport_failed channel_id=%s failed_stage=read error_type=%s"
REPLY_FINISHED_LOG_TEMPLATE = "event=wecom_aibot_long_connection_reply_finished channel_id=%s outcome=%s"

_RENEW_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
end
return 0
"""


def long_connection_url() -> str:
    configured = (os.environ.get(LONG_CONNECTION_URL_ENV) or "").strip()
    return configured or DEFAULT_LONG_CONNECTION_URL


def long_connection_credentials(config: dict[str, Any] | None) -> tuple[str, str] | None:
    """已选长连接且 BotID、长连接 Secret 都有值时返回凭据。"""
    config = config or {}
    if config.get("connectionMode") != "websocket":
        return None
    websocket = config.get("websocket") or {}
    if not isinstance(websocket, dict):
        return None
    bot_id = websocket.get("botId") or websocket.get("bot_id") or ""
    secret = websocket.get("secret") or ""
    if isinstance(bot_id, str):
        bot_id = bot_id.strip()
    else:
        bot_id = ""
    if isinstance(secret, str):
        secret = secret.strip()
    else:
        secret = ""
    if not bot_id or not secret:
        return None
    return bot_id, secret


def visible_answer_delta(event: dict[str, Any]) -> str | None:
    """流式正文只保留最终回答，丢掉思考、工具和规划 JSON。"""
    if not isinstance(event, dict) or event.get("type") != "TEXT_MESSAGE_CONTENT":
        return None
    delta = event.get("delta") or ""
    if not isinstance(delta, str) or not delta:
        return None
    stripped = delta.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get("phase") in {"planning", "planned", "replanning", "idle", "start", "end"}:
            return None
    return delta


class LeaderLock:
    """Redis 锁选出唯一持有者。只有持锁进程建立连接并续期。"""

    def __init__(self, redis, token: str, *, key: str = LEADER_LOCK_KEY, ttl_seconds: int = LEADER_LOCK_TTL_SECONDS):
        self.redis = redis
        self.token = token
        self.key = key
        self.ttl_seconds = ttl_seconds

    def acquire_or_renew(self) -> bool:
        if self.redis is None:
            return False
        if self.held():
            return self.renew()
        return bool(self.redis.set(self.key, self.token, nx=True, ex=self.ttl_seconds))

    def held(self) -> bool:
        if self.redis is None:
            return False
        current = self.redis.get(self.key)
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        return current == self.token

    def renew(self) -> bool:
        if self.redis is None:
            return False
        renewed = self.redis.eval(self._script(), 1, self.key, self.token, self.ttl_seconds)
        return bool(renewed)

    @staticmethod
    def _script() -> str:
        return _RENEW_LOCK_SCRIPT


class AnswerRequest:
    """一轮智能体执行。取消后后续 publish/finish/fail 不再改企微消息。"""

    def __init__(self, session: WecomAibotConnection, turn: Turn):
        self.session = session
        self.turn = turn
        self.channel = session.channel
        self.user_message = turn.user_message
        self.external_user_id = turn.external_user_id
        self.session_id = turn.session_id
        self.cancelled = False

    def publish(self, text: str) -> None:
        self.session.note_generated(self.turn, text or "")

    def finish(self) -> None:
        self.session.complete_turn(self.turn)

    def fail(self, message: str | None = None) -> None:
        self.session.fail_turn(self.turn, message)


@dataclass
class Turn:
    req_id: str
    stream_id: str
    session_key: str
    session_id: str
    external_user_id: str
    user_message: str
    started_at: float
    last_sent_at: float
    displayed: str = ""
    generated: str = ""
    closed: bool = False
    request: AnswerRequest | None = None


@dataclass
class LiveConnection:
    bot_id: str
    secret: str
    channel_id: int
    transport: Any
    session: WecomAibotConnection
    last_ping_at: float = 0


class WecomAibotConnection:
    """一条企微长连接上的入站帧与流式回覆。"""

    def __init__(self, channel, transport, agent_runner: Callable[[AnswerRequest], None], clock=None):
        self.channel = channel
        self.transport = transport
        self.agent_runner = agent_runner
        self.clock = clock or _MonotonicClock()
        self._lock = threading.Lock()
        self._turns: dict[str, Turn] = {}

    def send_subscribe(self, bot_id: str, secret: str) -> None:
        self.transport.send_json(
            {
                "cmd": "aibot_subscribe",
                "headers": {"req_id": uuid.uuid4().hex},
                "body": {"bot_id": bot_id, "secret": secret},
            }
        )
        logger.info(SUBSCRIBE_LOG_TEMPLATE, self.channel.id)

    def handle_frame(self, frame: dict[str, Any]) -> str | None:
        """处理一帧。被新连接踢掉时返回 ``kicked``。"""
        if not isinstance(frame, dict):
            return None
        cmd = frame.get("cmd")
        body = frame.get("body") or {}
        if cmd == "aibot_event_callback":
            eventtype = ((body.get("event") or {}) if isinstance(body, dict) else {}).get("eventtype")
            if eventtype == "disconnected_event":
                return "kicked"
            return None
        if cmd != "aibot_msg_callback" or not isinstance(body, dict):
            return None
        msgtype = body.get("msgtype")
        if msgtype == "event":
            return None
        req_id = ((frame.get("headers") or {}).get("req_id")) or ""
        if msgtype in NON_TEXT_MSGTYPES:
            self._reply_unsupported(req_id)
            return None
        if msgtype != "text":
            return None
        self._start_text_turn(body, req_id)
        return None

    def tick(self) -> None:
        now = self.clock.now()
        with self._lock:
            for turn in list(self._turns.values()):
                self._apply_deadline(turn, now)
                self._maybe_refresh(turn, now)

    def note_generated(self, turn: Turn, text: str) -> None:
        now = self.clock.now()
        with self._lock:
            if turn.closed or (turn.request and turn.request.cancelled):
                return
            turn.generated = text
            self._maybe_refresh(turn, now)

    def complete_turn(self, turn: Turn) -> None:
        with self._lock:
            if turn.closed or (turn.request and turn.request.cancelled):
                return
            turn.closed = True
            content = (turn.generated or "").strip() or EMPTY_ANSWER_TEXT
            self._send_stream(turn, content, finish=True)
            self._persist_assistant(turn, content)
            self._turns.pop(turn.session_key, None)
        logger.info(REPLY_FINISHED_LOG_TEMPLATE, self.channel.id, "completed")

    def fail_turn(self, turn: Turn, message: str | None = None) -> None:
        with self._lock:
            if turn.closed or (turn.request and turn.request.cancelled):
                return
            turn.closed = True
            content = message or FAILURE_TEXT
            self._send_stream(turn, content, finish=True)
            self._persist_assistant(turn, content)
            self._turns.pop(turn.session_key, None)
        logger.info(REPLY_FINISHED_LOG_TEMPLATE, self.channel.id, "failed")

    def _start_text_turn(self, body: dict[str, Any], req_id: str) -> None:
        raw = ((body.get("text") or {}) if isinstance(body.get("text"), dict) else {}).get("content") or ""
        cleaned = EnterpriseWechatAibotChatFlowUtils.clean_text_message(raw if isinstance(raw, str) else "")
        session_id, external_user_id = _conversation_identity(body)
        session_key = session_id or external_user_id or req_id
        now = self.clock.now()
        previous = None
        with self._lock:
            previous = self._turns.get(session_key)
            if previous is not None:
                self._interrupt_locked(previous)
            turn = Turn(
                req_id=req_id,
                stream_id=uuid.uuid4().hex,
                session_key=session_key,
                session_id=session_id,
                external_user_id=external_user_id,
                user_message=cleaned,
                started_at=now,
                last_sent_at=now,
            )
            request = AnswerRequest(self, turn)
            turn.request = request
            self._turns[session_key] = turn
            self._persist_user(turn)
            self._send_stream(turn, PROCESSING_TEXT, finish=False)
            turn.displayed = PROCESSING_TEXT
        self.agent_runner(request)

    def _interrupt_locked(self, turn: Turn) -> None:
        if turn.request is not None:
            turn.request.cancelled = True
        if turn.closed:
            return
        turn.closed = True
        self._send_stream(turn, turn.displayed or PROCESSING_TEXT, finish=True)
        generated = (turn.generated or "").strip()
        if generated:
            self._persist_assistant(turn, turn.generated)
        self._turns.pop(turn.session_key, None)
        logger.info(REPLY_FINISHED_LOG_TEMPLATE, self.channel.id, "interrupted")

    def _apply_deadline(self, turn: Turn, now: float) -> None:
        if turn.closed:
            return
        if now - turn.started_at < STREAM_DEADLINE_SECONDS - STREAM_FINISH_LEAD_SECONDS:
            return
        if turn.request is not None:
            turn.request.cancelled = True
        turn.closed = True
        generated = (turn.generated or "").strip()
        content = turn.generated if generated else TIMEOUT_TEXT
        self._send_stream(turn, content, finish=True)
        self._persist_assistant(turn, content)
        self._turns.pop(turn.session_key, None)
        logger.info(REPLY_FINISHED_LOG_TEMPLATE, self.channel.id, "timeout")

    def _maybe_refresh(self, turn: Turn, now: float) -> None:
        if turn.closed:
            return
        generated = turn.generated or ""
        if not generated.strip():
            return
        if generated == turn.displayed:
            return
        if now - turn.last_sent_at < STREAM_REFRESH_SECONDS:
            return
        self._send_stream(turn, generated, finish=False)
        turn.displayed = generated
        turn.last_sent_at = now

    def _reply_unsupported(self, req_id: str) -> None:
        turn = Turn(
            req_id=req_id,
            stream_id=uuid.uuid4().hex,
            session_key="",
            session_id="",
            external_user_id="",
            user_message="",
            started_at=self.clock.now(),
            last_sent_at=self.clock.now(),
        )
        self._send_stream(turn, UNSUPPORTED_TEXT, finish=True)

    def _send_stream(self, turn: Turn, content: str, *, finish: bool) -> None:
        text = EnterpriseWechatAibotChatFlowUtils.truncate_markdown(content or "")
        self.transport.send_json(
            {
                "cmd": "aibot_respond_msg",
                "headers": {"req_id": turn.req_id},
                "body": {
                    "msgtype": "stream",
                    "stream": {
                        "id": turn.stream_id,
                        "finish": finish,
                        "content": text,
                    },
                },
            }
        )

    def _persist_user(self, turn: Turn) -> None:
        from apps.opspilot.models import SkillConversationMessage
        from apps.opspilot.services.skill_channel_chat_service import append_message, get_or_create_conversation

        conversation = get_or_create_conversation(self.channel, turn.external_user_id, turn.session_id or None)
        append_message(conversation, SkillConversationMessage.ROLE_USER, turn.user_message)

    def _persist_assistant(self, turn: Turn, content: str) -> None:
        from apps.opspilot.models import SkillConversationMessage
        from apps.opspilot.services.skill_channel_chat_service import append_message, get_or_create_conversation
        from apps.opspilot.services.skill_memory_service import maybe_schedule_skill_memory_write

        conversation = get_or_create_conversation(self.channel, turn.external_user_id, turn.session_id or None)
        append_message(conversation, SkillConversationMessage.ROLE_ASSISTANT, content)
        maybe_schedule_skill_memory_write(conversation)


class WecomAibotLongConnectionLeader:
    """一个进程维护全部长连接。未持锁时不建立连接。"""

    def __init__(
        self, lock: LeaderLock, opener: Callable[[str], Any], agent_runner: Callable[[AnswerRequest], None], clock=None, url: str | None = None
    ):
        self.lock = lock
        self.opener = opener
        self.agent_runner = agent_runner
        self.clock = clock or _MonotonicClock()
        self.url = url if url is not None else long_connection_url()
        self._live: dict[str, LiveConnection] = {}
        self._desired: dict[str, tuple[Any, str]] = {}

    def reconcile(self, channels) -> None:
        if not self.lock.acquire_or_renew():
            self.stop_all()
            return
        desired: dict[str, tuple[Any, str]] = {}
        for channel in channels:
            if not getattr(channel, "enabled", False):
                continue
            creds = long_connection_credentials(getattr(channel, "channel_config", None))
            if creds is None:
                continue
            bot_id, secret = creds
            if bot_id in desired:
                continue
            desired[bot_id] = (channel, secret)
        self._desired = desired
        for bot_id in list(self._live):
            live = self._live[bot_id]
            wanted = desired.get(bot_id)
            if wanted is None or wanted[0].id != live.channel_id or wanted[1] != live.secret:
                self._stop_bot(bot_id)
        for bot_id, (channel, secret) in desired.items():
            if bot_id not in self._live:
                self._connect(channel, bot_id, secret)

    def handle_transport_frame(self, bot_id: str, frame: dict[str, Any]) -> None:
        live = self._live.get(bot_id)
        if live is None:
            return
        outcome = live.session.handle_frame(frame)
        if outcome == "kicked":
            self._on_connection_lost(bot_id)

    def on_transport_closed(self, bot_id: str) -> None:
        self._on_connection_lost(bot_id)

    def pump(self) -> None:
        if not self.lock.held():
            self.stop_all()
            return
        now = self.clock.now()
        for bot_id, live in list(self._live.items()):
            live.session.tick()
            self._maybe_ping(live, now)
            recv = getattr(live.transport, "recv_json", None)
            if recv is None:
                continue
            try:
                frame = recv(0.05)
            except TimeoutError:
                continue
            except Exception as exc:
                logger.warning(
                    TRANSPORT_FAILED_LOG_TEMPLATE,
                    live.channel_id,
                    type(exc).__name__,
                )
                self._on_connection_lost(bot_id)
                continue
            if frame:
                self.handle_transport_frame(bot_id, frame)

    def stop_all(self) -> None:
        for bot_id in list(self._live):
            self._stop_bot(bot_id)

    def _on_connection_lost(self, bot_id: str) -> None:
        wanted = self._desired.get(bot_id)
        self._stop_bot(bot_id)
        if self.lock.held() and wanted is not None:
            self._connect(wanted[0], bot_id, wanted[1])
        elif not self.lock.held():
            self.stop_all()

    def _connect(self, channel, bot_id: str, secret: str) -> None:
        try:
            transport = self.opener(self.url)
        except Exception as exc:
            logger.warning(CONNECT_FAILED_LOG_TEMPLATE, channel.id, type(exc).__name__)
            return
        session = WecomAibotConnection(channel, transport, self.agent_runner, clock=self.clock)
        try:
            session.send_subscribe(bot_id, secret)
        except Exception as exc:
            logger.warning(CONNECT_FAILED_LOG_TEMPLATE, channel.id, type(exc).__name__)
            _close_transport(transport)
            return
        self._live[bot_id] = LiveConnection(
            bot_id=bot_id,
            secret=secret,
            channel_id=channel.id,
            transport=transport,
            session=session,
            last_ping_at=self.clock.now(),
        )

    def _stop_bot(self, bot_id: str) -> None:
        live = self._live.pop(bot_id, None)
        if live is None:
            return
        _close_transport(live.transport)

    def _maybe_ping(self, live: LiveConnection, now: float) -> None:
        if now - live.last_ping_at < HEARTBEAT_SECONDS:
            return
        try:
            live.transport.send_json({"cmd": "ping", "headers": {"req_id": uuid.uuid4().hex}})
        except Exception as exc:
            logger.warning(TRANSPORT_FAILED_LOG_TEMPLATE, live.channel_id, type(exc).__name__)
            self._on_connection_lost(live.bot_id)
            return
        live.last_ping_at = now


def open_wecom_websocket(url: str):
    from websockets.sync.client import connect

    # 企微只认应用层 cmd=ping。库默认的协议层 ping 约 40 秒无 pong 就会把连接拆掉。
    socket = connect(url, open_timeout=10, close_timeout=5, ping_interval=None)
    return _WebSocketTransport(socket)


class _WebSocketTransport:
    def __init__(self, socket):
        self.socket = socket

    def send_json(self, payload: dict) -> None:
        self.socket.send(json.dumps(payload, ensure_ascii=False))

    def recv_json(self, timeout: float):
        try:
            raw = self.socket.recv(timeout=timeout)
        except TimeoutError:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def close(self) -> None:
        self.socket.close()


def load_long_connection_channels():
    from apps.opspilot.enum import SkillChannelChoices
    from apps.opspilot.models import SkillChannel

    channels = (
        SkillChannel.objects.filter(
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
            enabled=True,
        )
        .select_related("skill")
        .order_by("id")
    )
    return [channel for channel in channels if long_connection_credentials(channel.channel_config)]


def redis_client_from_env():
    url = (os.environ.get("REDIS_CACHE_URL") or os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return None
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


class _MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


def _conversation_identity(body: dict[str, Any]) -> tuple[str, str]:
    sender = ""
    sender_info = body.get("from") or {}
    if isinstance(sender_info, dict):
        sender = sender_info.get("userid") or ""
    if not isinstance(sender, str):
        sender = ""
    chatid = body.get("chatid") or ""
    if not isinstance(chatid, str):
        chatid = ""
    return chatid or sender, sender


def _close_transport(transport) -> None:
    close = getattr(transport, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        logger.debug("event=wecom_aibot_long_connection_close_ignored")
