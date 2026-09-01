"""MCP 工具缓存命中/清除与 EnabledFilter 布尔过滤契约。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.opspilot.utils import mcp_cache
from apps.opspilot.viewsets.view_filter import EnabledFilter


class _MemCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def test_mcp_tools_cache_roundtrip_and_clear_by_url():
    mem = _MemCache()
    url = "http://mcp.example/sse"
    tools = [{"name": "search"}]
    with patch("apps.opspilot.utils.mcp_cache.cache", mem):
        assert mcp_cache.get_cached_mcp_tools(url, auth_token="tok", transport="sse") is None
        mcp_cache.set_cached_mcp_tools(url, tools, auth_token="tok", transport="sse")
        assert mcp_cache.get_cached_mcp_tools(url, auth_token="tok", transport="sse") == tools
        assert mcp_cache.get_cached_mcp_tools(url, auth_token="other", transport="sse") is None
        mcp_cache.clear_mcp_tools_cache(url, auth_token="tok", transport="sse")
        assert mcp_cache.get_cached_mcp_tools(url, auth_token="tok", transport="sse") is None


def test_clear_all_mcp_tools_cache_uses_pattern_or_warns():
    backend = SimpleNamespace()
    backend.delete_pattern = MagicMock()
    with patch("apps.opspilot.utils.mcp_cache.cache", backend):
        mcp_cache.clear_mcp_tools_cache()
    backend.delete_pattern.assert_called_once_with("mcp_tools:*")

    with patch("apps.opspilot.utils.mcp_cache.cache", SimpleNamespace()):
        mcp_cache.clear_mcp_tools_cache()

    exploding = SimpleNamespace()
    exploding.delete_pattern = MagicMock(side_effect=RuntimeError("redis down"))
    with patch("apps.opspilot.utils.mcp_cache.cache", exploding):
        mcp_cache.clear_mcp_tools_cache()


def test_enabled_filter_treats_empty_as_noop_and_maps_1_0():
    qs = MagicMock()
    filtered = MagicMock()
    qs.filter.return_value = filtered

    assert EnabledFilter.filter_is_enabled(qs, "is_enabled", "") is qs
    assert EnabledFilter.filter_is_enabled(qs, "is_enabled", None) is qs
    qs.filter.assert_not_called()

    assert EnabledFilter.filter_is_enabled(qs, "is_enabled", "1") is filtered
    qs.filter.assert_called_with(enabled=True)

    assert EnabledFilter.filter_is_enabled(qs, "is_enabled", "0") is filtered
    qs.filter.assert_called_with(enabled=False)
