"""opspilot-biz 切片: metis/llm/chain 同步纯逻辑 helper 真实测试。

覆盖 token_utils（真实 tiktoken）与 message_trim（真实 tiktoken 编码/解码）。
不 mock tokenizer —— tiktoken 是确定性纯函数库，直接断言真实 token 计数/截断行为。
"""

import pydantic.root_model  # noqa

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from apps.opspilot.metis.llm.chain.entity import MessageTrimConfig
from apps.opspilot.metis.llm.chain.message_trim import (
    _message_has_images,
    _strip_images_from_message,
    _truncate_text,
    trim_messages,
)
from apps.opspilot.metis.llm.chain.token_utils import (
    count_message_tokens,
    count_text_tokens,
    get_encoding,
)


# ---------------------------------------------------------------------------
# token_utils
# ---------------------------------------------------------------------------


class TestTokenUtils:
    def test_get_encoding_known_model(self):
        enc = get_encoding("gpt-4o")
        # 真实 tiktoken encoding 往返编码一致
        assert enc.decode(enc.encode("hello world")) == "hello world"

    def test_get_encoding_unknown_model_falls_back(self):
        # 未知模型名应回退到 cl100k_base，不抛异常
        enc = get_encoding("totally-not-a-real-model-xyz")
        fallback = get_encoding.__globals__["tiktoken"].get_encoding("cl100k_base")
        assert enc.encode("abc") == fallback.encode("abc")

    def test_count_text_tokens_matches_encoding(self):
        enc = get_encoding("gpt-4o")
        text = "The quick brown fox jumps over the lazy dog."
        assert count_text_tokens(text) == len(enc.encode(text))

    def test_count_text_tokens_empty(self):
        assert count_text_tokens("") == 0

    def test_count_message_tokens_str_content(self):
        enc = get_encoding("gpt-4o")
        msgs = [HumanMessage(content="hello"), AIMessage(content="world")]
        expected = len(enc.encode("hello")) + len(enc.encode("world"))
        assert count_message_tokens(msgs) == expected

    def test_count_message_tokens_multimodal_list(self):
        enc = get_encoding("gpt-4o")
        content = [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]
        msg = HumanMessage(content=content)
        # 只对 text part 计 token，image_url part 不计
        assert count_message_tokens([msg]) == len(enc.encode("describe this"))

    def test_count_message_tokens_with_tool_calls(self):
        enc = get_encoding("gpt-4o")
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "scale_deployment", "args": {"replicas": 3}, "id": "t1"}],
        )
        expected = len(enc.encode(str({"replicas": 3}))) + len(enc.encode("scale_deployment"))
        assert count_message_tokens([msg]) == expected


# ---------------------------------------------------------------------------
# message_trim - helpers
# ---------------------------------------------------------------------------


class TestMessageTrimHelpers:
    def test_truncate_text_no_truncation_when_short(self):
        enc = get_encoding("gpt-4o")
        text = "short text"
        assert _truncate_text(text, 100, enc, "...{kept}") == text

    def test_truncate_text_truncates_long(self):
        enc = get_encoding("gpt-4o")
        text = "word " * 200  # 远超 5 token
        out = _truncate_text(text, 5, enc, "保留前 {kept} tokens")
        assert out != text
        assert "保留前 5 tokens" in out
        # 截断后正文部分 token 数应等于 max_tokens
        body = out.split("\n保留前 5 tokens")[0]
        assert len(enc.encode(body)) == 5

    def test_message_has_images_true(self):
        msg = HumanMessage(content=[{"type": "image_url", "image_url": {"url": "x"}}])
        assert _message_has_images(msg) is True

    def test_message_has_images_false_for_str(self):
        assert _message_has_images(HumanMessage(content="plain")) is False

    def test_message_has_images_false_text_only_list(self):
        msg = HumanMessage(content=[{"type": "text", "text": "no image"}])
        assert _message_has_images(msg) is False

    def test_strip_images_keeps_text_adds_notice(self):
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "看这张图"},
                {"type": "image_url", "image_url": {"url": "x"}},
                {"type": "image_url", "image_url": {"url": "y"}},
            ]
        )
        out = _strip_images_from_message(msg)
        assert isinstance(out, HumanMessage)
        assert isinstance(out.content, list)
        texts = [p["text"] for p in out.content if p.get("type") == "text"]
        assert "看这张图" in texts
        # 2 张图片被移除并写入提示
        assert any("2 张图片已从历史中移除" in t for t in texts)

    def test_strip_images_single_text_simplifies_to_str(self):
        msg = HumanMessage(content=[{"type": "text", "text": "唯一文本"}])
        out = _strip_images_from_message(msg)
        # 仅一个 text part 且无图片 → 简化为字符串
        assert out.content == "唯一文本"

    def test_strip_images_aimessage_preserves_tool_calls(self):
        tc = [{"name": "t", "args": {}, "id": "1"}]
        msg = AIMessage(
            content=[{"type": "image_url", "image_url": {"url": "x"}}],
            tool_calls=tc,
        )
        out = _strip_images_from_message(msg)
        assert isinstance(out, AIMessage)
        # langchain 会规范化 tool_calls（补 type 字段），断言关键字段被保留
        assert len(out.tool_calls) == 1
        assert out.tool_calls[0]["name"] == "t"
        assert out.tool_calls[0]["id"] == "1"

    def test_strip_images_str_content_returned_as_is(self):
        msg = HumanMessage(content="just a string")
        assert _strip_images_from_message(msg) is msg


# ---------------------------------------------------------------------------
# message_trim - trim_messages 主流程
# ---------------------------------------------------------------------------


class TestTrimMessages:
    def test_disabled_returns_same_object(self):
        cfg = MessageTrimConfig(enabled=False)
        msgs = [HumanMessage(content="x")]
        assert trim_messages(msgs, cfg) is msgs

    def test_truncates_long_single_message(self):
        enc = get_encoding("gpt-4o")
        cfg = MessageTrimConfig(enabled=True, max_single_message_tokens=5, image_retain_recent=0)
        long_text = "word " * 100
        msgs = [HumanMessage(content=long_text)]
        out = trim_messages(msgs, cfg)
        # 原列表不被修改
        assert msgs[0].content == long_text
        assert len(enc.encode(out[0].content.split("\n")[0])) == 5

    def test_system_message_not_truncated(self):
        cfg = MessageTrimConfig(enabled=True, max_single_message_tokens=2, image_retain_recent=0)
        long_text = "system " * 100
        out = trim_messages([SystemMessage(content=long_text)], cfg)
        assert out[0].content == long_text

    def test_tool_message_truncated_preserves_id(self):
        cfg = MessageTrimConfig(enabled=True, max_single_message_tokens=3, image_retain_recent=0)
        msg = ToolMessage(content="long " * 50, tool_call_id="call-42")
        out = trim_messages([msg], cfg)
        assert isinstance(out[0], ToolMessage)
        assert out[0].tool_call_id == "call-42"
        assert out[0].content != msg.content

    def test_image_aging_strips_old_keeps_recent(self):
        img = lambda u: HumanMessage(content=[{"type": "image_url", "image_url": {"url": u}}])  # noqa: E731
        cfg = MessageTrimConfig(enabled=True, max_single_message_tokens=0, image_retain_recent=1)
        msgs = [img("a"), img("b"), img("c")]
        out = trim_messages(msgs, cfg)
        # 最早 2 条图片被剥离，最后 1 条保留
        assert not _message_has_images(out[0])
        assert not _message_has_images(out[1])
        assert _message_has_images(out[2])

    def test_image_aging_noop_when_under_threshold(self):
        img = lambda u: HumanMessage(content=[{"type": "image_url", "image_url": {"url": u}}])  # noqa: E731
        cfg = MessageTrimConfig(enabled=True, max_single_message_tokens=0, image_retain_recent=3)
        msgs = [img("a"), img("b")]
        out = trim_messages(msgs, cfg)
        assert _message_has_images(out[0]) and _message_has_images(out[1])

    def test_multimodal_message_skipped_by_token_truncation(self):
        # 多模态 list content 不走字符串截断分支
        cfg = MessageTrimConfig(enabled=True, max_single_message_tokens=1, image_retain_recent=5)
        content = [{"type": "text", "text": "very long " * 50}]
        msgs = [HumanMessage(content=content)]
        out = trim_messages(msgs, cfg)
        assert out[0].content == content
