"""飞书长连接的外部行为。不连接真实飞书。"""

import logging
import threading
from types import SimpleNamespace

import pytest

from apps.opspilot.services.skill_channel_aibot_long_connection import LeaderLock
from apps.opspilot.services.skill_channel_feishu_long_connection import (
    EMPTY_ANSWER_TEXT,
    FAILURE_TEXT,
    FILE_FAILED_TEXT,
    LEADER_LOCK_KEY,
    PROCESSING_TEXT,
    REPLY_FAILED_LOG_TEMPLATE,
    STREAM_DEADLINE_SECONDS,
    STREAM_FINISH_LEAD_SECONDS,
    TIMEOUT_TEXT,
    UNSUPPORTED_TEXT,
    FeishuConnection,
    FeishuDeliveryError,
    FeishuInbound,
    FeishuLongConnectionLeader,
)
from apps.opspilot.services.skill_channel_feishu_long_connection_sdk import inbound_from_event

SECRET_SENTINEL = "feishu-secret-should-not-be-logged"


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


class ManualClock:
    def __init__(self):
        self.value = 1_000.0

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeGateway:
    def __init__(self, bot_open_id="ou_bot"):
        self.bot = bot_open_id
        self.replies = []
        self.updates = []
        self.files = []
        self.fail_updates = 0
        self.fail_files = False
        self.events = []
        self.closed = False
        self._seq = 0

    def bot_open_id(self):
        return self.bot

    def reply_text(self, message_id, text):
        self._seq += 1
        reply_id = f"om_{self._seq}"
        self.replies.append((message_id, text, reply_id))
        return reply_id

    def update_text(self, message_id, text):
        if self.fail_updates:
            self.fail_updates -= 1
            raise FeishuDeliveryError("update")
        self.updates.append((message_id, text))

    def reply_file(self, message_id, filename, content):
        if self.fail_files:
            raise FeishuDeliveryError("file")
        self.files.append((message_id, filename, content))

    def poll(self, timeout):
        if not self.events:
            return None
        return self.events.pop(0)

    def close(self):
        self.closed = True


class RecordingAgent:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)


def _channel(channel_id=7, *, enabled=True, config=None, skill=None):
    return SimpleNamespace(
        id=channel_id,
        enabled=enabled,
        skill=skill,
        channel_config=config or {"connectionMode": "websocket", "app_id": "cli_a", "app_secret": SECRET_SENTINEL},
    )


def _text(**overrides):
    event = dict(
        message_id="om_user",
        chat_id="oc_chat",
        chat_type="p2p",
        message_type="text",
        text="你好",
        mentions=[],
        sender_open_id="ou_user",
        sender_type="user",
    )
    event.update(overrides)
    return FeishuInbound(**event)


def _session(channel, agent, gateway=None, clock=None, *, sync_agents=True):
    gateway = gateway or FakeGateway()
    clock = clock or ManualClock()
    session = FeishuConnection(channel, gateway, agent, clock=clock, sync_agents=sync_agents)
    return session, gateway, clock


def _leader(redis, opener, agent, token="owner"):
    return FeishuLongConnectionLeader(
        lock=LeaderLock(redis, token, key=LEADER_LOCK_KEY),
        opener=opener,
        agent_runner=agent,
    )


def test_credentials_are_not_written_to_logs(caplog):
    redis = FakeRedis()
    opened = []

    def opener(app_id, secret):
        gateway = FakeGateway()
        opened.append((app_id, secret, gateway))
        return gateway

    leader = _leader(redis, opener, RecordingAgent())
    caplog.set_level(logging.DEBUG, logger="opspilot")
    leader.reconcile([_channel()])

    assert opened[0][0] == "cli_a"
    assert opened[0][1] == SECRET_SENTINEL
    assert SECRET_SENTINEL not in caplog.text


def test_second_process_does_not_connect_while_lock_is_held():
    redis = FakeRedis()
    first_opened = []
    second_opened = []

    def opener_for(bucket):
        def opener(app_id, secret):
            gateway = FakeGateway()
            bucket.append(gateway)
            return gateway

        return opener

    channel = _channel()
    _leader(redis, opener_for(first_opened), RecordingAgent(), token="owner-a").reconcile([channel])
    _leader(redis, opener_for(second_opened), RecordingAgent(), token="owner-b").reconcile([channel])

    assert len(first_opened) == 1
    assert second_opened == []


def test_webhook_and_disabled_channels_are_not_connected():
    redis = FakeRedis()
    opened = []

    def opener(app_id, secret):
        opened.append(app_id)
        return FakeGateway()

    leader = _leader(redis, opener, RecordingAgent())
    leader.reconcile(
        [
            _channel(1, config={"connectionMode": "webhook", "app_id": "cli_hook", "app_secret": "s", "verification_token": "t"}),
            _channel(2, enabled=False),
            _channel(3, config={"connectionMode": "websocket", "app_id": "cli_live", "app_secret": "s"}),
        ]
    )
    assert opened == ["cli_live"]


def test_text_updates_the_same_bubble_then_finishes():
    channel = _channel()
    agent = RecordingAgent()
    clock = ManualClock()
    session, gateway, clock = _session(channel, agent, clock=clock)
    session.handle(_text())

    assert gateway.replies == [("om_user", PROCESSING_TEXT, "om_1")]
    assert agent.requests[0].user_message == "你好"
    agent.requests[0].publish("磁盘")
    clock.advance(2)
    session.tick()
    assert gateway.updates == [("om_1", "磁盘")]
    agent.requests[0].publish("磁盘使用率 70%")
    agent.requests[0].finish()
    assert gateway.updates[-1] == ("om_1", "磁盘使用率 70%")
    assert [item[1] for item in gateway.replies] == [PROCESSING_TEXT]


def test_update_failure_sends_the_current_text_once():
    channel = _channel()
    agent = RecordingAgent()
    clock = ManualClock()
    gateway = FakeGateway()
    gateway.fail_updates = 1
    session, gateway, clock = _session(channel, agent, gateway, clock)
    session.handle(_text())
    agent.requests[0].publish("第一段")
    clock.advance(2)
    session.tick()
    assert ("om_user", "第一段", "om_2") in gateway.replies
    agent.requests[0].publish("第一段加上第二段")
    clock.advance(2)
    session.tick()
    assert gateway.updates == [("om_2", "第一段加上第二段")]
    assert [text for _message_id, text, _reply_id in gateway.replies].count("第一段") == 1


def test_non_text_replies_without_agent():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(_text(message_type="image", text=""))
    assert gateway.replies == [("om_user", UNSUPPORTED_TEXT, "om_1")]
    assert agent.requests == []
    assert gateway.updates == []


def test_group_mention_strips_only_the_bot_placeholder():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(
        _text(
            chat_type="group",
            text="@_user_1 @_user_2 看一下",
            mentions=[
                {"key": "@_user_1", "open_id": "ou_bot"},
                {"key": "@_user_2", "open_id": "ou_other"},
            ],
        )
    )
    assert agent.requests[0].user_message == "@_user_2 看一下"
    assert gateway.replies[0][1] == PROCESSING_TEXT


def test_group_message_without_bot_mention_is_ignored():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(_text(chat_type="group", text="普通聊天", mentions=[]))
    session.handle(_text(message_id="om_all", chat_type="group", text="@_all 大家", mentions=[{"key": "@_all", "open_id": ""}]))
    assert agent.requests == []
    assert gateway.replies == []


def test_same_chat_interrupts_the_previous_turn():
    agent = RecordingAgent()
    started = threading.Event()

    def blocking(request):
        agent.requests.append(request)
        if len(agent.requests) == 1:
            started.set()
            while not request.cancelled:
                pass

    session, gateway, _clock = _session(_channel(), blocking, sync_agents=False)
    session.handle(_text(message_id="om_old", text="第一句"))
    assert started.wait(2)
    agent.requests[0].publish("半截")
    session.handle(_text(message_id="om_new", text="第二句"))
    session.wait()
    assert agent.requests[0].cancelled is True
    assert ("om_1", "半截") not in gateway.updates
    assert gateway.replies[-1][1] == PROCESSING_TEXT
    assert gateway.replies[-1][0] == "om_new"


def test_duplicate_message_does_not_start_another_turn():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    event = _text()
    session.handle(event)
    session.handle(event)
    assert len(agent.requests) == 1
    assert len(gateway.replies) == 1


def test_persist_user_failure_does_not_swallow_the_message(monkeypatch, caplog):
    agent = RecordingAgent()
    channel = _channel()
    session, gateway, _clock = _session(channel, agent)
    event = _text()
    attempts = {"count": 0}

    def flaky(_self, _turn):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError(SECRET_SENTINEL)

    monkeypatch.setattr(FeishuConnection, "_persist_user", flaky)
    caplog.set_level(logging.DEBUG, logger="opspilot")
    session.handle(event)

    assert session._turns == {}
    assert agent.requests == []
    assert gateway.updates == [("om_1", FAILURE_TEXT)]
    assert PROCESSING_TEXT not in [text for _message_id, text in gateway.updates]
    records = [record for record in caplog.records if record.msg == REPLY_FAILED_LOG_TEMPLATE]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].args == (channel.id, "begin", "RuntimeError")
    assert records[0].exc_info is None
    rendered = records[0].getMessage()
    formatted = logging.Formatter().format(records[0])
    assert SECRET_SENTINEL not in rendered
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text
    assert [record for record in caplog.records if record.exc_info] == []

    session.handle(event)
    session.handle(event)
    assert attempts["count"] == 2
    assert len(agent.requests) == 1
    assert agent.requests[0].user_message == "你好"
    assert [item[1] for item in gateway.replies] == [PROCESSING_TEXT, PROCESSING_TEXT]


def test_seen_ids_drop_expired_and_oldest_finished_messages(monkeypatch):
    ttl_seconds = 30
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_feishu_long_connection.SEEN_LIMIT",
        2,
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_feishu_long_connection.SEEN_TTL_SECONDS",
        ttl_seconds,
    )
    agent = RecordingAgent()
    clock = ManualClock()
    session, _gateway, clock = _session(_channel(), agent, clock=clock)

    def finish(message_id, chat_id):
        session.handle(_text(message_id=message_id, chat_id=chat_id, text=message_id))
        agent.requests[-1].finish()

    finish("om_a", "oc_a")
    finish("om_b", "oc_b")
    session.handle(_text(message_id="om_a", chat_id="oc_a", text="again"))
    assert [request.user_message for request in agent.requests] == ["om_a", "om_b"]

    finish("om_c", "oc_c")
    session.handle(_text(message_id="om_a", chat_id="oc_a", text="revived"))
    assert agent.requests[-1].user_message == "revived"

    clock.advance(ttl_seconds - 1)
    before = len(agent.requests)
    session.handle(_text(message_id="om_c", chat_id="oc_c", text="still-fresh"))
    assert len(agent.requests) == before
    clock.advance(1)
    session.handle(_text(message_id="om_c", chat_id="oc_c", text="after-ttl"))
    assert agent.requests[-1].user_message == "after-ttl"


def test_finished_workers_are_removed():
    session, _gateway, _clock = _session(_channel(), RecordingAgent(), sync_agents=False)
    session.handle(_text())
    session.wait()
    assert session._workers == []


def test_pump_stops_when_the_lock_is_lost():
    redis = FakeRedis()
    opened = []

    def opener(app_id, secret):
        gateway = FakeGateway()
        opened.append(gateway)
        return gateway

    agent = RecordingAgent()
    leader = _leader(redis, opener, agent)
    leader.reconcile([_channel()])
    opened[0].events.append(_text())
    redis.values.clear()
    leader.pump()

    assert opened[0].closed is True
    assert leader._live == {}
    assert agent.requests == []
    assert opened[0].events


def test_timeout_replaces_the_bubble_without_a_file():
    agent = RecordingAgent()
    clock = ManualClock()
    gateway = FakeGateway()
    started = threading.Event()

    def blocking(request):
        agent.requests.append(request)
        started.set()
        while not request.cancelled:
            pass

    session, gateway, clock = _session(_channel(), blocking, gateway, clock, sync_agents=False)
    session.handle(_text())
    assert started.wait(2)
    agent.requests[0].publish("已经写出的一半")
    agent.requests[0].add_generated_file("a.txt", b"abc")
    clock.advance(STREAM_DEADLINE_SECONDS - STREAM_FINISH_LEAD_SECONDS)
    session.tick()
    session.wait()
    assert gateway.updates[-1] == ("om_1", "已经写出的一半")
    assert gateway.files == []
    assert TIMEOUT_TEXT not in [text for _mid, text in gateway.updates]


def test_timeout_without_text_uses_the_fixed_notice():
    clock = ManualClock()

    def blocking(request):
        while not request.cancelled:
            pass

    session, gateway, clock = _session(_channel(), blocking, clock=clock, sync_agents=False)
    session.handle(_text())
    clock.advance(STREAM_DEADLINE_SECONDS - STREAM_FINISH_LEAD_SECONDS)
    session.tick()
    session.wait()
    assert gateway.updates[-1] == ("om_1", TIMEOUT_TEXT)


def test_failure_replaces_the_bubble_and_skips_files():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(_text())
    agent.requests[0].add_generated_file("a.txt", b"abc")
    agent.requests[0].fail("流里的失败说明")
    assert gateway.updates[-1] == ("om_1", "流里的失败说明")
    assert gateway.files == []


def test_failure_without_stream_text_uses_the_fixed_notice():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(_text())
    agent.requests[0].fail(None)
    assert gateway.updates[-1] == ("om_1", FAILURE_TEXT)


def test_empty_answer_uses_the_fixed_notice():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(_text())
    agent.requests[0].finish()
    assert gateway.updates[-1] == ("om_1", EMPTY_ANSWER_TEXT)


def test_finished_answer_sends_a_separate_file():
    agent = RecordingAgent()
    session, gateway, _clock = _session(_channel(), agent)
    session.handle(_text())
    agent.requests[0].publish("报告在附件")
    agent.requests[0].add_generated_file("报告.txt", b"hello")
    agent.requests[0].finish()
    assert gateway.updates[-1] == ("om_1", "报告在附件")
    assert gateway.files == [("om_user", "报告.txt", b"hello")]


def test_file_failure_keeps_the_answer_and_sends_a_notice():
    agent = RecordingAgent()
    gateway = FakeGateway()
    gateway.fail_files = True
    session, gateway, _clock = _session(_channel(), agent, gateway)
    session.handle(_text())
    agent.requests[0].publish("正文")
    agent.requests[0].add_generated_file("报告.txt", b"hello")
    agent.requests[0].finish()
    assert gateway.updates[-1] == ("om_1", "正文")
    assert ("om_user", FILE_FAILED_TEXT, "om_2") in gateway.replies


def test_upload_request_includes_the_filename():
    from lark_oapi.core.utils import Files
    from requests_toolbelt import MultipartEncoder

    from apps.opspilot.services.skill_channel_feishu_long_connection_sdk import upload_file_request

    request = upload_file_request("深圳介绍_v1.0.txt", b"hello")
    encoded = MultipartEncoder(Files.parse_form_data(request.body)).to_string()
    assert b'filename="\xe6\xb7\xb1\xe5\x9c\xb3\xe4\xbb\x8b\xe7\xbb\x8d_v1.0.txt"' in encoded
    assert b"hello" in encoded


def test_inbound_event_keeps_mention_keys():
    mention = SimpleNamespace(key="@_user_1", id=SimpleNamespace(open_id="ou_bot"))
    message = SimpleNamespace(
        message_id="om_in",
        chat_id="oc_1",
        chat_type="group",
        message_type="text",
        content='{"text": "@_user_1 你好"}',
        mentions=[mention],
    )
    sender = SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_user"), sender_type="user")
    event = SimpleNamespace(event=SimpleNamespace(message=message, sender=sender))
    inbound = inbound_from_event(event)
    assert inbound.text == "@_user_1 你好"
    assert inbound.mentions == [{"key": "@_user_1", "open_id": "ou_bot"}]


@pytest.mark.django_db
class TestFeishuHistory:
    def _skill(self):
        from apps.opspilot.models import LLMSkill

        return LLMSkill.objects.create(name="feishu-long-skill", team=[1], usage_team=[1])

    def _saved_channel(self, skill):
        from apps.opspilot.enum import SkillChannelChoices
        from apps.opspilot.models import SkillChannel

        return SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.FEISHU,
            enabled=True,
            usage_team=[1],
            channel_config={"connectionMode": "websocket", "app_id": "cli_hist", "app_secret": "sec"},
        )

    def test_speakers_keep_separate_history(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        session, _gateway, _clock = _session(channel, agent)
        session.handle(
            _text(
                chat_id="oc_group",
                chat_type="group",
                sender_open_id="ou_a",
                text="@_user_1 甲的问题",
                mentions=[{"key": "@_user_1", "open_id": "ou_bot"}],
            )
        )
        agent.requests[0].publish("回答甲")
        agent.requests[0].finish()
        session.handle(
            _text(
                message_id="om_b",
                chat_id="oc_group",
                chat_type="group",
                sender_open_id="ou_b",
                text="@_user_1 乙的问题",
                mentions=[{"key": "@_user_1", "open_id": "ou_bot"}],
            )
        )
        agent.requests[1].publish("回答乙")
        agent.requests[1].finish()

        from apps.opspilot.models import SkillConversation

        saved = {
            conv.external_user_id: list(conv.messages.order_by("id").values_list("role", "content"))
            for conv in SkillConversation.objects.filter(channel=channel)
        }
        assert saved["ou_a"] == [("user", "甲的问题"), ("assistant", "回答甲")]
        assert saved["ou_b"] == [("user", "乙的问题"), ("assistant", "回答乙")]
        assert "回答乙" not in str(saved["ou_a"])

    def test_interrupt_keeps_partial_answer_in_history(self):
        channel = self._saved_channel(self._skill())
        agent = RecordingAgent()
        started = threading.Event()

        def blocking(request):
            agent.requests.append(request)
            if len(agent.requests) == 1:
                started.set()
                while not request.cancelled:
                    pass

        session, _gateway, _clock = _session(channel, blocking, sync_agents=False)
        session.handle(_text(text="第一句"))
        assert started.wait(2)
        agent.requests[0].publish("半截回答")
        session.handle(_text(message_id="om_next", text="第二句"))
        session.wait()

        from apps.opspilot.models import SkillConversation

        conversation = SkillConversation.objects.get(channel=channel, external_user_id="ou_user")
        rows = list(conversation.messages.order_by("id").values_list("role", "content"))
        assert rows == [("user", "第一句"), ("assistant", "半截回答"), ("user", "第二句")]
        assert PROCESSING_TEXT not in [content for _role, content in rows]
