"""企微机器人长连接：假连接上的回复帧、会话历史与选主。"""

import asyncio
import json
import logging
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.opspilot.services.skill_channel_aibot_long_connection import (
    TRANSPORT_FAILED_LOG_TEMPLATE,
    DEFAULT_LONG_CONNECTION_URL,
    EMPTY_ANSWER_TEXT,
    FAILURE_TEXT,
    PROCESSING_TEXT,
    SUBSCRIBE_LOG_TEMPLATE,
    STREAM_DEADLINE_SECONDS,
    STREAM_FINISH_LEAD_SECONDS,
    TIMEOUT_TEXT,
    UNSUPPORTED_TEXT,
    LeaderLock,
    WecomAibotConnection,
    WecomAibotLongConnectionLeader,
    long_connection_credentials,
    long_connection_url,
    visible_answer_delta,
)

SECRET_SENTINEL = "LONG_CONNECTION_SECRET_SENTINEL"


class ManualClock:
    def __init__(self):
        self.current = 1_000.0

    def now(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, name, value, nx=False, ex=None):
        if nx and name in self.values:
            return None
        self.values[name] = value
        return True

    def get(self, name):
        return self.values.get(name)

    def eval(self, script, numkeys, key, token, ttl):
        if self.values.get(key) == token:
            return 1
        return 0


class FakeTransport:
    def __init__(self):
        self.sent = []
        self.closed = False
        self.fail_recv = None

    def send_json(self, payload):
        self.sent.append(payload)

    def recv_json(self, timeout):
        if self.fail_recv is not None:
            raise self.fail_recv
        raise TimeoutError()

    def close(self):
        self.closed = True


class RecordingAgent:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)


def _channel(channel_id=7, *, enabled=True, config=None):
    return SimpleNamespace(id=channel_id, enabled=enabled, channel_config=config or _long_config(), skill=None)


def _long_config(bot_id="bot-1", secret=SECRET_SENTINEL):
    return {"connectionMode": "websocket", "websocket": {"botId": bot_id, "secret": secret}}


def _text_frame(req_id, content, *, chattype="single", userid="user-1", chatid=""):
    body = {
        "msgid": req_id,
        "chattype": chattype,
        "from": {"userid": userid},
        "msgtype": "text",
        "text": {"content": content},
    }
    if chatid:
        body["chatid"] = chatid
    return {"cmd": "aibot_msg_callback", "headers": {"req_id": req_id}, "body": body}


def _event_frame(eventtype, req_id="evt-1"):
    return {
        "cmd": "aibot_event_callback",
        "headers": {"req_id": req_id},
        "body": {"msgid": req_id, "msgtype": "event", "event": {"eventtype": eventtype}},
    }


def _streams(transport):
    return [item for item in transport.sent if item.get("cmd") == "aibot_respond_msg"]


def _stream_body(frame):
    return frame["body"]["stream"]


def _leader(redis, opener, agent, clock=None, token="owner-a"):
    return WecomAibotLongConnectionLeader(
        lock=LeaderLock(redis, token),
        opener=opener,
        agent_runner=agent,
        clock=clock or ManualClock(),
        url=DEFAULT_LONG_CONNECTION_URL,
    )


def test_long_connection_credentials_require_bot_id_and_secret():
    assert long_connection_credentials(_long_config()) == ("bot-1", SECRET_SENTINEL)
    assert long_connection_credentials({"connectionMode": "websocket", "websocket": {"botId": "bot-1", "secret": "  "}}) is None
    assert long_connection_credentials({"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}}) is None


def test_private_address_comes_from_environment(monkeypatch):
    assert long_connection_url() == DEFAULT_LONG_CONNECTION_URL
    monkeypatch.setenv("WECOM_AIBOT_LONG_CONNECTION_URL", "wss://wecom.internal.example/ws")
    assert long_connection_url() == "wss://wecom.internal.example/ws"


def test_visible_answer_keeps_final_text_only():
    events = [
        {"type": "THINKING_TEXT_MESSAGE_CONTENT", "delta": "思考过程"},
        {"type": "TOOL_CALL_RESULT", "content": "工具结果"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": '{"phase":"planning"}'},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "磁盘使用率 70%"},
    ]
    assert "".join(delta for event in events if (delta := visible_answer_delta(event))) == "磁盘使用率 70%"


def test_subscribe_sends_bot_id_and_secret_without_logging_secret(caplog):
    redis = FakeRedis()
    opened = []

    def opener(url):
        transport = FakeTransport()
        opened.append((url, transport))
        return transport

    leader = _leader(redis, opener, RecordingAgent())
    caplog.set_level(logging.INFO, logger="opspilot")
    leader.reconcile([_channel()])

    assert opened[0][0] == DEFAULT_LONG_CONNECTION_URL
    subscribe = opened[0][1].sent[0]
    assert subscribe["cmd"] == "aibot_subscribe"
    assert subscribe["body"] == {"bot_id": "bot-1", "secret": SECRET_SENTINEL}
    records = [record for record in caplog.records if record.msg == SUBSCRIBE_LOG_TEMPLATE]
    assert len(records) == 1
    assert records[0].args == (7,)
    assert SECRET_SENTINEL not in caplog.text
    assert SECRET_SENTINEL not in records[0].getMessage()


def test_second_process_does_not_connect_while_lock_is_held():
    redis = FakeRedis()
    first_opened = []
    second_opened = []

    def opener_for(bucket):
        def opener(url):
            transport = FakeTransport()
            bucket.append(transport)
            return transport

        return opener

    first = _leader(redis, opener_for(first_opened), RecordingAgent(), token="owner-a")
    second = _leader(redis, opener_for(second_opened), RecordingAgent(), token="owner-b")
    channel = _channel()
    first.reconcile([channel])
    second.reconcile([channel])

    assert len(first_opened) == 1
    assert second_opened == []


def test_webhook_disabled_and_incomplete_channels_are_not_connected():
    redis = FakeRedis()
    opened = []

    def opener(url):
        transport = FakeTransport()
        opened.append(transport)
        return transport

    leader = _leader(redis, opener, RecordingAgent())
    leader.reconcile(
        [
            _channel(1, config={"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}}),
            _channel(2, enabled=False),
            _channel(3, config={"connectionMode": "websocket", "websocket": {"botId": "bot-only"}}),
        ]
    )
    assert opened == []


def test_credential_change_reconnects_and_disable_closes():
    redis = FakeRedis()
    opened = []

    def opener(url):
        transport = FakeTransport()
        opened.append(transport)
        return transport

    leader = _leader(redis, opener, RecordingAgent())
    leader.reconcile([_channel(config=_long_config(secret="secret-a"))])
    leader.reconcile([_channel(config=_long_config(secret="secret-b"))])

    assert opened[0].closed is True
    assert opened[1].sent[0]["body"]["secret"] == "secret-b"
    leader.reconcile([_channel(enabled=False, config=_long_config(secret="secret-b"))])
    assert opened[1].closed is True
    assert len(opened) == 2


def test_kicked_while_holding_lock_reconnects_otherwise_stops():
    redis = FakeRedis()
    opened = []

    def opener(url):
        transport = FakeTransport()
        opened.append(transport)
        return transport

    leader = _leader(redis, opener, RecordingAgent())
    channel = _channel()
    leader.reconcile([channel])
    leader.handle_transport_frame("bot-1", _event_frame("disconnected_event"))

    assert opened[0].closed is True
    assert len(opened) == 2
    assert opened[1].sent[0]["body"]["bot_id"] == "bot-1"

    redis.values.clear()
    leader.handle_transport_frame("bot-1", _event_frame("disconnected_event", req_id="evt-2"))

    assert opened[1].closed is True
    assert len(opened) == 2


def test_transport_drop_retries_without_logging_secret(caplog):
    redis = FakeRedis()
    opened = []

    def opener(url):
        transport = FakeTransport()
        opened.append(transport)
        return transport

    leader = _leader(redis, opener, RecordingAgent())
    leader.reconcile([_channel()])
    opened[0].fail_recv = ConnectionError("reset")
    caplog.set_level(logging.WARNING, logger="opspilot")
    leader.pump()

    assert opened[0].closed is True
    assert len(opened) == 2
    records = [record for record in caplog.records if record.msg == TRANSPORT_FAILED_LOG_TEMPLATE]
    assert len(records) == 1
    assert records[0].args == (7, "ConnectionError")
    rendered = records[0].getMessage()
    formatted = logging.Formatter().format(records[0])
    assert SECRET_SENTINEL not in rendered
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text


@pytest.mark.django_db
def test_answer_failure_owns_one_traceback_and_omits_exception_text(caplog):
    from apps.opspilot.services import skill_channel_aibot_long_connection_agent as agent_mod

    failed = []
    request = SimpleNamespace(channel=SimpleNamespace(id=7), fail=lambda message=None: failed.append(message))

    def boom(_request):
        raise ValueError(SECRET_SENTINEL)

    caplog.set_level(logging.ERROR, logger="opspilot")
    with patch.object(agent_mod, "_run", boom):
        agent_mod._run_guarded(request)

    assert failed == [None]
    records = [record for record in caplog.records if record.msg == agent_mod.ANSWER_FAILED_LOG_TEMPLATE]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].args == (7, "ValueError")
    exc_type, exc_value, exc_tb = records[0].exc_info
    assert exc_type is RuntimeError
    assert str(exc_value) == "ValueError"
    frames = []
    cursor = exc_tb
    while cursor is not None:
        frames.append(cursor.tb_frame.f_code.co_name)
        cursor = cursor.tb_next
    assert "boom" in frames
    rendered = records[0].getMessage()
    formatted = logging.Formatter().format(records[0])
    assert SECRET_SENTINEL not in rendered
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text


def test_cancelling_a_turn_stops_the_blocked_agent_stream(monkeypatch):
    from apps.opspilot.services.skill_channel_aibot_long_connection_agent import _run

    started = threading.Event()
    closed = threading.Event()
    finished = []
    failed = []

    async def fake_stream(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            closed.set()
        if False:
            yield ""

    monkeypatch.setattr("apps.opspilot.utils.agui_chat._generate_agui_stream", fake_stream)
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service.get_or_create_conversation",
        lambda *args, **kwargs: SimpleNamespace(session_id="session-1"),
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service.build_skill_chat_params",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service._history_from_conversation",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_memory_service.inject_skill_memory_prompt",
        lambda *args, **kwargs: None,
    )
    request = SimpleNamespace(
        channel=SimpleNamespace(id=7, skill=SimpleNamespace(id=1, name="skill", skill_type=1, conversation_window_size=10)),
        external_user_id="user-1",
        session_id="room-1",
        user_message="第一句",
        cancelled=False,
        publish=lambda text: None,
        finish=lambda: finished.append("finish"),
        fail=lambda message=None: failed.append(message),
    )
    thread = threading.Thread(target=_run, args=(request,))
    thread.start()
    assert started.wait(2)
    request.cancelled = True
    thread.join(2)

    assert not thread.is_alive()
    assert closed.is_set()
    assert finished == []
    assert failed == []


def test_duplicate_bot_opens_one_connection():
    redis = FakeRedis()
    opened = []

    def opener(url):
        transport = FakeTransport()
        opened.append(transport)
        return transport

    leader = _leader(redis, opener, RecordingAgent())
    leader.reconcile(
        [
            _channel(4, config=_long_config(bot_id="same-bot", secret="s1")),
            _channel(9, config=_long_config(bot_id="same-bot", secret="s2")),
        ]
    )
    assert len(opened) == 1
    assert opened[0].sent[0]["body"]["secret"] == "s1"


@pytest.mark.django_db
class TestLongConnectionConversation:
    def _skill(self):
        from apps.opspilot.models import LLMSkill

        return LLMSkill.objects.create(name="long-conn-skill", team=[1], usage_team=[1])

    def _saved_channel(self, skill):
        from apps.opspilot.enum import SkillChannelChoices
        from apps.opspilot.models import SkillChannel

        return SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
            enabled=True,
            usage_team=[1],
            channel_config=_long_config(),
        )

    def _session(self, channel, agent, clock=None):
        clock = clock or ManualClock()
        transport = FakeTransport()
        session = WecomAibotConnection(channel, transport, agent, clock=clock)
        return session, transport, clock

    def _history(self, channel):
        from apps.opspilot.models import SkillConversation

        conversation = SkillConversation.objects.get(channel=channel)
        return list(conversation.messages.order_by("id").values_list("role", "content"))

    def test_text_stream_overwrites_then_finishes_with_answer_only(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        clock = ManualClock()
        session, transport, clock = self._session(channel, agent, clock)
        session.handle_frame(_text_frame("req-1", "@机器人 查询 CPU"))

        assert agent.requests[0].user_message == "查询 CPU"
        first = _stream_body(_streams(transport)[0])
        assert first["finish"] is False
        assert first["content"] == PROCESSING_TEXT

        agent.requests[0].publish("磁盘")
        clock.advance(2)
        session.tick()
        second = _stream_body(_streams(transport)[1])
        assert second["finish"] is False
        assert second["content"] == "磁盘"
        assert second["id"] == first["id"]
        assert _streams(transport)[1]["headers"]["req_id"] == "req-1"

        agent.requests[0].publish("磁盘使用率 70%")
        clock.advance(2)
        session.tick()
        agent.requests[0].finish()

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == "磁盘使用率 70%"
        assert finished["id"] == first["id"]
        assert self._history(channel) == [("user", "查询 CPU"), ("assistant", "磁盘使用率 70%")]

    def test_non_text_replies_without_agent_or_history(self):
        from apps.opspilot.models import SkillConversation

        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        for msgtype in ("image", "file", "voice", "video", "mixed"):
            session.handle_frame(
                {
                    "cmd": "aibot_msg_callback",
                    "headers": {"req_id": f"media-{msgtype}"},
                    "body": {"msgid": msgtype, "msgtype": msgtype, "from": {"userid": "user-1"}},
                }
            )
            frame = _stream_body(_streams(transport)[-1])
            assert frame["finish"] is True
            assert frame["content"] == UNSUPPORTED_TEXT
            assert _streams(transport)[-1]["headers"]["req_id"] == f"media-{msgtype}"

        assert agent.requests == []
        assert SkillConversation.objects.filter(channel=channel).count() == 0
        assert all(item["content"] != PROCESSING_TEXT for item in (_stream_body(frame) for frame in _streams(transport)))

    def test_events_are_ignored(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        for eventtype in ("enter_chat", "template_card_event", "feedback_event"):
            assert session.handle_frame(_event_frame(eventtype)) is None
        assert transport.sent == []
        assert agent.requests == []

    def test_interrupt_ends_displayed_text_and_keeps_partial_answer(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        session.handle_frame(_text_frame("req-1", "第一句", chattype="group", chatid="room-1", userid="user-1"))
        agent.requests[0].publish("半截回答")
        session.handle_frame(_text_frame("req-2", "第二句", chattype="group", chatid="room-1", userid="user-1"))

        frames = _streams(transport)
        assert _stream_body(frames[0])["content"] == PROCESSING_TEXT
        assert _stream_body(frames[0])["finish"] is False
        assert _stream_body(frames[1])["content"] == PROCESSING_TEXT
        assert _stream_body(frames[1])["finish"] is True
        assert frames[1]["headers"]["req_id"] == "req-1"
        assert _stream_body(frames[2])["content"] == PROCESSING_TEXT
        assert frames[2]["headers"]["req_id"] == "req-2"
        assert agent.requests[0].cancelled is True
        assert agent.requests[1].user_message == "第二句"
        assert self._history(channel) == [
            ("user", "第一句"),
            ("assistant", "半截回答"),
            ("user", "第二句"),
        ]
        assert not any("第一句" in content and "第二句" in content for _role, content in self._history(channel))

    def test_interrupt_without_body_does_not_store_processing_text(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        session.handle_frame(_text_frame("req-1", "第一句"))
        session.handle_frame(_text_frame("req-2", "第二句"))

        assert _stream_body(_streams(transport)[1])["finish"] is True
        assert _stream_body(_streams(transport)[1])["content"] == PROCESSING_TEXT
        assert self._history(channel) == [("user", "第一句"), ("user", "第二句")]

    def test_timeout_without_body_ends_with_timeout_copy(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        clock = ManualClock()
        session, transport, clock = self._session(channel, agent, clock)
        session.handle_frame(_text_frame("req-1", "慢问题"))
        clock.advance(10 * 60)
        session.tick()
        agent.requests[0].publish("迟到的正文")
        session.tick()

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == TIMEOUT_TEXT
        assert len(_streams(transport)) == 2
        assert self._history(channel) == [("user", "慢问题"), ("assistant", TIMEOUT_TEXT)]

    def test_timeout_finishes_before_the_ten_minute_mark(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        clock = ManualClock()
        session, transport, clock = self._session(channel, agent, clock)
        session.handle_frame(_text_frame("req-1", "慢问题"))
        clock.advance(STREAM_DEADLINE_SECONDS - STREAM_FINISH_LEAD_SECONDS - 1)
        session.tick()

        assert _stream_body(_streams(transport)[-1])["finish"] is False
        clock.advance(1)
        session.tick()
        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == TIMEOUT_TEXT
        assert clock.now() - 1_000 < STREAM_DEADLINE_SECONDS

    def test_timeout_with_body_keeps_that_body(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        clock = ManualClock()
        session, transport, clock = self._session(channel, agent, clock)
        session.handle_frame(_text_frame("req-1", "慢问题"))
        agent.requests[0].publish("已经写出的正文")
        clock.advance(10 * 60)
        session.tick()

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == "已经写出的正文"
        assert self._history(channel) == [("user", "慢问题"), ("assistant", "已经写出的正文")]

    def test_stream_error_uses_the_channel_failure_copy(self, monkeypatch):
        channel = self._saved_channel(self._skill())
        failure = "无法连接大模型服务，请检查 API 地址、网络连通性或白名单"

        async def fake_stream(*args, **kwargs):
            yield f"data: {json.dumps({'type': 'ERROR', 'error': failure}, ensure_ascii=False)}\n\n"

        monkeypatch.setattr("apps.opspilot.utils.agui_chat._generate_agui_stream", fake_stream)

        def runner(request):
            from apps.opspilot.services.skill_channel_aibot_long_connection_agent import _run

            _run(request)

        session, transport, _clock = self._session(channel, runner)
        session.handle_frame(_text_frame("req-1", "会失败"))

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == failure
        assert self._history(channel) == [("user", "会失败"), ("assistant", failure)]
        assert FAILURE_TEXT not in finished["content"]

    def test_failure_replaces_the_message_and_history(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        session.handle_frame(_text_frame("req-1", "会失败"))
        agent.requests[0].publish("半截")
        agent.requests[0].fail()

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == FAILURE_TEXT
        assert self._history(channel) == [("user", "会失败"), ("assistant", FAILURE_TEXT)]

    def test_short_callback_does_not_dispatch_a_long_connection_channel(self):
        from django.test import RequestFactory

        from apps.opspilot import views as opspilot_views
        from apps.opspilot.enum import SkillChannelChoices

        channel = self._saved_channel(self._skill())
        request = RequestFactory().post("/", data=b'{"encrypt":"abc"}', content_type="application/json")
        with patch("apps.opspilot.tasks.process_skill_channel_aibot_message.delay") as delay:
            response = opspilot_views.execute_skill_channel_im(
                request,
                channel.id,
                SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
            )
        assert response.status_code == 200
        assert response.content == b"success"
        delay.assert_not_called()

    def test_stream_content_uses_existing_markdown_limit(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        session.handle_frame(_text_frame("req-1", "长回答"))
        agent.requests[0].publish("测" * 12000)
        agent.requests[0].finish()

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"].endswith("内容过长，已截断")
        assert len(finished["content"].encode("utf-8")) <= 20480

    def test_empty_answer_finishes_instead_of_leaving_processing_text(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, transport, _clock = self._session(channel, agent)
        session.handle_frame(_text_frame("req-1", "空回答"))
        agent.requests[0].finish()

        finished = _stream_body(_streams(transport)[-1])
        assert finished["finish"] is True
        assert finished["content"] == EMPTY_ANSWER_TEXT
        assert self._history(channel) == [("user", "空回答"), ("assistant", EMPTY_ANSWER_TEXT)]
