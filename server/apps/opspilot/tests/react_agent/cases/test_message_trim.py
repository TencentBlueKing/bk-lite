"""
Tests for #9 消息裁剪增强 (Message Trimming).

Tests trim_messages utility directly:
1. Single message truncation (exceeds max_single_message_tokens)
2. Image aging (retain only recent N image messages)
3. SystemMessage preserved untouched
4. Disabled config returns messages unchanged
5. Multimodal message handling
"""

import sys
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import MessageTrimConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.message_trim import trim_messages  # noqa: E402

# ---------------------------------------------------------------------------
# Tests: Single Message Truncation
# ---------------------------------------------------------------------------


class TestMessageTruncation:
    """Truncation of messages exceeding max_single_message_tokens."""

    def test_long_message_truncated(self):
        """Message exceeding token limit gets truncated with suffix."""
        long_text = "hello world " * 2000  # ~4000 tokens
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content=long_text),
        ]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=100, image_retain_recent=0)

        result = trim_messages(messages, config)

        assert len(result) == 2
        # SystemMessage untouched
        assert result[0].content == "system"
        # HumanMessage truncated
        assert len(result[1].content) < len(long_text)
        assert "截断" in result[1].content

    def test_short_message_unchanged(self):
        """Message within limit is not modified."""
        messages = [HumanMessage(content="short message")]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=4000)

        result = trim_messages(messages, config)

        assert result[0].content == "short message"

    def test_system_message_never_truncated(self):
        """SystemMessage is always preserved regardless of length."""
        long_system = "x " * 5000
        messages = [SystemMessage(content=long_system)]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=10)

        result = trim_messages(messages, config)

        assert result[0].content == long_system

    def test_tool_message_truncated_preserves_tool_call_id(self):
        """ToolMessage truncation preserves tool_call_id."""
        long_content = "data " * 3000
        messages = [ToolMessage(content=long_content, tool_call_id="tc_123")]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=50)

        result = trim_messages(messages, config)

        assert isinstance(result[0], ToolMessage)
        assert result[0].tool_call_id == "tc_123"
        assert "截断" in result[0].content
        assert len(result[0].content) < len(long_content)

    def test_ai_message_truncated_preserves_tool_calls(self):
        """AIMessage truncation preserves tool_calls attribute."""
        long_content = "thinking " * 3000
        tool_calls = [{"name": "foo", "args": {}, "id": "c1"}]
        messages = [AIMessage(content=long_content, tool_calls=tool_calls)]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=50)

        result = trim_messages(messages, config)

        assert isinstance(result[0], AIMessage)
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0]["name"] == "foo"
        assert result[0].tool_calls[0]["id"] == "c1"
        assert "截断" in result[0].content


# ---------------------------------------------------------------------------
# Tests: Image Aging
# ---------------------------------------------------------------------------


class TestImageAging:
    """Removal of images from older messages."""

    def _make_image_msg(self, text="look at this", img_url="data:image/png;base64,abc123"):
        return HumanMessage(
            content=[
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": img_url}},
            ]
        )

    def test_retains_recent_n_images(self):
        """Only the most recent N image messages keep their images."""
        messages = [
            self._make_image_msg("img1"),
            self._make_image_msg("img2"),
            self._make_image_msg("img3"),
            self._make_image_msg("img4"),
        ]
        config = MessageTrimConfig(enabled=True, image_retain_recent=2, max_single_message_tokens=0)

        result = trim_messages(messages, config)

        # First 2 messages should have images stripped
        # Check they no longer have image_url parts
        for i in range(2):
            content = getattr(result[i], "content", "")
            if isinstance(content, list):
                assert not any(p.get("type") == "image_url" for p in content if isinstance(p, dict))
            else:
                assert "移除" in content or "图片" in content

        # Last 2 messages should still have images
        for i in range(2, 4):
            content = getattr(result[i], "content", "")
            assert isinstance(content, list)
            assert any(p.get("type") == "image_url" for p in content if isinstance(p, dict))

    def test_fewer_images_than_retain_no_change(self):
        """If image count <= retain limit, nothing is stripped."""
        messages = [
            self._make_image_msg("img1"),
            HumanMessage(content="text only"),
        ]
        config = MessageTrimConfig(enabled=True, image_retain_recent=3, max_single_message_tokens=0)

        result = trim_messages(messages, config)

        # Image message unchanged
        assert isinstance(result[0].content, list)
        assert any(p.get("type") == "image_url" for p in result[0].content if isinstance(p, dict))

    def test_stripped_message_has_removal_note(self):
        """Stripped image messages include a note about removed images."""
        messages = [
            self._make_image_msg("old image"),
            self._make_image_msg("new image"),
        ]
        config = MessageTrimConfig(enabled=True, image_retain_recent=1, max_single_message_tokens=0)

        result = trim_messages(messages, config)

        # First message stripped
        content = result[0].content
        if isinstance(content, str):
            assert "图片" in content and "移除" in content
        else:
            text_content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            assert "图片" in text_content and "移除" in text_content


# ---------------------------------------------------------------------------
# Tests: Disabled Config
# ---------------------------------------------------------------------------


class TestTrimDisabled:
    """Config disabled returns original messages."""

    def test_disabled_returns_unchanged(self):
        """When enabled=False, messages returned as-is."""
        long_text = "x " * 10000
        messages = [HumanMessage(content=long_text)]
        config = MessageTrimConfig(enabled=False)

        result = trim_messages(messages, config)

        assert result[0].content == long_text

    def test_max_tokens_zero_skips_truncation(self):
        """max_single_message_tokens=0 skips truncation step."""
        long_text = "y " * 10000
        messages = [HumanMessage(content=long_text)]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=0)

        result = trim_messages(messages, config)

        assert result[0].content == long_text


# ---------------------------------------------------------------------------
# Tests: Does not mutate original
# ---------------------------------------------------------------------------


class TestImmutability:
    """Original messages list is not mutated."""

    def test_original_list_unchanged(self):
        """Trimming returns new list, original is intact."""
        long_text = "z " * 5000
        original_msg = HumanMessage(content=long_text)
        messages = [original_msg]
        config = MessageTrimConfig(enabled=True, max_single_message_tokens=50)

        result = trim_messages(messages, config)

        # Original message unchanged
        assert messages[0].content == long_text
        # Result is different
        assert result[0].content != long_text
