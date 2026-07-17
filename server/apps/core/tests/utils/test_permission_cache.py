import pydantic.root_model  # noqa
"""apps/core/utils/permission_cache.py 真实行为单元测试。

策略：以真实 Django cache（locmem，不支持 delete_pattern）执行键生成/读写/清除主路径；
对支持 delete_pattern 的后端分支，用具备 delete_pattern 的 fake cache 注入到模块的 cache 引用。
断言真实缓存副作用（get/set/delete 后的可见性）与键派生的确定性。
"""
import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.core.utils import permission_cache as pc

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _locmem_cache():
    """强制使用 locmem 后端：确定性、无外部依赖，且不支持 delete_pattern（覆盖索引兜底路径）。"""
    with override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "perm-cache-test"}}
    ):
        cache.clear()
        yield
        cache.clear()


class _PatternCache:
    """支持 delete_pattern 的 fake cache，模拟 django-redis 行为。"""

    def __init__(self):
        self.store = {}

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, ttl=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)

    def delete_pattern(self, pattern):
        prefix = pattern.rstrip("*")
        for k in [k for k in self.store if k.startswith(prefix)]:
            del self.store[k]


# ---------------------------------------------------------------------------
# 键派生
# ---------------------------------------------------------------------------


class TestKeyDerivation:
    def test_user_prefix_stable_and_user_specific(self):
        p1 = pc._get_user_perm_prefix("alice", "domain.com")
        p2 = pc._get_user_perm_prefix("alice", "domain.com")
        p3 = pc._get_user_perm_prefix("bob", "domain.com")
        assert p1 == p2
        assert p1 != p3
        assert p1.startswith(pc.PERM_CACHE_PREFIX)

    def test_cache_key_embeds_user_prefix_and_varies_by_dimensions(self):
        prefix = pc._get_user_perm_prefix("alice", "domain.com")
        k1 = pc._get_cache_key("alice", "domain.com", 1, "cmdb", "view")
        k2 = pc._get_cache_key("alice", "domain.com", 2, "cmdb", "view")
        assert k1.startswith(prefix)
        assert k1 != k2

    def test_cache_key_separates_query_scopes(self):
        app_key = pc._get_cache_key("alice", "domain.com", 1, "log", "policy", query_scope="app")
        module_key = pc._get_cache_key("alice", "domain.com", 1, "log", "policy", query_scope="module")
        assert app_key != module_key

    def test_token_info_key_format(self):
        assert pc._get_token_info_key("u", "d") == "token_info:u:d"

    def test_user_keys_index_format(self):
        assert pc._get_user_keys_index("u", "d") == "user_perm_keys:u:d"


# ---------------------------------------------------------------------------
# token_info 缓存
# ---------------------------------------------------------------------------


class TestTokenInfoCache:
    def test_set_get_clear_roundtrip(self):
        assert pc.get_cached_token_info("u", "domain.com") is None
        pc.set_cached_token_info("u", "domain.com", {"id": 1})
        assert pc.get_cached_token_info("u", "domain.com") == {"id": 1}
        pc.clear_token_info_cache("u", "domain.com")
        assert pc.get_cached_token_info("u", "domain.com") is None


# ---------------------------------------------------------------------------
# permission rules 读写（locmem 后端 -> 触发索引兜底路径）
# ---------------------------------------------------------------------------


class TestPermissionRulesCache:
    def test_miss_returns_none(self):
        assert pc.get_cached_permission_rules("u", "domain.com", 1, "cmdb", "view") is None

    def test_set_then_get_roundtrip(self):
        data = {"team": [1], "instance": []}
        pc.set_cached_permission_rules("u", "domain.com", 1, "cmdb", "view", data)
        assert pc.get_cached_permission_rules("u", "domain.com", 1, "cmdb", "view") == data

    def test_query_scopes_do_not_share_cached_payloads(self):
        app_data = {"team": [1], "instance": []}
        module_data = {"result": True, "data": {"1": app_data}, "team": [1]}
        pc.set_cached_permission_rules("u", "domain.com", 1, "log", "policy", app_data)
        pc.set_cached_permission_rules(
            "u",
            "domain.com",
            1,
            "log",
            "policy",
            module_data,
            query_scope="module",
        )

        assert pc.get_cached_permission_rules("u", "domain.com", 1, "log", "policy") == app_data
        assert (
            pc.get_cached_permission_rules("u", "domain.com", 1, "log", "policy", query_scope="module")
            == module_data
        )

    def test_set_maintains_key_index_on_non_pattern_backend(self):
        pc.set_cached_permission_rules("u", "domain.com", 1, "cmdb", "view", {"team": []})
        index_key = pc._get_user_keys_index("u", "domain.com")
        index = cache.get(index_key)
        assert index is not None
        cache_key = pc._get_cache_key("u", "domain.com", 1, "cmdb", "view")
        assert cache_key in index

    def test_clear_user_cache_by_index_removes_entries(self):
        pc.set_cached_permission_rules("u", "domain.com", 1, "cmdb", "view", {"team": [1]})
        pc.set_cached_permission_rules("u", "domain.com", 2, "cmdb", "edit", {"team": [2]})
        pc.clear_user_permission_cache("u", "domain.com")
        assert pc.get_cached_permission_rules("u", "domain.com", 1, "cmdb", "view") is None
        assert pc.get_cached_permission_rules("u", "domain.com", 2, "cmdb", "edit") is None

    def test_clear_by_index_when_no_index_present(self):
        # 没有任何缓存写入时清除不应报错
        pc.clear_user_permission_cache("ghost", "domain.com")
        assert pc.get_cached_permission_rules("ghost", "domain.com", 1, "cmdb", "view") is None


# ---------------------------------------------------------------------------
# clear_users_permission_cache（批量）
# ---------------------------------------------------------------------------


class TestClearUsersPermissionCache:
    def test_batch_clears_each_user(self):
        pc.set_cached_permission_rules("a", "domain.com", 1, "cmdb", "view", {"team": [1]})
        pc.set_cached_permission_rules("b", "corp.io", 1, "cmdb", "view", {"team": [2]})
        pc.clear_users_permission_cache([{"username": "a"}, {"username": "b", "domain": "corp.io"}])
        assert pc.get_cached_permission_rules("a", "domain.com", 1, "cmdb", "view") is None
        assert pc.get_cached_permission_rules("b", "corp.io", 1, "cmdb", "view") is None

    def test_entry_without_username_skipped(self):
        # 不含 username 的条目不应触发异常
        pc.clear_users_permission_cache([{"domain": "x"}])


# ---------------------------------------------------------------------------
# 支持 delete_pattern 的后端分支
# ---------------------------------------------------------------------------


class TestPatternBackendBranches:
    def test_set_skips_index_on_pattern_backend(self, mocker):
        fake = _PatternCache()
        mocker.patch.object(pc, "cache", fake)
        pc.set_cached_permission_rules("u", "domain.com", 1, "cmdb", "view", {"team": [1]})
        # delete_pattern 后端不维护键索引
        assert pc._get_user_keys_index("u", "domain.com") not in fake.store
        cache_key = pc._get_cache_key("u", "domain.com", 1, "cmdb", "view")
        assert fake.store[cache_key] == {"team": [1]}

    def test_clear_user_uses_delete_pattern(self, mocker):
        fake = _PatternCache()
        mocker.patch.object(pc, "cache", fake)
        pc.set_cached_permission_rules("u", "domain.com", 1, "cmdb", "view", {"team": [1]})
        pc.set_cached_permission_rules("u", "domain.com", 2, "cmdb", "edit", {"team": [2]})
        pc.clear_user_permission_cache("u", "domain.com")
        assert pc.get_cached_permission_rules("u", "domain.com", 1, "cmdb", "view") is None
        assert pc.get_cached_permission_rules("u", "domain.com", 2, "cmdb", "edit") is None

    def test_clear_user_pattern_failure_falls_back_to_index(self, mocker):
        fake = _PatternCache()
        mocker.patch.object(pc, "cache", fake)
        # 先用索引兜底方式写入，再让 delete_pattern 抛错触发回退
        index_key = pc._get_user_keys_index("u", "domain.com")
        cache_key = pc._get_cache_key("u", "domain.com", 1, "cmdb", "view")
        fake.store[cache_key] = {"team": [1]}
        fake.store[index_key] = {cache_key}

        def boom(_pattern):
            raise RuntimeError("redis down")

        mocker.patch.object(fake, "delete_pattern", side_effect=boom)
        # delete_many 不存在于 fake -> _clear_user_cache_by_index 会调用 delete_many；补一个
        fake.delete_many = lambda keys: [fake.store.pop(k, None) for k in keys]
        pc.clear_user_permission_cache("u", "domain.com")
        assert cache_key not in fake.store

    def test_clear_all_uses_delete_pattern(self, mocker):
        fake = _PatternCache()
        mocker.patch.object(pc, "cache", fake)
        fake.store[f"{pc.PERM_CACHE_PREFIX}abc:hash"] = {"team": []}
        fake.store[f"{pc.USER_PERM_KEYS_PREFIX}u:d"] = {"x"}
        pc.clear_all_permission_cache()
        assert fake.store == {}

    def test_clear_all_no_pattern_backend_is_noop(self):
        # locmem 无 delete_pattern -> 仅记录告警，不报错
        pc.set_cached_permission_rules("u", "domain.com", 1, "cmdb", "view", {"team": [1]})
        pc.clear_all_permission_cache()
        # locmem 下无法清除，数据仍在
        assert pc.get_cached_permission_rules("u", "domain.com", 1, "cmdb", "view") == {"team": [1]}
