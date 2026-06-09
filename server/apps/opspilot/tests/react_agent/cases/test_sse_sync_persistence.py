"""
Tests for SSE synchronous persistence (Scenario 19, Issue #2959).

Verifies that:
- _record_execution_result is synchronous (no daemon threads)
- _record_conversation_history is synchronous (no daemon threads)
- Persistence failures are logged but don't crash the flow
- WorkFlowTaskResult is saved with correct status
- WorkFlowConversationHistory is created correctly
- No threading.Thread with daemon=True in persistence code
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

import inspect  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestNoDaemonThreadsInPersistence:
    """Tests to verify no daemon threads are used in persistence code."""

    def test_record_execution_result_no_daemon_thread(self):
        """TC-19-01: _record_execution_result should not use daemon threads."""
        from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

        source = inspect.getsource(ChatFlowEngine._record_execution_result)

        # Check that daemon=True is not in the source
        assert "daemon=True" not in source, "_record_execution_result should not use daemon threads"
        assert "daemon = True" not in source, "_record_execution_result should not use daemon threads"

        # Check that threading.Thread is not used
        assert "threading.Thread" not in source, "_record_execution_result should not spawn threads"

    def test_record_conversation_history_no_daemon_thread(self):
        """TC-19-02: _record_conversation_history should not use daemon threads."""
        from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

        source = inspect.getsource(ChatFlowEngine._record_conversation_history)

        assert "daemon=True" not in source, "_record_conversation_history should not use daemon threads"
        assert "daemon = True" not in source, "_record_conversation_history should not use daemon threads"
        assert "threading.Thread" not in source, "_record_conversation_history should not spawn threads"


class TestRecordExecutionResult:
    """Tests for _record_execution_result method."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock ChatFlowEngine instance."""
        with patch("apps.opspilot.utils.chat_flow_utils.engine.engine.WorkFlowTaskResult") as mock_task_result:
            with patch("apps.opspilot.utils.chat_flow_utils.engine.engine.WorkFlowTaskNodeResult"):
                from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

                # Create mock instance
                mock_instance = MagicMock()
                mock_instance.flow_json = {"nodes": [], "edges": []}
                mock_instance.id = 1
                mock_instance.bot_id = "bot_123"

                engine = ChatFlowEngine(mock_instance)
                engine.execution_contexts = {}
                engine.variable_manager = MagicMock()
                engine.variable_manager.get_variable.return_value = None

                # Setup mock task_result
                mock_task = MagicMock()
                mock_task.status = "running"
                mock_task_result.objects.filter.return_value.order_by.return_value.first.return_value = None
                mock_task_result.objects.create.return_value = mock_task
                engine._mock_task_result_class = mock_task_result

                yield engine

    def test_record_execution_result_saves_synchronously(self, mock_engine):
        """TC-19-03: _record_execution_result should save synchronously."""
        input_data = {"last_message": "test"}
        result = {"content": "response"}

        # Track if save was called
        save_called = []

        def mock_save(*args, **kwargs):
            save_called.append(True)

        mock_engine.task_result = MagicMock()
        mock_engine.task_result.status = "running"
        mock_engine.task_result.save = mock_save

        mock_engine._record_execution_result(input_data, result, success=True)

        # Save should be called synchronously (in the same thread)
        assert len(save_called) == 1, "save() should be called synchronously"

    def test_record_execution_result_handles_exception(self, mock_engine):
        """TC-19-04: _record_execution_result should handle exceptions gracefully."""
        input_data = {"last_message": "test"}
        result = {"content": "response"}

        mock_engine.task_result = MagicMock()
        mock_engine.task_result.status = "running"
        mock_engine.task_result.save.side_effect = Exception("DB error")

        # Should not raise
        mock_engine._record_execution_result(input_data, result, success=True)


class TestRecordConversationHistory:
    """Tests for _record_conversation_history method."""

    @pytest.fixture
    def mock_engine_for_history(self):
        """Create a mock ChatFlowEngine for conversation history tests."""
        with patch("apps.opspilot.utils.chat_flow_utils.engine.engine.WorkFlowConversationHistory") as mock_history:
            with patch("apps.opspilot.utils.chat_flow_utils.engine.engine.WorkFlowTaskResult"):
                with patch("apps.opspilot.utils.chat_flow_utils.engine.engine.WorkFlowTaskNodeResult"):
                    from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

                    mock_instance = MagicMock()
                    mock_instance.flow_json = {"nodes": [], "edges": []}
                    mock_instance.id = 1
                    mock_instance.bot_id = "bot_123"

                    engine = ChatFlowEngine(mock_instance)
                    engine._mock_history_class = mock_history

                    yield engine

    def test_record_conversation_history_creates_synchronously(self, mock_engine_for_history):
        """TC-19-05: _record_conversation_history should create record synchronously."""
        create_called = []

        def mock_create(**kwargs):
            create_called.append(kwargs)
            return MagicMock()

        mock_engine_for_history._mock_history_class.objects.create = mock_create

        mock_engine_for_history._record_conversation_history(
            user_id="user_123",
            message="Hello",
            role="user",
            entry_type="openai",
            node_id="node_1",
            session_id="session_1",
        )

        assert len(create_called) == 1, "create() should be called synchronously"
        assert create_called[0]["user_id"] == "user_123"
        assert create_called[0]["conversation_content"] == "Hello"
        assert create_called[0]["conversation_role"] == "user"

    def test_record_conversation_history_skips_empty_user_id(self, mock_engine_for_history):
        """TC-19-06: _record_conversation_history should skip if user_id is empty."""
        create_called = []
        mock_engine_for_history._mock_history_class.objects.create = lambda **kwargs: create_called.append(kwargs)

        mock_engine_for_history._record_conversation_history(
            user_id="",
            message="Hello",
            role="user",
            entry_type="openai",
        )

        assert len(create_called) == 0, "Should skip when user_id is empty"

    def test_record_conversation_history_skips_empty_message(self, mock_engine_for_history):
        """TC-19-07: _record_conversation_history should skip if message is empty."""
        create_called = []
        mock_engine_for_history._mock_history_class.objects.create = lambda **kwargs: create_called.append(kwargs)

        mock_engine_for_history._record_conversation_history(
            user_id="user_123",
            message="",
            role="user",
            entry_type="openai",
        )

        assert len(create_called) == 0, "Should skip when message is empty"

    def test_record_conversation_history_skips_celery_entry_type(self, mock_engine_for_history):
        """TC-19-08: _record_conversation_history should skip celery entry type."""
        create_called = []
        mock_engine_for_history._mock_history_class.objects.create = lambda **kwargs: create_called.append(kwargs)

        mock_engine_for_history._record_conversation_history(
            user_id="user_123",
            message="Hello",
            role="user",
            entry_type="celery",
        )

        assert len(create_called) == 0, "Should skip when entry_type is celery"

    def test_record_conversation_history_handles_exception(self, mock_engine_for_history):
        """TC-19-09: _record_conversation_history should handle exceptions gracefully."""
        mock_engine_for_history._mock_history_class.objects.create.side_effect = Exception("DB error")

        # Should not raise
        mock_engine_for_history._record_conversation_history(
            user_id="user_123",
            message="Hello",
            role="user",
            entry_type="openai",
        )

    def test_record_conversation_history_converts_dict_message(self, mock_engine_for_history):
        """TC-19-10: _record_conversation_history should convert dict message to JSON string."""
        create_called = []

        def mock_create(**kwargs):
            create_called.append(kwargs)
            return MagicMock()

        mock_engine_for_history._mock_history_class.objects.create = mock_create

        mock_engine_for_history._record_conversation_history(
            user_id="user_123",
            message={"key": "value"},
            role="bot",
            entry_type="openai",
        )

        assert len(create_called) == 1
        assert create_called[0]["conversation_content"] == '{"key": "value"}'


class TestSynchronousExecution:
    """Tests to verify synchronous execution behavior."""

    def test_no_thread_spawning_in_persistence_path(self):
        """TC-19-11: Persistence methods should not spawn any threads."""
        from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

        # Get all method source code
        methods_to_check = [
            "_record_execution_result",
            "_record_conversation_history",
            "_record_node_execution_result",
        ]

        for method_name in methods_to_check:
            method = getattr(ChatFlowEngine, method_name, None)
            if method:
                source = inspect.getsource(method)
                assert "Thread(" not in source, f"{method_name} should not create threads"
                assert "thread.start()" not in source, f"{method_name} should not start threads"


class TestAsyncWrappers:
    """Tests for async wrapper methods."""

    def test_async_wrapper_uses_sync_to_async(self):
        """TC-19-12: Async wrappers should use sync_to_async for thread safety."""
        from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

        # Check _record_execution_result_async
        source = inspect.getsource(ChatFlowEngine._record_execution_result_async)
        assert "sync_to_async" in source, "_record_execution_result_async should use sync_to_async"

        # Check _record_node_execution_result_async
        source = inspect.getsource(ChatFlowEngine._record_node_execution_result_async)
        assert "sync_to_async" in source, "_record_node_execution_result_async should use sync_to_async"


# ---------------------------------------------------------------------------
# Tests for sse_chat.py persistence (Issue #2959 - 3.1)
# ---------------------------------------------------------------------------


class TestSseChatPersistence:
    """Tests for sse_chat.py persistence."""

    def test_log_and_update_tokens_sync_no_daemon_thread(self):
        """TC-19-13: _log_and_update_tokens_sync should not use daemon threads."""
        from apps.opspilot.utils.sse_chat import _log_and_update_tokens_sync

        source = inspect.getsource(_log_and_update_tokens_sync)
        assert "daemon=True" not in source, "_log_and_update_tokens_sync should not use daemon threads"
        assert "daemon = True" not in source, "_log_and_update_tokens_sync should not use daemon threads"
        assert "threading.Thread" not in source, "_log_and_update_tokens_sync should not spawn threads"

    def test_log_and_update_tokens_sync_saves_history_log(self):
        """TC-19-14: Should save history_log when provided."""
        from apps.opspilot.utils.sse_chat import _log_and_update_tokens_sync

        mock_history_log = MagicMock()
        final_stats = {"content": "test response"}

        with patch("apps.opspilot.utils.sse_chat.insert_skill_log"):
            _log_and_update_tokens_sync(
                final_stats=final_stats,
                skill_name="test_skill",
                skill_id="skill_123",
                current_ip=None,
                kwargs={},
                user_message="hello",
                show_think=True,
                history_log=mock_history_log,
            )

        assert mock_history_log.conversation == "test response"
        mock_history_log.save.assert_called_once()

    def test_log_and_update_tokens_sync_strips_think_tags(self):
        """TC-19-15: Should strip <think> tags when show_think=False."""
        from apps.opspilot.utils.sse_chat import _log_and_update_tokens_sync

        mock_history_log = MagicMock()
        final_stats = {"content": "<think>reasoning</think>actual response"}

        with patch("apps.opspilot.utils.sse_chat.insert_skill_log"):
            _log_and_update_tokens_sync(
                final_stats=final_stats,
                skill_name="test_skill",
                skill_id="skill_123",
                current_ip=None,
                kwargs={},
                user_message="hello",
                show_think=False,
                history_log=mock_history_log,
            )

        assert mock_history_log.conversation == "actual response"

    def test_log_and_update_tokens_sync_handles_exception(self):
        """TC-19-16: Should handle exceptions gracefully."""
        from apps.opspilot.utils.sse_chat import _log_and_update_tokens_sync

        mock_history_log = MagicMock()
        mock_history_log.save.side_effect = Exception("DB error")
        final_stats = {"content": "test"}

        # Should not raise
        _log_and_update_tokens_sync(
            final_stats=final_stats,
            skill_name="test_skill",
            skill_id="skill_123",
            current_ip=None,
            kwargs={},
            user_message="hello",
            show_think=True,
            history_log=mock_history_log,
        )

    def test_log_and_update_tokens_sync_calls_insert_skill_log(self):
        """TC-19-17: Should call insert_skill_log when current_ip provided."""
        from apps.opspilot.utils.sse_chat import _log_and_update_tokens_sync

        final_stats = {"content": "test response"}

        with patch("apps.opspilot.utils.sse_chat.insert_skill_log") as mock_insert:
            _log_and_update_tokens_sync(
                final_stats=final_stats,
                skill_name="test_skill",
                skill_id="skill_123",
                current_ip="192.168.1.1",
                kwargs={"key": "value"},
                user_message="hello",
                show_think=True,
                history_log=None,
            )

        mock_insert.assert_called_once()


class TestSubsequentNodesAsync:
    """Tests for _execute_subsequent_nodes_async execution mechanics (post-F013)."""

    def test_subsequent_nodes_async_is_awaited_not_detached_daemon_thread(self):
        """TC-19-18: subsequent-node execution is awaited in-flow, not a detached daemon thread.

        F013 changed _execute_subsequent_nodes_async from spawning a fire-and-forget
        ``threading.Thread(daemon=True)`` to awaiting the work via
        ``sync_to_async(thread_sensitive=False)``. This guarantees the subsequent
        nodes run race-free (serialized against the SSE stream) and are not silently
        dropped when the request/process ends.
        """
        from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

        method = ChatFlowEngine._execute_subsequent_nodes_async
        source = inspect.getsource(method)

        # Must be a coroutine that the caller awaits — not a detached daemon thread.
        assert inspect.iscoroutinefunction(method), "_execute_subsequent_nodes_async must be a coroutine (awaited in-flow)"
        assert "daemon=True" not in source, "Must not spawn a detached daemon thread for subsequent nodes"
        assert "daemon = True" not in source, "Must not spawn a detached daemon thread for subsequent nodes"
        assert "threading.Thread" not in source, "Must not spawn a thread for subsequent nodes"

        # The synchronous body (incl. ORM writes) runs via sync_to_async and is awaited.
        assert "sync_to_async" in source, "Subsequent-node work must run via sync_to_async"
        assert "thread_sensitive=False" in source, "sync_to_async must use thread_sensitive=False"
        assert "await sync_to_async" in source, "Subsequent-node work must be awaited to completion"
        # Persistence is still recorded as part of that awaited work.
        assert "_record_execution_result" in source, "Should record execution result as part of the awaited work"

    def test_subsequent_nodes_async_runs_work_to_completion_when_awaited(self):
        """TC-19-19: awaiting the coroutine runs subsequent-node work to completion (not dropped).

        Verifies the intent of F013: the inner synchronous logic actually executes
        and finishes within the await, rather than being handed off to a daemon
        thread that may never be joined.
        """
        import asyncio

        from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

        engine = ChatFlowEngine.__new__(ChatFlowEngine)

        executed = {"ran": False}

        def fake_next_nodes(*args, **kwargs):
            executed["ran"] = True
            return []  # no further nodes; method returns after marking work done

        engine._get_next_nodes = fake_next_nodes

        # Awaiting must drive the inner sync work to completion in-flow.
        asyncio.run(engine._execute_subsequent_nodes_async({"id": "agent-1", "data": {}}, "final output"))

        assert executed["ran"] is True, "Awaited coroutine must run the subsequent-node work to completion"
