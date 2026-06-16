"""
Tests for external channel message two-phase deduplication (Scenario 17, Issue #2961).

Verifies that:
- First message sets "processing" status and returns False (can process)
- Duplicate message during processing returns True (skip)
- Completed message returns True (skip)
- Failed message clears status, allowing retry
- Processing timeout allows retry (TTL expiry)
- Concurrent messages are handled correctly
"""

import inspect
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

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from apps.opspilot.utils.base_chat_flow_utils import (  # noqa: E402
    MESSAGE_COMPLETED_EXPIRE_SECONDS,
    MESSAGE_PROCESSING_EXPIRE_SECONDS,
    BaseChatFlowUtils,
)

# ---------------------------------------------------------------------------
# Test Implementation of BaseChatFlowUtils
# ---------------------------------------------------------------------------


class TestChatFlowUtils(BaseChatFlowUtils):
    """Concrete implementation for testing."""

    channel_name = "Test"
    channel_code = "test"
    cache_key_prefix = "test_msg"

    def send_reply(self, reply_text: str, sender_id: str, config: dict):
        """Mock send_reply for testing."""
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cache():
    """Mock Django cache with in-memory dict and atomic add() support."""
    cache_data = {}

    def mock_get(key):
        return cache_data.get(key)

    def mock_set(key, value, timeout=None):
        cache_data[key] = value

    def mock_add(key, value, timeout=None):
        """Atomic add - only sets if key doesn't exist, returns True if set."""
        if key not in cache_data:
            cache_data[key] = value
            return True
        return False

    def mock_delete(key):
        cache_data.pop(key, None)

    with patch("apps.opspilot.utils.base_chat_flow_utils.cache") as cache_mock:
        cache_mock.get = mock_get
        cache_mock.set = mock_set
        cache_mock.add = mock_add
        cache_mock.delete = mock_delete
        cache_mock._data = cache_data  # Expose for inspection
        yield cache_mock


@pytest.fixture
def utils(mock_cache):
    """Create TestChatFlowUtils instance."""
    return TestChatFlowUtils(bot_id="bot_123")


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestTwoPhaseDedup:
    """Tests for two-phase deduplication mechanism."""

    def test_first_message_sets_processing_and_returns_false(self, utils, mock_cache):
        """TC-17-01: First message should set 'processing' status and return False."""
        msg_id = "msg_001"

        result = utils.is_message_processed(msg_id)

        assert result is False, "First message should return False (can process)"
        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"
        assert mock_cache._data.get(cache_key) == "processing"

    def test_duplicate_during_processing_returns_true(self, utils, mock_cache):
        """TC-17-02: Duplicate message during processing should return True."""
        msg_id = "msg_002"

        # First call sets processing
        first_result = utils.is_message_processed(msg_id)
        assert first_result is False

        # Second call should skip (already processing)
        second_result = utils.is_message_processed(msg_id)
        assert second_result is True, "Duplicate during processing should return True"

    def test_completed_message_returns_true(self, utils, mock_cache):
        """TC-17-03: Completed message should return True."""
        msg_id = "msg_003"

        # First call sets processing
        utils.is_message_processed(msg_id)

        # Mark as completed
        utils.mark_message_completed(msg_id)

        # Check status
        result = utils.is_message_processed(msg_id)
        assert result is True, "Completed message should return True"

        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"
        assert mock_cache._data.get(cache_key) == "completed"

    def test_failed_message_clears_status_allows_retry(self, utils, mock_cache):
        """TC-17-04: Failed message should clear status, allowing retry."""
        msg_id = "msg_004"

        # First call sets processing
        first_result = utils.is_message_processed(msg_id)
        assert first_result is False

        # Mark as failed (clears status)
        utils.mark_message_failed(msg_id)

        # Retry should be allowed
        retry_result = utils.is_message_processed(msg_id)
        assert retry_result is False, "After failure, retry should be allowed"

    def test_processing_ttl_is_short(self, utils, mock_cache):
        """TC-17-05: Processing TTL should be 300 seconds (5 minutes)."""
        assert MESSAGE_PROCESSING_EXPIRE_SECONDS == 300

    def test_completed_ttl_is_long(self, utils, mock_cache):
        """TC-17-06: Completed TTL should be 86400 seconds (24 hours)."""
        assert MESSAGE_COMPLETED_EXPIRE_SECONDS == 86400


class TestCacheKeyFormat:
    """Tests for cache key format."""

    def test_cache_key_includes_prefix_bot_and_msg(self, utils, mock_cache):
        """Cache key should include prefix, bot_id, and msg_id."""
        msg_id = "msg_key_test"
        utils.is_message_processed(msg_id)

        expected_key = f"test_msg:bot_123:{msg_id}"
        assert expected_key in mock_cache._data

    def test_different_bots_have_different_keys(self, mock_cache):
        """Different bots should have isolated cache keys."""
        utils1 = TestChatFlowUtils(bot_id="bot_A")
        utils2 = TestChatFlowUtils(bot_id="bot_B")
        msg_id = "same_msg"

        utils1.is_message_processed(msg_id)
        utils2.is_message_processed(msg_id)

        key_a = f"test_msg:bot_A:{msg_id}"
        key_b = f"test_msg:bot_B:{msg_id}"
        assert key_a in mock_cache._data
        assert key_b in mock_cache._data


class TestAsyncProcessAndReply:
    """Tests for async_process_and_reply method."""

    def test_success_marks_completed(self, utils, mock_cache):
        """TC-17-07: Successful processing should mark message as completed."""
        msg_id = "msg_success"
        bot_chat_flow = MagicMock()
        config = {"node_id": "node_1"}

        with patch.object(utils, "execute_chatflow_with_message", return_value="reply"):
            with patch.object(utils, "send_reply"):
                utils.async_process_and_reply(bot_chat_flow, config, "hello", "user_1", msg_id)

        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"
        assert mock_cache._data.get(cache_key) == "completed"

    def test_failure_clears_status_and_raises(self, utils, mock_cache):
        """TC-17-08: Failed processing should clear status and raise exception."""
        msg_id = "msg_failure"
        bot_chat_flow = MagicMock()
        config = {"node_id": "node_1"}

        # Set initial processing status
        utils.is_message_processed(msg_id)

        with patch.object(utils, "execute_chatflow_with_message", side_effect=Exception("ChatFlow error")):
            with pytest.raises(Exception, match="ChatFlow error"):
                utils.async_process_and_reply(bot_chat_flow, config, "hello", "user_1", msg_id)

        # Status should be cleared
        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"
        assert cache_key not in mock_cache._data, "Failed message should clear cache"


class TestStateTransitions:
    """Tests for state transition correctness."""

    def test_none_to_processing_to_completed(self, utils, mock_cache):
        """TC-17-09: State transition: None → processing → completed."""
        msg_id = "msg_transition_1"
        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"

        # Initial: None
        assert mock_cache._data.get(cache_key) is None

        # After is_message_processed: processing
        utils.is_message_processed(msg_id)
        assert mock_cache._data.get(cache_key) == "processing"

        # After mark_message_completed: completed
        utils.mark_message_completed(msg_id)
        assert mock_cache._data.get(cache_key) == "completed"

    def test_none_to_processing_to_failed_to_none(self, utils, mock_cache):
        """TC-17-10: State transition: None → processing → failed → None."""
        msg_id = "msg_transition_2"
        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"

        # Initial: None
        assert mock_cache._data.get(cache_key) is None

        # After is_message_processed: processing
        utils.is_message_processed(msg_id)
        assert mock_cache._data.get(cache_key) == "processing"

        # After mark_message_failed: None (cleared)
        utils.mark_message_failed(msg_id)
        assert mock_cache._data.get(cache_key) is None

    def test_completed_cannot_be_overwritten_by_processing(self, utils, mock_cache):
        """TC-17-11: Completed status should not be overwritten by new processing attempt."""
        msg_id = "msg_completed_protect"
        cache_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"

        # Set to completed
        utils.is_message_processed(msg_id)
        utils.mark_message_completed(msg_id)
        assert mock_cache._data.get(cache_key) == "completed"

        # Try to process again - should return True (skip)
        result = utils.is_message_processed(msg_id)
        assert result is True
        # Status should still be completed
        assert mock_cache._data.get(cache_key) == "completed"


# ---------------------------------------------------------------------------
# TTL Tests (Issue #2961 - 1.3)
# ---------------------------------------------------------------------------


class TestTTLConfiguration:
    """Tests for TTL configuration and parameter passing."""

    def test_processing_ttl_passed_correctly(self):
        """TC-17-12: Processing status should use MESSAGE_PROCESSING_EXPIRE_SECONDS TTL via cache.add()."""
        with patch("apps.opspilot.utils.base_chat_flow_utils.cache") as mock_cache:
            mock_cache.get.return_value = None  # Simulate no existing status
            mock_cache.add.return_value = True  # Simulate successful acquisition

            utils = TestChatFlowUtils(bot_id="bot_ttl_test")
            msg_id = "msg_ttl_test"

            result = utils.is_message_processed(msg_id)

            # Verify cache.add was called with correct TTL (atomic operation)
            expected_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"
            mock_cache.add.assert_called_once_with(
                expected_key,
                "processing",
                MESSAGE_PROCESSING_EXPIRE_SECONDS,
            )
            assert result is False  # Successfully acquired processing rights

    def test_completed_ttl_passed_correctly(self):
        """TC-17-13: Completed status should use MESSAGE_COMPLETED_EXPIRE_SECONDS TTL."""
        with patch("apps.opspilot.utils.base_chat_flow_utils.cache") as mock_cache:
            mock_cache.get.return_value = "processing"  # Simulate processing status

            utils = TestChatFlowUtils(bot_id="bot_ttl_test")
            msg_id = "msg_ttl_completed"

            utils.mark_message_completed(msg_id)

            # Verify cache.set was called with correct TTL
            expected_key = f"{utils.cache_key_prefix}:{utils.bot_id}:{msg_id}"
            mock_cache.set.assert_called_once_with(
                expected_key,
                "completed",
                MESSAGE_COMPLETED_EXPIRE_SECONDS,
            )


# ---------------------------------------------------------------------------
# Concurrent Safety Tests (Issue #2961 - Race Condition Fix)
# ---------------------------------------------------------------------------


class TestConcurrentSafety:
    """Tests for concurrent message processing safety using cache.add() atomic operation."""

    def test_cache_add_used_for_atomic_acquisition(self):
        """TC-17-14: is_message_processed should use cache.add() for atomic lock acquisition."""
        with patch("apps.opspilot.utils.base_chat_flow_utils.cache") as mock_cache:
            mock_cache.get.return_value = None
            mock_cache.add.return_value = True  # First caller wins

            utils = TestChatFlowUtils(bot_id="bot_atomic")
            msg_id = "msg_atomic_test"

            result = utils.is_message_processed(msg_id)

            # Should use add() not set() for atomic operation
            mock_cache.add.assert_called_once()
            assert result is False  # Got processing rights

    def test_cache_add_fails_returns_true(self):
        """TC-17-15: When cache.add() fails (another worker got lock), should return True."""
        with patch("apps.opspilot.utils.base_chat_flow_utils.cache") as mock_cache:
            mock_cache.get.return_value = None  # No status yet
            mock_cache.add.return_value = False  # Another worker already acquired

            utils = TestChatFlowUtils(bot_id="bot_concurrent")
            msg_id = "msg_concurrent_test"

            result = utils.is_message_processed(msg_id)

            # Should return True (skip) because another worker got the lock
            assert result is True

    def test_concurrent_workers_only_one_processes(self):
        """TC-17-16: Simulate concurrent workers - only one should get processing rights."""
        # This test simulates the race condition scenario:
        # Worker A and B both call is_message_processed() nearly simultaneously
        # Both see cache.get() return None
        # But only one should succeed with cache.add()

        call_count = {"add": 0}
        add_results = [True, False]  # First call succeeds, second fails

        def mock_add(key, value, timeout):
            result = add_results[call_count["add"]]
            call_count["add"] += 1
            return result

        with patch("apps.opspilot.utils.base_chat_flow_utils.cache") as mock_cache:
            mock_cache.get.return_value = None  # Both workers see no status
            mock_cache.add.side_effect = mock_add

            utils = TestChatFlowUtils(bot_id="bot_race")
            msg_id = "msg_race_test"

            # Simulate two workers calling is_message_processed
            result_worker_a = utils.is_message_processed(msg_id)
            result_worker_b = utils.is_message_processed(msg_id)

            # Only worker A should get processing rights
            assert result_worker_a is False  # Worker A processes
            assert result_worker_b is True  # Worker B skips

    def test_source_code_uses_cache_add(self):
        """TC-17-17: Verify source code uses cache.add() for atomic operation."""

        from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils

        source = inspect.getsource(BaseChatFlowUtils.is_message_processed)

        # Must use cache.add() for atomic acquisition
        assert "cache.add(" in source, "is_message_processed must use cache.add() for atomic operation"
        # Should NOT use cache.set() for initial processing status
        assert (
            "cache.set(" not in source or "processing" not in source.split("cache.set(")[0].split("cache.add(")[-1]
        ), "is_message_processed should not use cache.set() for processing status"
