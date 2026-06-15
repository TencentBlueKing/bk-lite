"""
Tests for interrupt signal database fallback (Scenario 18, Issue #2960).

Verifies that:
- Cache hit returns True immediately (fast path)
- Cache miss triggers database fallback
- Database fallback detects INTERRUPTED status
- Empty execution_id returns False
- Database query failure is handled gracefully
- Dual-check mechanism works correctly
- Async versions work correctly in async contexts
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

from apps.opspilot.utils.execution_interrupt import (  # noqa: E402
    INTERRUPT_CACHE_PREFIX,
    INTERRUPT_CACHE_TTL,
    _check_interrupt_in_database,
    _get_interrupt_cache_key,
    clear_interrupt_request,
    get_interrupt_request,
    is_interrupt_requested,
    request_interrupt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cache():
    """Mock Django cache with in-memory dict."""
    cache_data = {}

    def mock_get(key):
        return cache_data.get(key)

    def mock_set(key, value, timeout=None):
        cache_data[key] = value

    def mock_delete(key):
        cache_data.pop(key, None)

    with patch("apps.opspilot.utils.execution_interrupt.cache") as cache_mock:
        cache_mock.get = mock_get
        cache_mock.set = mock_set
        cache_mock.delete = mock_delete
        cache_mock._data = cache_data
        yield cache_mock


@pytest.fixture
def mock_db_no_interrupt():
    """Mock database returning no interrupt status."""
    with patch("apps.opspilot.utils.execution_interrupt._check_interrupt_in_database", return_value=False) as mock:
        yield mock


@pytest.fixture
def mock_db_has_interrupt():
    """Mock database returning interrupt status exists."""
    with patch("apps.opspilot.utils.execution_interrupt._check_interrupt_in_database", return_value=True) as mock:
        yield mock


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestCacheKeyFormat:
    """Tests for cache key format."""

    def test_cache_key_format(self):
        """Cache key should follow prefix:execution_id format."""
        execution_id = "exec_123"
        key = _get_interrupt_cache_key(execution_id)
        assert key == f"{INTERRUPT_CACHE_PREFIX}:{execution_id}"

    def test_cache_ttl_default(self):
        """Default TTL should be 3600 seconds (1 hour)."""
        assert INTERRUPT_CACHE_TTL == 3600


class TestRequestInterrupt:
    """Tests for request_interrupt function."""

    def test_request_interrupt_sets_cache(self, mock_cache):
        """TC-18-01: request_interrupt should set cache with payload."""
        execution_id = "exec_001"

        result = request_interrupt(execution_id, reason="user_manual")

        assert result["execution_id"] == execution_id
        assert result["reason"] == "user_manual"
        assert "requested_at" in result

        cache_key = _get_interrupt_cache_key(execution_id)
        assert cache_key in mock_cache._data

    def test_request_interrupt_with_meta(self, mock_cache):
        """TC-18-02: request_interrupt should include meta data."""
        execution_id = "exec_002"
        meta = {"user_id": "user_123", "source": "api"}

        result = request_interrupt(execution_id, reason="timeout", meta=meta)

        assert result["meta"] == meta


class TestGetInterruptRequest:
    """Tests for get_interrupt_request function."""

    def test_get_existing_request(self, mock_cache):
        """TC-18-03: get_interrupt_request should return payload if exists."""
        execution_id = "exec_003"
        request_interrupt(execution_id)

        result = get_interrupt_request(execution_id)

        assert result is not None
        assert result["execution_id"] == execution_id

    def test_get_nonexistent_request(self, mock_cache):
        """TC-18-04: get_interrupt_request should return None if not exists."""
        result = get_interrupt_request("nonexistent_exec")
        assert result is None

    def test_get_empty_execution_id(self, mock_cache):
        """TC-18-05: get_interrupt_request should return None for empty id."""
        assert get_interrupt_request("") is None
        assert get_interrupt_request(None) is None


class TestIsInterruptRequested:
    """Tests for is_interrupt_requested function with dual-check mechanism."""

    def test_cache_hit_returns_true(self, mock_cache, mock_db_no_interrupt):
        """TC-18-06: Cache hit should return True without database query."""
        execution_id = "exec_cache_hit"
        request_interrupt(execution_id)

        result = is_interrupt_requested(execution_id)

        assert result is True
        # Database should not be called when cache hits
        mock_db_no_interrupt.assert_not_called()

    def test_cache_miss_triggers_db_fallback(self, mock_cache, mock_db_has_interrupt):
        """TC-18-07: Cache miss should trigger database fallback."""
        execution_id = "exec_cache_miss"
        # No cache entry

        result = is_interrupt_requested(execution_id)

        assert result is True
        mock_db_has_interrupt.assert_called_once_with(execution_id)

    def test_cache_miss_db_no_interrupt(self, mock_cache, mock_db_no_interrupt):
        """TC-18-08: Cache miss + DB no interrupt should return False."""
        execution_id = "exec_no_interrupt"

        result = is_interrupt_requested(execution_id)

        assert result is False
        mock_db_no_interrupt.assert_called_once_with(execution_id)

    def test_empty_execution_id_returns_false(self, mock_cache):
        """TC-18-09: Empty execution_id should return False immediately."""
        assert is_interrupt_requested("") is False
        assert is_interrupt_requested(None) is False


class TestDatabaseFallback:
    """Tests for _check_interrupt_in_database function."""

    def test_db_query_finds_interrupted_status(self):
        """TC-18-10: Database query should find INTERRUPTED status."""
        execution_id = "exec_db_test"

        # Mock the ORM query - patch at the model's location
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.exists.return_value = True

        with patch("apps.opspilot.models.WorkFlowTaskResult") as mock_model:
            mock_model.objects = mock_queryset

            result = _check_interrupt_in_database(execution_id)

            assert result is True
            mock_queryset.filter.assert_called_once()

    def test_db_query_no_interrupted_status(self):
        """TC-18-11: Database query should return False if no INTERRUPTED status."""
        execution_id = "exec_db_no_interrupt"

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.exists.return_value = False

        with patch("apps.opspilot.models.WorkFlowTaskResult") as mock_model:
            mock_model.objects = mock_queryset

            result = _check_interrupt_in_database(execution_id)

            assert result is False

    def test_db_query_exception_returns_false(self):
        """TC-18-12: Database query exception should return False (graceful degradation)."""
        execution_id = "exec_db_error"

        with patch("apps.opspilot.models.WorkFlowTaskResult") as mock_model:
            mock_model.objects.filter.side_effect = Exception("DB connection error")

            result = _check_interrupt_in_database(execution_id)

            assert result is False


class TestClearInterruptRequest:
    """Tests for clear_interrupt_request function."""

    def test_clear_removes_cache_entry(self, mock_cache):
        """TC-18-13: clear_interrupt_request should remove cache entry."""
        execution_id = "exec_clear"
        request_interrupt(execution_id)

        cache_key = _get_interrupt_cache_key(execution_id)
        assert cache_key in mock_cache._data

        clear_interrupt_request(execution_id)

        assert cache_key not in mock_cache._data

    def test_clear_empty_execution_id(self, mock_cache):
        """TC-18-14: clear_interrupt_request should handle empty id gracefully."""
        # Should not raise
        clear_interrupt_request("")
        clear_interrupt_request(None)


class TestLongRunningTaskScenario:
    """Tests for long-running task scenarios where cache TTL expires."""

    def test_cache_expired_db_fallback_detects_interrupt(self, mock_cache):
        """TC-18-15: After cache TTL expires, DB fallback should still detect interrupt."""
        execution_id = "exec_long_task"

        # Simulate: interrupt was requested, but cache has expired
        # (cache is empty, but DB has INTERRUPTED status)

        mock_queryset = MagicMock()
        mock_queryset.filter.return_value.exists.return_value = True

        with patch("apps.opspilot.models.WorkFlowTaskResult") as mock_model:
            mock_model.objects = mock_queryset

            result = is_interrupt_requested(execution_id)

            assert result is True, "DB fallback should detect interrupt after cache expires"

    def test_dual_check_cache_first_then_db(self, mock_cache):
        """TC-18-16: Dual-check should query cache first, then DB."""
        execution_id = "exec_dual_check"

        call_order = []

        def mock_cache_get(key):
            call_order.append("cache")
            return None  # Cache miss

        def mock_db_check(exec_id):
            call_order.append("db")
            return True

        mock_cache.get = mock_cache_get

        with patch("apps.opspilot.utils.execution_interrupt._check_interrupt_in_database", mock_db_check):
            result = is_interrupt_requested(execution_id)

        assert result is True
        assert call_order == ["cache", "db"], "Should check cache first, then DB"


# ---------------------------------------------------------------------------
# Source Analysis Tests (Issue #2960 - 2.1, 2.3)
# ---------------------------------------------------------------------------


class TestSourceAnalysis:
    """Source-level tests to verify implementation details."""

    def test_db_query_uses_exists_optimization(self):
        """TC-18-17: Database query should use exists() for performance."""

        from apps.opspilot.utils.execution_interrupt import _check_interrupt_in_database

        source = inspect.getsource(_check_interrupt_in_database)
        assert ".exists()" in source, "Should use exists() for performance"
        assert ".first()" not in source, "Should not use first()"
        # Note: .get( is allowed in cache.get(), so we check for model.objects.get
        assert "objects.get(" not in source, "Should not use objects.get()"

    def test_uses_correct_status_enum(self):
        """TC-18-18: Should use WorkFlowTaskStatus.INTERRUPTED enum."""

        from apps.opspilot.utils.execution_interrupt import _check_interrupt_in_database

        source = inspect.getsource(_check_interrupt_in_database)
        assert "WorkFlowTaskStatus.INTERRUPTED" in source, "Should use WorkFlowTaskStatus.INTERRUPTED enum"


# ---------------------------------------------------------------------------
# Async Version Tests (Issue #2960 - async context fix)
# ---------------------------------------------------------------------------


class TestAsyncInterruptCheck:
    """Tests for async versions of interrupt check functions."""

    @pytest.mark.asyncio
    async def test_async_cache_hit_returns_true(self, mock_cache):
        """TC-18-19: Async version should return True on cache hit."""
        from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

        execution_id = "exec_async_cache_hit"
        request_interrupt(execution_id)

        result = await is_interrupt_requested_async(execution_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_async_cache_miss_triggers_db_fallback(self, mock_cache):
        """TC-18-20: Async version should fallback to DB on cache miss."""
        from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

        execution_id = "exec_async_db_fallback"

        # Mock DB to return True (interrupted)
        with patch("apps.opspilot.utils.execution_interrupt._check_interrupt_in_database", return_value=True):
            result = await is_interrupt_requested_async(execution_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_async_empty_execution_id_returns_false(self, mock_cache):
        """TC-18-21: Async version should return False for empty execution_id."""
        from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

        assert await is_interrupt_requested_async("") is False
        assert await is_interrupt_requested_async(None) is False

    @pytest.mark.asyncio
    async def test_async_db_check_uses_sync_to_async(self):
        """TC-18-22: Async DB check should use sync_to_async wrapper."""

        from apps.opspilot.utils.execution_interrupt import _check_interrupt_in_database_async

        source = inspect.getsource(_check_interrupt_in_database_async)
        assert "sync_to_async" in source, "Should use sync_to_async wrapper"
        assert "await" in source, "Should be an async function with await"

    @pytest.mark.asyncio
    async def test_async_version_callable_from_async_context(self, mock_cache):
        """TC-18-23: Async version should be safely callable from async context without errors."""
        from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

        execution_id = "exec_async_context_test"

        # This should NOT raise "You cannot call this from an async context" error
        with patch("apps.opspilot.utils.execution_interrupt._check_interrupt_in_database", return_value=False):
            result = await is_interrupt_requested_async(execution_id)

        assert result is False
