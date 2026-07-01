"""opspilot-biz 切片: services/history_service 纯逻辑真实测试。

HistoryService 是无外部依赖的消息解析/格式化逻辑，直接断言真实输出。
"""

import pydantic.root_model  # noqa

from apps.opspilot.services.history_service import HistoryService, history_service


# ---------------------------------------------------------------------------
# process_user_message_and_images
# ---------------------------------------------------------------------------


class TestProcessUserMessage:
    def test_plain_string_returns_text_no_images(self):
        text, images = HistoryService.process_user_message_and_images("你好")
        assert text == "你好"
        assert images == []

    def test_list_with_image_url_dict(self):
        msg = [
            {"type": "text", "message": "看图"},
            {"type": "image_url", "image_url": {"url": "http://a/1.png"}},
        ]
        text, images = HistoryService.process_user_message_and_images(msg)
        assert text == "看图"
        assert images == ["http://a/1.png"]

    def test_list_with_image_url_plain_string(self):
        msg = [{"type": "image_url", "image_url": "http://a/2.png"}]
        _, images = HistoryService.process_user_message_and_images(msg)
        assert images == ["http://a/2.png"]

    def test_list_with_url_fallback_key(self):
        # 无 image_url 键时回退到 url 键
        msg = [{"type": "image_url", "url": "http://a/3.png"}]
        _, images = HistoryService.process_user_message_and_images(msg)
        assert images == ["http://a/3.png"]

    def test_text_fallback_to_text_key(self):
        msg = [{"type": "text", "text": "fallback text"}]
        text, _ = HistoryService.process_user_message_and_images(msg)
        assert text == "fallback text"

    def test_multiple_images_collected(self):
        msg = [
            {"type": "image_url", "image_url": {"url": "u1"}},
            {"type": "image_url", "image_url": {"url": "u2"}},
        ]
        _, images = HistoryService.process_user_message_and_images(msg)
        assert images == ["u1", "u2"]

    def test_empty_image_url_skipped(self):
        msg = [{"type": "image_url", "image_url": {"url": ""}}]
        _, images = HistoryService.process_user_message_and_images(msg)
        assert images == []


# ---------------------------------------------------------------------------
# process_chat_history
# ---------------------------------------------------------------------------


class TestProcessChatHistory:
    def test_assistant_role_mapped_to_bot(self):
        history = [{"event": "assistant", "message": "我是助手"}]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=[])
        assert out == [{"event": "bot", "message": "我是助手"}]

    def test_user_simple_string_preserved(self):
        history = [{"event": "user", "message": "问题"}]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=[])
        assert out == [{"event": "user", "message": "问题"}]

    def test_window_size_keeps_last_n(self):
        history = [{"event": "user", "message": f"m{i}"} for i in range(5)]
        out = HistoryService.process_chat_history(history, window_size=2, image_data=[])
        assert [h["message"] for h in out] == ["m3", "m4"]

    def test_user_list_message_splits_text_and_images(self):
        history = [
            {
                "event": "user",
                "message": [
                    {"type": "text", "text": "带图的问题"},
                    {"type": "image_url", "image_url": {"url": "img1"}},
                ],
            }
        ]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=[])
        assert out == [{"event": "user", "message": "带图的问题", "image_data": ["img1"]}]

    def test_user_list_image_url_plain_string(self):
        history = [
            {
                "event": "user",
                "message": [{"type": "image_url", "url": "imgX"}],
            }
        ]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=[])
        assert out[0]["image_data"] == ["imgX"]

    def test_assistant_list_message_joined(self):
        # 非 user 事件且 message 为 list → 用换行 join
        history = [
            {
                "event": "assistant",
                "message": [{"type": "text", "text": "line1"}, {"type": "text", "text": "line2"}],
            }
        ]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=[])
        assert out[0]["event"] == "bot"
        assert out[0]["message"] == "line1\nline2"

    def test_trailing_image_data_appended(self):
        history = [{"event": "user", "message": "上一句"}]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=["new_img"])
        assert out[-1] == {"event": "user", "message": "", "image_data": ["new_img"]}

    def test_text_key_fallback_for_user(self):
        history = [{"event": "user", "text": "用 text 键"}]
        out = HistoryService.process_chat_history(history, window_size=10, image_data=[])
        assert out[0]["message"] == "用 text 键"

    def test_module_singleton_exists(self):
        assert isinstance(history_service, HistoryService)
