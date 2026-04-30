# """
# Tests for Agent context compaction functionality.
#
# Verifies that when message token count exceeds threshold, the compaction
# module correctly compresses historical messages into a summary while
# preserving SystemMessages, recent messages, and tool_call/tool_result pairs.
# """
#
# from unittest.mock import AsyncMock, MagicMock, patch
#
# import pytest
# from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
#
# from apps.opspilot.metis.llm.chain.compaction import (
#     CompactionConfig,
#     _find_safe_split_point,
#     _format_messages_for_summary,
#     compact_messages,
#     count_message_tokens,
#     generate_summary,
# )
#
# # ---------------------------------------------------------------------------
# # TestCountMessageTokens
# # ---------------------------------------------------------------------------
#
#
# class TestCountMessageTokens:
#     """Tests for count_message_tokens function."""
#
#     def test_empty_messages_returns_zero(self):
#         assert count_message_tokens([]) == 0
#
#     def test_plain_text_messages(self):
#         msgs = [HumanMessage(content="Hello world")]
#         tokens = count_message_tokens(msgs)
#         assert tokens > 0
#         # "Hello world" is 2 tokens
#         assert tokens == 2
#
#     def test_includes_tool_calls_tokens(self):
#         msg_without_tools = AIMessage(content="I'll help you.")
#         msg_with_tools = AIMessage(
#             content="I'll help you.",
#             tool_calls=[{"name": "search", "args": {"query": "test"}, "id": "1"}],
#         )
#         tokens_without = count_message_tokens([msg_without_tools])
#         tokens_with = count_message_tokens([msg_with_tools])
#         assert tokens_with > tokens_without
#
#     def test_multimodal_content_list(self):
#         msg = HumanMessage(
#             content=[
#                 {"type": "text", "text": "Describe this image"},
#                 {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
#             ]
#         )
#         tokens = count_message_tokens([msg])
#         # Should count "Describe this image" tokens, ignore image_url
#         assert tokens > 0
#
#     def test_unknown_model_falls_back(self):
#         msgs = [HumanMessage(content="test message")]
#         # Should not raise, falls back to cl100k_base
#         tokens = count_message_tokens(msgs, model="nonexistent-model-xyz")
#         assert tokens > 0
#
#
# # ---------------------------------------------------------------------------
# # TestFindSafeSplitPoint
# # ---------------------------------------------------------------------------
#
#
# class TestFindSafeSplitPoint:
#     """Tests for _find_safe_split_point function."""
#
#     def test_few_messages_returns_zero(self):
#         msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
#         assert _find_safe_split_point(msgs, keep_recent=5) == 0
#
#     def test_normal_split(self):
#         msgs = [
#             HumanMessage(content="msg1"),
#             AIMessage(content="resp1"),
#             HumanMessage(content="msg2"),
#             AIMessage(content="resp2"),
#             HumanMessage(content="msg3"),
#             AIMessage(content="resp3"),
#         ]
#         # keep_recent=2 -> split at idx 4
#         split = _find_safe_split_point(msgs, keep_recent=2)
#         assert split == 4
#
#     def test_tool_message_at_split_moves_backward(self):
#         msgs = [
#             HumanMessage(content="msg1"),
#             AIMessage(content="call tool", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
#             ToolMessage(content="result", tool_call_id="1"),
#             HumanMessage(content="msg2"),
#             AIMessage(content="final"),
#         ]
#         # keep_recent=2 -> naive split at idx 3, which is HumanMessage - OK
#         # keep_recent=3 -> naive split at idx 2, which is ToolMessage -> should move back
#         split = _find_safe_split_point(msgs, keep_recent=3)
#         # Should move backward past ToolMessage, landing at idx 1 (AIMessage with tool_calls)
#         # Then detect tool_calls on AIMessage, move to idx 0
#         assert split <= 1
#         # The kept portion should contain the full tool_call/tool_result pair
#         assert isinstance(msgs[split:][0], (HumanMessage, AIMessage))
#
#     def test_consecutive_tool_messages_skipped(self):
#         msgs = [
#             HumanMessage(content="msg1"),
#             AIMessage(
#                 content="",
#                 tool_calls=[
#                     {"name": "t1", "args": {}, "id": "1"},
#                     {"name": "t2", "args": {}, "id": "2"},
#                 ],
#             ),
#             ToolMessage(content="r1", tool_call_id="1"),
#             ToolMessage(content="r2", tool_call_id="2"),
#             HumanMessage(content="msg2"),
#             AIMessage(content="done"),
#         ]
#         # keep_recent=2 -> naive split at idx 4, HumanMessage - OK
#         split = _find_safe_split_point(msgs, keep_recent=2)
#         assert split == 4
#
#         # keep_recent=3 -> naive split at idx 3, ToolMessage -> move back
#         split = _find_safe_split_point(msgs, keep_recent=3)
#         assert split <= 1
#
#
# # ---------------------------------------------------------------------------
# # TestFormatMessagesForSummary
# # ---------------------------------------------------------------------------
#
#
# class TestFormatMessagesForSummary:
#     """Tests for _format_messages_for_summary function."""
#
#     def test_basic_roles(self):
#         msgs = [
#             HumanMessage(content="What is 2+2?"),
#             AIMessage(content="4"),
#         ]
#         result = _format_messages_for_summary(msgs)
#         assert "[Human] What is 2+2?" in result
#         assert "[AI] 4" in result
#
#     def test_tool_calls_formatted(self):
#         msgs = [
#             AIMessage(content="Let me search", tool_calls=[{"name": "web_search", "args": {"q": "test"}, "id": "1"}]),
#         ]
#         result = _format_messages_for_summary(msgs)
#         assert "called tools: web_search(...)" in result
#         assert "[AI] Let me search" in result
#
#     def test_long_content_truncated(self):
#         long_text = "x" * 5000
#         msgs = [HumanMessage(content=long_text)]
#         result = _format_messages_for_summary(msgs)
#         assert "...(truncated)" in result
#         assert len(result) < 5000
#
#     def test_list_content_joined(self):
#         msgs = [
#             HumanMessage(
#                 content=[
#                     {"type": "text", "text": "Hello"},
#                     {"type": "text", "text": "World"},
#                 ]
#             )
#         ]
#         result = _format_messages_for_summary(msgs)
#         assert "Hello" in result
#         assert "World" in result
#
#
# # ---------------------------------------------------------------------------
# # TestGenerateSummary
# # ---------------------------------------------------------------------------
#
#
# @pytest.mark.asyncio
# class TestGenerateSummary:
#     """Tests for generate_summary function."""
#
#     async def test_normal_summary(self):
#         msgs = [HumanMessage(content="Deploy the app"), AIMessage(content="Done, deployed to prod")]
#         mock_llm = AsyncMock()
#         mock_llm.ainvoke.return_value = MagicMock(content="User requested deployment. App deployed to prod.")
#
#         with patch("apps.opspilot.metis.llm.chain.compaction.TemplateLoader.render_template", return_value="Summarize this..."):
#             result = await generate_summary(msgs, mock_llm, max_tokens=2000)
#
#         assert result == "User requested deployment. App deployed to prod."
#         mock_llm.ainvoke.assert_called_once()
#
#     async def test_llm_failure_falls_back_to_truncation(self):
#         msgs = [HumanMessage(content="Some conversation")]
#         mock_llm = AsyncMock()
#         mock_llm.ainvoke.side_effect = Exception("API error")
#
#         with patch("apps.opspilot.metis.llm.chain.compaction.TemplateLoader.render_template", return_value="Summarize this..."):
#             result = await generate_summary(msgs, mock_llm, max_tokens=2000)
#
#         assert "[对话历史摘要 - 自动截断]" in result
#
#
# # ---------------------------------------------------------------------------
# # TestCompactMessages
# # ---------------------------------------------------------------------------
#
#
# @pytest.mark.asyncio
# class TestCompactMessages:
#     """Tests for compact_messages main entry point."""
#
#     async def test_disabled_returns_original(self):
#         msgs = [HumanMessage(content="x" * 100000)]
#         config = CompactionConfig(enabled=False)
#         result = await compact_messages(msgs, AsyncMock(), config)
#         assert result is msgs
#
#     async def test_below_threshold_returns_original(self):
#         msgs = [HumanMessage(content="short message")]
#         config = CompactionConfig(max_token_threshold=80000)
#         result = await compact_messages(msgs, AsyncMock(), config)
#         assert result is msgs
#
#     async def test_above_threshold_triggers_compaction(self):
#         # Build messages that exceed threshold
#         system_msg = SystemMessage(content="You are helpful.")
#         # ~50 messages with 2000 tokens each = ~100k tokens
#         long_msgs = []
#         for i in range(50):
#             long_msgs.append(HumanMessage(content=f"Question {i}: " + "detail " * 300))
#             long_msgs.append(AIMessage(content=f"Answer {i}: " + "response " * 300))
#
#         all_msgs = [system_msg] + long_msgs
#         config = CompactionConfig(
#             max_token_threshold=5000,  # Low threshold to force compaction
#             keep_recent_messages=4,
#             summary_max_tokens=500,
#         )
#
#         mock_llm = AsyncMock()
#         mock_llm.ainvoke.return_value = MagicMock(content="Summary of prior conversation.")
#
#         with patch("apps.opspilot.metis.llm.chain.compaction.TemplateLoader.render_template", return_value="Summarize..."):
#             result = await compact_messages(all_msgs, mock_llm, config, model_name="gpt-4o")
#
#         # Structure: [original system] + [summary system] + [recent N msgs]
#         assert isinstance(result[0], SystemMessage)
#         assert result[0].content == "You are helpful."
#         assert isinstance(result[1], SystemMessage)
#         assert "摘要" in result[1].content or "Summary" in result[1].content
#         # Recent messages preserved
#         assert len(result) <= 4 + 2  # keep_recent + 2 system messages
#
#     async def test_preserves_tool_call_pairs(self):
#         system_msg = SystemMessage(content="System")
#         msgs = [
#             HumanMessage(content="long " * 1000),
#             AIMessage(content="ok " * 1000),
#             HumanMessage(content="do something " * 1000),
#             AIMessage(content="calling", tool_calls=[{"name": "run", "args": {"cmd": "ls"}, "id": "tc1"}]),
#             ToolMessage(content="file1\nfile2", tool_call_id="tc1"),
#             HumanMessage(content="thanks"),
#             AIMessage(content="you're welcome"),
#         ]
#
#         config = CompactionConfig(
#             max_token_threshold=100,  # Very low to force compaction
#             keep_recent_messages=4,
#         )
#
#         mock_llm = AsyncMock()
#         mock_llm.ainvoke.return_value = MagicMock(content="Prior conversation summary")
#
#         with patch("apps.opspilot.metis.llm.chain.compaction.TemplateLoader.render_template", return_value="Summarize..."):
#             result = await compact_messages([system_msg] + msgs, mock_llm, config)
#
#         # Check no orphaned ToolMessage in result (every ToolMessage must follow
#         # an AIMessage with tool_calls)
#         for i, msg in enumerate(result):
#             if isinstance(msg, ToolMessage):
#                 # Previous message must be AIMessage with tool_calls
#                 prev = result[i - 1]
#                 assert isinstance(prev, AIMessage) and getattr(
#                     prev, "tool_calls", None
#                 ), f"ToolMessage at index {i} has no preceding AIMessage with tool_calls"
#
#     async def test_all_system_messages_no_compaction(self):
#         msgs = [SystemMessage(content="sys1"), SystemMessage(content="sys2")]
#         config = CompactionConfig(max_token_threshold=1)
#         result = await compact_messages(msgs, AsyncMock(), config)
#         assert result is msgs
#
#     async def test_split_idx_zero_no_compaction(self):
#         """When messages are fewer than keep_recent, no compaction occurs."""
#         msgs = [SystemMessage(content="sys"), HumanMessage(content="hi"), AIMessage(content="hello")]
#         config = CompactionConfig(max_token_threshold=1, keep_recent_messages=10)
#         mock_llm = AsyncMock()
#         result = await compact_messages(msgs, mock_llm, config)
#         assert result is msgs
#
#
# # ---------------------------------------------------------------------------
# # TestCompactionIntegration
# # ---------------------------------------------------------------------------
#
#
# @pytest.mark.asyncio
# class TestCompactionIntegration:
#     """End-to-end compaction flow test."""
#
#     async def test_long_conversation_compression_ratio(self):
#         """Simulate a long conversation and verify compression reduces token count."""
#         system_msg = SystemMessage(content="You are an operations assistant.")
#         msgs = [system_msg]
#         for i in range(30):
#             msgs.append(HumanMessage(content=f"Step {i}: Please check server-{i}.example.com status and fix any issues. " * 20))
#             msgs.append(AIMessage(content=f"Checked server-{i}. CPU usage 85%, disk 90%. Applied fix #{i}. " * 20))
#
#         original_tokens = count_message_tokens(msgs)
#         assert original_tokens > 10000, f"Test setup: need >10k tokens, got {original_tokens}"
#
#         config = CompactionConfig(
#             max_token_threshold=5000,
#             keep_recent_messages=6,
#             summary_max_tokens=1000,
#         )
#
#         mock_llm = AsyncMock()
#         mock_llm.ainvoke.return_value = MagicMock(content="Checked servers 0-26. All had high CPU/disk. Applied fixes.")
#
#         with patch("apps.opspilot.metis.llm.chain.compaction.TemplateLoader.render_template", return_value="Summarize..."):
#             result = await compact_messages(msgs, mock_llm, config)
#
#         result_tokens = count_message_tokens(result)
#         assert result_tokens < original_tokens, f"Compaction should reduce tokens: {original_tokens} -> {result_tokens}"
#         # At least 50% compression on this large input
#         assert result_tokens < original_tokens * 0.5, f"Expected >50% compression, got {(1 - result_tokens/original_tokens)*100:.1f}%"
