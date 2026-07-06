import json
from unittest.mock import Mock, patch

import pytest

from apps.opspilot.tasks import process_enterprise_wechat_aibot_message, process_enterprise_wechat_aibot_reply
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils


def test_process_enterprise_wechat_aibot_message_enqueues_reply_without_marking_completed_before_send():
    flow_input = {
        "last_message": "查询 CPU",
        "user_id": "user-1",
        "response_url": "https://example.com/response",
        "session_id": "chat-1",
    }

    with patch("apps.opspilot.tasks._get_bot_chat_flow", return_value=Mock()) as get_flow, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "execute_chatflow_with_message",
        return_value="CPU 正常",
    ) as execute, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_completed",
    ) as mark_completed, patch.object(
        process_enterprise_wechat_aibot_reply,
        "delay",
    ) as reply_delay, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_failed",
    ) as mark_failed, patch.object(
        process_enterprise_wechat_aibot_message,
        "retry",
    ) as retry:
        process_enterprise_wechat_aibot_message.run(
            10,
            "m1",
            flow_input,
            "user-1",
            {"node_id": "node-1", "response_url": "https://example.com/response"},
        )

    get_flow.assert_called_once_with(10)
    execute.assert_called_once()
    mark_completed.assert_not_called()
    reply_delay.assert_called_once_with(10, "m1", "https://example.com/response", "CPU 正常")
    mark_failed.assert_not_called()
    retry.assert_not_called()


def test_process_enterprise_wechat_aibot_message_retries_when_workflow_execution_fails():
    with patch("apps.opspilot.tasks._get_bot_chat_flow", return_value=Mock()), patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "execute_chatflow_with_message",
        side_effect=RuntimeError("tool failed"),
    ), patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_completed",
    ) as mark_completed, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "send_reply",
    ) as send_reply, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_failed",
    ) as mark_failed, patch.object(
        process_enterprise_wechat_aibot_message,
        "retry",
        side_effect=RuntimeError("retry scheduled"),
    ) as retry:
        try:
            process_enterprise_wechat_aibot_message.run(10, "m1", {"last_message": "hi"}, "user-1", {"node_id": "node-1"})
        except RuntimeError as exc:
            assert str(exc) == "retry scheduled"

    mark_failed.assert_called_once_with("m1")
    mark_completed.assert_not_called()
    send_reply.assert_not_called()
    retry.assert_called_once()


def test_process_enterprise_wechat_aibot_reply_marks_completed_after_send_success():
    with patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "send_markdown_reply",
    ) as send_markdown, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_completed",
    ) as mark_completed, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_failed",
    ) as mark_failed:
        process_enterprise_wechat_aibot_reply.run(10, "m1", "https://example.com/response", "CPU 正常")

    send_markdown.assert_called_once_with("https://example.com/response", "CPU 正常")
    mark_completed.assert_called_once_with("m1")
    mark_failed.assert_not_called()


def test_process_enterprise_wechat_aibot_reply_retries_without_clearing_dedup_on_send_failure():
    with patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "send_markdown_reply",
        side_effect=RuntimeError("network down"),
    ) as send_markdown, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_completed",
    ) as mark_completed, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_failed",
    ) as mark_failed:
        with pytest.raises(RuntimeError, match="retry scheduled"), patch.object(
            process_enterprise_wechat_aibot_reply,
            "retry",
            side_effect=RuntimeError("retry scheduled"),
        ) as retry:
            process_enterprise_wechat_aibot_reply.run(10, "m1", "https://example.com/response", "当前仅支持文本消息")

    send_markdown.assert_called_once_with("https://example.com/response", "当前仅支持文本消息")
    mark_completed.assert_not_called()
    mark_failed.assert_not_called()
    retry.assert_called_once()


def test_send_markdown_reply_posts_markdown_payload():
    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {"errcode": 0}

        EnterpriseWechatAibotChatFlowUtils.send_markdown_reply("https://example.com/response", "hello")

    post.assert_called_once_with(
        "https://example.com/response",
        json={"msgtype": "markdown", "markdown": {"content": "hello"}},
        timeout=10,
    )


def test_send_markdown_reply_raises_when_wechat_returns_error_code():
    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {"errcode": 40001, "errmsg": "invalid credential"}

        with pytest.raises(RuntimeError, match="40001"):
            EnterpriseWechatAibotChatFlowUtils.send_markdown_reply("https://example.com/response", "hello")


def test_send_reply_uses_response_url_from_config():
    utils = EnterpriseWechatAibotChatFlowUtils(10)

    with patch.object(EnterpriseWechatAibotChatFlowUtils, "send_markdown_reply") as send_markdown:
        utils.send_reply("hello", "user-1", {"response_url": "https://example.com/response"})

    send_markdown.assert_called_once_with("https://example.com/response", "hello")


def test_execute_chatflow_uses_clean_text_payload_and_preserves_channel_context():
    utils = EnterpriseWechatAibotChatFlowUtils(10)
    message = {
        "last_message": "查询 CPU",
        "user_id": "user-1",
        "bot_id": 10,
        "node_id": "node-1",
        "channel": "enterprise_wechat_aibot",
        "is_third_party": True,
        "entry_type": "enterprise_wechat_aibot",
        "session_id": "chat-1",
        "response_url": "https://example.com/response",
    }

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.create_chat_flow_engine") as create_engine:
        create_engine.return_value.execute.return_value = {"last_message": "CPU 正常"}

        reply = utils.execute_chatflow_with_message(
            bot_chat_flow=Mock(),
            node_id="node-1",
            message=message,
            sender_id="user-1",
        )

    assert reply == "CPU 正常"
    create_engine.return_value.execute.assert_called_once_with(message)


def test_execute_chatflow_returns_failure_message_from_result():
    utils = EnterpriseWechatAibotChatFlowUtils(10)

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.create_chat_flow_engine") as create_engine:
        create_engine.return_value.execute.return_value = {"success": False, "error": "处理失败"}

        reply = utils.execute_chatflow_with_message(Mock(), "node-1", {"last_message": "hi"}, "user-1")

    assert reply == "处理失败"


def test_execute_chatflow_returns_string_for_scalar_result():
    utils = EnterpriseWechatAibotChatFlowUtils(10)

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.create_chat_flow_engine") as create_engine:
        create_engine.return_value.execute.return_value = "ok"

        reply = utils.execute_chatflow_with_message(Mock(), "node-1", {"last_message": "hi"}, "user-1")

    assert reply == "ok"


def test_execute_chatflow_returns_default_for_empty_result():
    utils = EnterpriseWechatAibotChatFlowUtils(10)

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.create_chat_flow_engine") as create_engine:
        create_engine.return_value.execute.return_value = None

        reply = utils.execute_chatflow_with_message(Mock(), "node-1", {"last_message": "hi"}, "user-1")

    assert reply == "处理完成"


def test_execute_chatflow_serializes_structured_data_result():
    utils = EnterpriseWechatAibotChatFlowUtils(10)

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.create_chat_flow_engine") as create_engine:
        create_engine.return_value.execute.return_value = {"data": {"status": "ok", "count": 2}}

        reply = utils.execute_chatflow_with_message(Mock(), "node-1", {"last_message": "hi"}, "user-1")

    assert reply == json.dumps({"status": "ok", "count": 2}, ensure_ascii=False, indent=2)
