"""企业微信 ChatFlow 公共入口的消息解析、分片、校验和投递契约。"""

from types import SimpleNamespace

import pytest

from apps.opspilot.utils import wechat_chat_flow_utils as wechat_module
from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils


pytestmark = pytest.mark.unit


@pytest.fixture
def utils():
    return WechatChatFlowUtils(bot_id=17)


def test_send_message_chunks_ignores_empty_content(monkeypatch, utils):
    client = pytest.fail
    monkeypatch.setattr(wechat_module, "WeChatClient", client)
    assert utils.send_message_chunks("u", "", "a", "corp", "secret") is None


@pytest.mark.parametrize("length,expected_sizes", [(500, [500]), (1001, [500, 500, 1])])
def test_send_message_chunks_respects_wechat_limit(
    monkeypatch, utils, length, expected_sizes
):
    sent = []
    client = SimpleNamespace(
        message=SimpleNamespace(
            send_markdown=lambda agent, user, text: sent.append((agent, user, text))
        )
    )
    monkeypatch.setattr(wechat_module, "WeChatClient", lambda *_: client)
    monkeypatch.setattr(wechat_module.time, "sleep", lambda _seconds: None)

    utils.send_message_chunks("user-1", "x" * length, "agent-1", "corp", "secret")

    assert [len(item[2]) for item in sent] == expected_sizes
    assert all(item[:2] == ("agent-1", "user-1") for item in sent)


def test_parse_message_builds_real_wechat_text_message():
    xml = b"""<xml>
      <ToUserName>corp</ToUserName>
      <FromUserName>user-1</FromUserName>
      <CreateTime>123</CreateTime>
      <MsgType>text</MsgType>
      <Content>inspect database</Content>
      <MsgId>9001</MsgId>
      <AgentID>17</AgentID>
    </xml>"""

    message = WechatChatFlowUtils.parse_message(xml)
    assert message.type == "text"
    assert message.content == "inspect database"
    assert message.source == "user-1"
    assert WechatChatFlowUtils.parse_message(b"") is None


def test_parse_message_uses_unknown_type_fallback(monkeypatch):
    captured = {}

    class Unknown:
        def __init__(self, message):
            captured.update(message)

    monkeypatch.setattr(wechat_module, "UnknownMessage", Unknown)
    result = WechatChatFlowUtils.parse_message(
        b"<xml><MsgType>not-supported</MsgType><Content>x</Content></xml>"
    )
    assert isinstance(result, Unknown)
    assert captured["Content"] == "x"


def test_wechat_node_config_rejects_missing_node(utils):
    config, response = utils.get_wechat_node_config(
        SimpleNamespace(flow_json={"nodes": [{"type": "start"}]})
    )
    assert config is None
    assert response.content == b"success"


def test_wechat_node_config_reports_missing_required_value(utils):
    node_config = {
        "token": "token",
        "aes_key": "key",
        "corp_id": "corp",
        "agent_id": "agent",
    }
    config, response = utils.get_wechat_node_config(
        SimpleNamespace(
            flow_json={
                "nodes": [
                    {
                        "id": "wechat-1",
                        "type": "enterprise_wechat",
                        "data": {"config": node_config},
                    }
                ]
            }
        )
    )
    assert config is None
    assert response.content == b"success"
    assert node_config["node_id"] == "wechat-1"


def test_wechat_node_config_returns_complete_public_configuration(utils):
    node_config = {
        "token": "token",
        "aes_key": "key",
        "corp_id": "corp",
        "agent_id": "agent",
        "secret": "secret",
    }
    config, response = utils.get_wechat_node_config(
        SimpleNamespace(
            flow_json={
                "nodes": [
                    {
                        "id": "wechat-1",
                        "type": "enterprise_wechat",
                        "data": {"config": node_config},
                    }
                ]
            }
        )
    )
    assert response is None
    assert config == {**node_config, "node_id": "wechat-1"}


def test_url_verification_requires_echo_string(utils):
    crypto = SimpleNamespace(check_signature=pytest.fail)
    assert utils.handle_url_verification(crypto, "sig", "1", "n", "").content == b"fail"


def test_url_verification_returns_decrypted_echo(utils):
    calls = []
    crypto = SimpleNamespace(
        check_signature=lambda *args: calls.append(args) or "verified"
    )
    response = utils.handle_url_verification(crypto, "sig", "1", "n", "echo")
    assert response.content == b"verified"
    assert calls == [("sig", "1", "n", "echo")]


def test_url_verification_maps_crypto_failure_to_fail(utils):
    def reject(*_args):
        raise ValueError("invalid signature")

    response = utils.handle_url_verification(
        SimpleNamespace(check_signature=reject), "sig", "1", "n", "echo"
    )
    assert response.content == b"fail"


def test_send_reply_normalizes_newlines_splits_50_lines_and_skips_empty(
    monkeypatch, utils
):
    sent = []
    monkeypatch.setattr(
        utils,
        "send_message_chunks",
        lambda user, text, agent, corp, secret: sent.append(
            (user, text, agent, corp, secret)
        ),
    )
    text = "\r\n".join([f"line-{i}" for i in range(51)]) + "\r\n\r\n"

    utils.send_reply(
        text,
        "user-1",
        {"agent_id": "agent", "corp_id": "corp", "secret": "secret"},
    )

    assert len(sent) == 2
    assert len(sent[0][1].splitlines()) == 50
    assert sent[1][1].startswith("line-50")


def test_send_reply_contains_single_chunk_failure(monkeypatch, utils):
    attempts = []

    def fail_once(_user, text, *_args):
        attempts.append(text)
        raise RuntimeError("gateway offline")

    monkeypatch.setattr(utils, "send_message_chunks", fail_once)
    assert (
        utils.send_reply(
            "visible answer",
            "user-1",
            {"agent_id": "agent", "corp_id": "corp", "secret": "secret"},
        )
        is None
    )
    assert attempts == ["visible answer"]


def _request(query=None, body=b"encrypted"):
    return SimpleNamespace(
        GET=query
        or {"signature": "sig", "timestamp": "123", "nonce": "nonce"},
        body=body,
    )


def test_handle_message_rejects_incomplete_signature(utils):
    response = utils.handle_wechat_message(
        _request({"signature": "sig"}), SimpleNamespace(), SimpleNamespace(), {}
    )
    assert response.content == b"success"


@pytest.mark.parametrize(
    ("message", "processed"),
    [
        (SimpleNamespace(type="image"), False),
        (SimpleNamespace(type="text", content="", source="user", id="m-1"), False),
        (
            SimpleNamespace(
                type="text", content="inspect", source="user", id="m-1"
            ),
            True,
        ),
    ],
)
def test_handle_message_ignores_non_actionable_or_duplicate_input(
    monkeypatch, utils, message, processed
):
    crypto = SimpleNamespace(decrypt_message=lambda *_: b"xml")
    monkeypatch.setattr(utils, "parse_message", lambda _xml: message)
    duplicate = monkeypatch.setattr(
        utils, "is_message_processed", lambda _msg_id: processed
    )
    response = utils.handle_wechat_message(
        _request(), crypto, SimpleNamespace(), {"node_id": "wechat-1"}
    )
    assert response.content == b"success"
    assert duplicate is None


def test_handle_message_dispatches_complete_task_payload(monkeypatch, utils):
    message = SimpleNamespace(
        type="text", content="inspect", source="user-1", id="msg-9"
    )
    monkeypatch.setattr(utils, "parse_message", lambda _xml: message)
    monkeypatch.setattr(utils, "is_message_processed", lambda _msg_id: False)
    delay = monkeypatch.setattr(
        "apps.opspilot.tasks.process_wechat_message.delay",
        lambda **kwargs: dispatched.update(kwargs),
    )
    dispatched = {}
    crypto = SimpleNamespace(decrypt_message=lambda *_: b"xml")
    config = {"node_id": "wechat-1", "agent_id": "agent"}

    response = utils.handle_wechat_message(
        _request(), crypto, SimpleNamespace(), config
    )

    assert response.content == b"success"
    assert dispatched == {
        "bot_id": 17,
        "msg_id": "msg-9",
        "message": "inspect",
        "sender_id": "user-1",
        "config": config,
    }
    assert delay is None


def test_handle_message_contains_decryption_failure(utils):
    def reject(*_args):
        raise ValueError("invalid cipher")

    response = utils.handle_wechat_message(
        _request(),
        SimpleNamespace(decrypt_message=reject),
        SimpleNamespace(),
        {},
    )
    assert response.content == b"success"
