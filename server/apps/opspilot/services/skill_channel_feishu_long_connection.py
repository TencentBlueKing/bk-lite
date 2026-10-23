"""智能体飞书长连接：官方 SDK 入站、同一条消息更新、环境内单连接。"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.skill_channel_aibot_long_connection import LeaderLock
from apps.opspilot.services.skill_channel_feishu import feishu_long_connection_credentials

LEADER_LOCK_KEY = "opspilot:feishu-long-connection:leader"
LEADER_LOCK_TTL_SECONDS = 30

PROCESSING_TEXT = "正在处理"
TIMEOUT_TEXT = "处理超时，请再发一次"
UNSUPPORTED_TEXT = "当前仅支持文本消息"
FAILURE_TEXT = "处理失败，请稍后重试"
EMPTY_ANSWER_TEXT = "处理完成，但未产生可展示内容"
FILE_FAILED_TEXT = "文件发送失败，请稍后重试"

STREAM_REFRESH_SECONDS = 2
STREAM_DEADLINE_SECONDS = 10 * 60
STREAM_FINISH_LEAD_SECONDS = 30
SEEN_LIMIT = 2048
SEEN_TTL_SECONDS = float(STREAM_DEADLINE_SECONDS)

CONNECT_FAILED_LOG_TEMPLATE = "event=feishu_long_connection_connect_failed channel_id=%s failed_stage=connect error_type=%s"
REPLY_FAILED_LOG_TEMPLATE = "event=feishu_long_connection_reply_failed channel_id=%s failed_stage=%s error_type=%s"
REPLY_FINISHED_LOG_TEMPLATE = "event=feishu_long_connection_reply_finished channel_id=%s outcome=%s"
FILE_SENT_LOG_TEMPLATE = "event=feishu_long_connection_file_sent channel_id=%s"
FILE_FAILED_LOG_TEMPLATE = "event=feishu_long_connection_file_failed channel_id=%s failed_stage=%s error_type=%s error_code=%s error_detail=%s"
BOT_INFO_FAILED_LOG_TEMPLATE = "event=feishu_long_connection_bot_info_failed channel_id=%s failed_stage=bot_info error_type=%s"
DUPLICATE_APP_LOG_TEMPLATE = "event=feishu_long_connection_duplicate_app channel_id=%s"


class FeishuDeliveryError(Exception):
    """飞书开放接口拒绝了回复、更新或文件发送。"""

    def __init__(self, stage: str, *, code: str = "-", detail: str = ""):
        super().__init__(stage)
        self.stage = stage
        self.code = str(code or "-")
        self.detail = (detail or "")[:200]


@dataclass
class FeishuInbound:
    message_id: str
    chat_id: str
    chat_type: str
    message_type: str
    text: str
    mentions: list[dict[str, str]]
    sender_open_id: str
    sender_type: str = "user"


def group_text_for_bot(text: str, mentions: list[dict[str, str]], bot_open_id: str) -> str | None:
    """群消息只有单独 @ 了本机器人时才返回去掉该占位符后的正文。"""
    matched = None
    for item in mentions:
        if item.get("open_id") == bot_open_id:
            matched = item
            break
    if matched is None:
        return None
    key = matched.get("key") or ""
    if key:
        text = text.replace(key, "", 1)
    return text.strip()


def speaker_session_id(chat_id: str, sender_open_id: str) -> str:
    return f"feishu:{chat_id}:{sender_open_id}"


class AnswerRequest:
    """一轮智能体执行。取消后后续 publish/finish/fail 不再改飞书消息。"""

    def __init__(self, session: FeishuConnection, turn: Turn):
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

    def add_generated_file(self, filename: str, content: bytes) -> None:
        self.session.note_file(self.turn, filename, content)

    def fail(self, message: str | None = None) -> None:
        self.session.fail_turn(self.turn, message)


@dataclass
class Turn:
    chat_id: str
    user_message_id: str
    bubble_id: str
    session_id: str
    external_user_id: str
    user_message: str
    started_at: float
    last_sent_at: float
    displayed: str = ""
    generated: str = ""
    closed: bool = False
    replaced: bool = False
    request: AnswerRequest | None = None
    files: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass
class LiveConnection:
    app_id: str
    secret: str
    channel_id: int
    transport: Any
    session: FeishuConnection


class FeishuConnection:
    """一条飞书长连接上的入站消息与气泡更新。"""

    def __init__(self, channel, gateway, agent_runner: Callable[[AnswerRequest], None], clock=None, *, sync_agents: bool = False):
        self.channel = channel
        self.gateway = gateway
        self.agent_runner = agent_runner
        self.clock = clock or _MonotonicClock()
        self.sync_agents = sync_agents
        self._lock = threading.Lock()
        self._turns: dict[str, Turn] = {}
        self._seen = _SeenIds(self.clock)
        self._workers: list[threading.Thread] = []

    def handle(self, event: FeishuInbound) -> None:
        if event.sender_type == "app" or not event.message_id or self._seen.contains(event.message_id, self._open_message_ids()):
            return
        if event.message_type != "text":
            self._remember(event.message_id)
            self._reply_unsupported(event.message_id)
            return
        text = event.text or ""
        if event.chat_type == "group":
            try:
                bot_open_id = self.gateway.bot_open_id()
            except Exception as exc:
                logger.warning(BOT_INFO_FAILED_LOG_TEMPLATE, self.channel.id, type(exc).__name__)
                return
            visible = group_text_for_bot(text, event.mentions, bot_open_id)
            if visible is None:
                self._remember(event.message_id)
                return
            text = visible
        try:
            bubble_id = self.gateway.reply_text(event.message_id, PROCESSING_TEXT)
        except Exception as exc:
            logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "reply", type(exc).__name__)
            return
        try:
            self._begin_turn(event, text, bubble_id)
        except Exception as exc:
            logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "begin", type(exc).__name__)
            self._abort_begin(event, bubble_id)
            return
        self._remember(event.message_id)

    def wait(self, timeout: float = 5) -> None:
        for worker in list(self._workers):
            worker.join(timeout)
        self._reap_workers()

    def tick(self) -> None:
        self._reap_workers()
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

    def note_file(self, turn: Turn, filename: str, content: bytes) -> None:
        if not isinstance(content, bytes) or not content:
            return
        with self._lock:
            if turn.closed or (turn.request and turn.request.cancelled):
                return
            if any(existing == filename for existing, _content in turn.files):
                return
            turn.files.append((filename, content))

    def complete_turn(self, turn: Turn) -> None:
        files: list[tuple[str, bytes]] = []
        with self._lock:
            if turn.closed or (turn.request and turn.request.cancelled):
                return
            turn.closed = True
            content = (turn.generated or "").strip() or EMPTY_ANSWER_TEXT
            files = list(turn.files)
            self._show(turn, content)
            self._persist_assistant(turn, content)
            self._turns.pop(turn.chat_id, None)
        self._deliver_files(turn, files)
        logger.info(REPLY_FINISHED_LOG_TEMPLATE, self.channel.id, "completed")

    def fail_turn(self, turn: Turn, message: str | None = None) -> None:
        with self._lock:
            if turn.closed or (turn.request and turn.request.cancelled):
                return
            turn.closed = True
            content = (message or "").strip() or FAILURE_TEXT
            self._show(turn, content)
            self._persist_assistant(turn, content)
            self._turns.pop(turn.chat_id, None)
        logger.info(REPLY_FINISHED_LOG_TEMPLATE, self.channel.id, "failed")

    def cancel_all(self) -> None:
        with self._lock:
            for turn in list(self._turns.values()):
                if turn.request is not None:
                    turn.request.cancelled = True
                turn.closed = True
            self._turns.clear()

    def _begin_turn(self, event: FeishuInbound, text: str, bubble_id: str) -> None:
        now = self.clock.now()
        sender = event.sender_open_id or event.message_id
        with self._lock:
            previous = self._turns.get(event.chat_id)
            if previous is not None:
                self._interrupt_locked(previous)
            turn = Turn(
                chat_id=event.chat_id,
                user_message_id=event.message_id,
                bubble_id=bubble_id,
                session_id=speaker_session_id(event.chat_id, sender),
                external_user_id=sender,
                user_message=text,
                started_at=now,
                last_sent_at=now,
                displayed=PROCESSING_TEXT,
            )
            request = AnswerRequest(self, turn)
            turn.request = request
            self._turns[event.chat_id] = turn
            self._persist_user(turn)
        if self.sync_agents:
            self._run_agent(request)
            return
        self._start_worker(request)

    def _start_worker(self, request: AnswerRequest) -> None:
        self._reap_workers()
        worker = threading.Thread(target=self._run_agent, args=(request,), daemon=True)
        worker.start()
        self._workers.append(worker)

    def _abort_begin(self, event: FeishuInbound, bubble_id: str) -> None:
        self._discard_turn(event.chat_id, event.message_id)
        try:
            self.gateway.update_text(bubble_id, FAILURE_TEXT)
        except Exception as exc:
            logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "update", type(exc).__name__)
            try:
                self.gateway.reply_text(event.message_id, FAILURE_TEXT)
            except Exception as reply_exc:
                logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "fallback", type(reply_exc).__name__)

    def _discard_turn(self, chat_id: str, message_id: str) -> None:
        with self._lock:
            turn = self._turns.get(chat_id)
            if turn is None or turn.user_message_id != message_id:
                return
            if turn.request is not None:
                turn.request.cancelled = True
            turn.closed = True
            self._turns.pop(chat_id, None)

    def _remember(self, message_id: str) -> None:
        self._seen.add(message_id, self._open_message_ids())

    def _open_message_ids(self) -> set[str]:
        with self._lock:
            return {turn.user_message_id for turn in self._turns.values() if turn.user_message_id}

    def _reap_workers(self) -> None:
        self._workers = [worker for worker in self._workers if worker.is_alive()]

    def _run_agent(self, request: AnswerRequest) -> None:
        try:
            self.agent_runner(request)
        except Exception as exc:
            logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "agent", type(exc).__name__)
            request.fail(None)

    def _interrupt_locked(self, turn: Turn) -> None:
        if turn.request is not None:
            turn.request.cancelled = True
        if turn.closed:
            self._turns.pop(turn.chat_id, None)
            return
        turn.closed = True
        generated = (turn.generated or "").strip()
        if generated:
            self._persist_assistant(turn, turn.generated)
        self._turns.pop(turn.chat_id, None)
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
        self._show(turn, content)
        self._persist_assistant(turn, content)
        self._turns.pop(turn.chat_id, None)
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
        self._show(turn, generated)

    def _show(self, turn: Turn, text: str) -> None:
        try:
            self.gateway.update_text(turn.bubble_id, text)
        except Exception as exc:
            if turn.replaced:
                logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "update", type(exc).__name__)
                return
            try:
                turn.bubble_id = self.gateway.reply_text(turn.user_message_id, text)
            except Exception as reply_exc:
                logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "fallback", type(reply_exc).__name__)
                return
            turn.replaced = True
        turn.displayed = text
        turn.last_sent_at = self.clock.now()

    def _reply_unsupported(self, message_id: str) -> None:
        try:
            self.gateway.reply_text(message_id, UNSUPPORTED_TEXT)
        except Exception as exc:
            logger.warning(REPLY_FAILED_LOG_TEMPLATE, self.channel.id, "unsupported", type(exc).__name__)

    def _deliver_files(self, turn: Turn, files: list[tuple[str, bytes]]) -> None:
        for filename, content in files:
            try:
                self.gateway.reply_file(turn.user_message_id, filename, content)
            except Exception as exc:
                logger.warning(
                    FILE_FAILED_LOG_TEMPLATE,
                    self.channel.id,
                    getattr(exc, "stage", "send"),
                    type(exc).__name__,
                    getattr(exc, "code", "-"),
                    getattr(exc, "detail", ""),
                )
                self._notify_file_failed(turn)
                continue
            logger.info(FILE_SENT_LOG_TEMPLATE, self.channel.id)

    def _notify_file_failed(self, turn: Turn) -> None:
        try:
            self.gateway.reply_text(turn.user_message_id, FILE_FAILED_TEXT)
        except Exception as exc:
            logger.warning(
                FILE_FAILED_LOG_TEMPLATE,
                self.channel.id,
                "notify",
                type(exc).__name__,
                getattr(exc, "code", "-"),
                getattr(exc, "detail", ""),
            )

    def _persist_user(self, turn: Turn) -> None:
        if getattr(self.channel, "skill", None) is None:
            return
        # 对话服务很重，只在真正落历史时导入。
        from apps.opspilot.models import SkillConversationMessage
        from apps.opspilot.services.skill_channel_chat_service import append_message, get_or_create_conversation

        conversation = get_or_create_conversation(self.channel, turn.external_user_id, turn.session_id or None)
        append_message(conversation, SkillConversationMessage.ROLE_USER, turn.user_message)

    def _persist_assistant(self, turn: Turn, content: str) -> None:
        if getattr(self.channel, "skill", None) is None:
            return
        from apps.opspilot.models import SkillConversationMessage
        from apps.opspilot.services.skill_channel_chat_service import append_message, get_or_create_conversation
        from apps.opspilot.services.skill_memory_service import maybe_schedule_skill_memory_write

        conversation = get_or_create_conversation(self.channel, turn.external_user_id, turn.session_id or None)
        append_message(conversation, SkillConversationMessage.ROLE_ASSISTANT, content)
        maybe_schedule_skill_memory_write(conversation)


class FeishuLongConnectionLeader:
    """一个进程维护全部飞书长连接。未持锁时不建立连接。"""

    def __init__(self, lock: LeaderLock, opener: Callable[[str, str], Any], agent_runner: Callable[[AnswerRequest], None], clock=None):
        self.lock = lock
        self.opener = opener
        self.agent_runner = agent_runner
        self.clock = clock or _MonotonicClock()
        self._live: dict[str, LiveConnection] = {}

    def reconcile(self, channels) -> None:
        if not self.lock.acquire_or_renew():
            self.stop_all()
            return
        desired: dict[str, tuple[Any, str]] = {}
        for channel in channels:
            credentials = feishu_long_connection_credentials(getattr(channel, "channel_config", None))
            if credentials is None or not getattr(channel, "enabled", True):
                continue
            app_id, secret = credentials
            if app_id in desired:
                logger.warning(DUPLICATE_APP_LOG_TEMPLATE, channel.id)
                continue
            desired[app_id] = (channel, secret)
        for app_id in list(self._live):
            current = self._live[app_id]
            wanted = desired.get(app_id)
            if wanted is None or wanted[1] != current.secret or wanted[0].id != current.channel_id:
                self._stop(app_id)
        for app_id, (channel, secret) in desired.items():
            if app_id not in self._live:
                self._connect(channel, app_id, secret)

    def pump(self) -> None:
        if not self.lock.held():
            self.stop_all()
            return
        for live in list(self._live.values()):
            self._drain(live)
            live.session.tick()

    def stop_all(self) -> None:
        for app_id in list(self._live):
            self._stop(app_id)

    def _drain(self, live: LiveConnection) -> None:
        while True:
            try:
                event = live.transport.poll(0)
            except Exception as exc:
                logger.warning(CONNECT_FAILED_LOG_TEMPLATE, live.channel_id, type(exc).__name__)
                self._stop(live.app_id)
                return
            if event is None:
                return
            live.session.handle(event)

    def _connect(self, channel, app_id: str, secret: str) -> None:
        try:
            transport = self.opener(app_id, secret)
        except Exception as exc:
            logger.warning(CONNECT_FAILED_LOG_TEMPLATE, channel.id, type(exc).__name__)
            return
        session = FeishuConnection(channel, transport, self.agent_runner, clock=self.clock)
        self._live[app_id] = LiveConnection(
            app_id=app_id,
            secret=secret,
            channel_id=channel.id,
            transport=transport,
            session=session,
        )

    def _stop(self, app_id: str) -> None:
        live = self._live.pop(app_id, None)
        if live is None:
            return
        live.session.cancel_all()
        close = getattr(live.transport, "close", None)
        if close is not None:
            try:
                close()
            except Exception as exc:
                logger.warning(CONNECT_FAILED_LOG_TEMPLATE, live.channel_id, type(exc).__name__)


def load_long_connection_channels():
    from apps.opspilot.enum import SkillChannelChoices
    from apps.opspilot.models import SkillChannel

    channels = (
        SkillChannel.objects.filter(
            channel_type=SkillChannelChoices.FEISHU,
            enabled=True,
        )
        .select_related("skill")
        .order_by("id")
    )
    return [channel for channel in channels if feishu_long_connection_credentials(channel.channel_config)]


class _SeenIds:
    """有界的已处理 message_id。进行中的一轮不会被淘汰，避免同一条消息重开。"""

    def __init__(self, clock):
        self._clock = clock
        self._items: OrderedDict[str, float] = OrderedDict()

    def contains(self, message_id: str, protected: set[str]) -> bool:
        self._evict(protected)
        return message_id in self._items

    def add(self, message_id: str, protected: set[str]) -> None:
        self._items[message_id] = self._clock.now()
        self._items.move_to_end(message_id)
        self._evict(protected | {message_id})

    def _evict(self, protected: set[str]) -> None:
        cutoff = self._clock.now() - SEEN_TTL_SECONDS
        for message_id, seen_at in list(self._items.items()):
            if message_id in protected or seen_at > cutoff:
                continue
            self._items.pop(message_id, None)
        while len(self._items) > SEEN_LIMIT:
            oldest = next((message_id for message_id in self._items if message_id not in protected), None)
            if oldest is None:
                return
            self._items.pop(oldest, None)


class _MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


def new_leader_lock(redis, token: str | None = None) -> LeaderLock:
    return LeaderLock(redis, token or uuid.uuid4().hex, key=LEADER_LOCK_KEY, ttl_seconds=LEADER_LOCK_TTL_SECONDS)
