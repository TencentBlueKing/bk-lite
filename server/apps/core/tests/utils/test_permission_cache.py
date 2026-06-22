"""
权限缓存并发安全性测试

验证 Issue #3491 修复：set_cached_permission_rules 对 user_keys_index
的非原子 RMW 竞态已消除——clear_user_permission_cache 不再漏删缓存键。

这些测试完全 Django-free（无需 ORM/settings），通过向 sys.modules 注入
伪依赖后直接 importlib 加载被测模块。
"""

import importlib.util
import sys
import types
from threading import Thread
from unittest.mock import MagicMock, call, patch


# ──────────────────────────────────────────────────
# Bootstrap: 向 sys.modules 注入最小伪依赖，让被测模块可导入
# ──────────────────────────────────────────────────


def _install(name: str, **attrs):
    """将一个伪模块注入 sys.modules（支持多级路径）"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod

    # 确保父级模块也存在
    parts = name.split(".")
    for i in range(1, len(parts)):
        parent_name = ".".join(parts[:i])
        if parent_name not in sys.modules:
            sys.modules[parent_name] = types.ModuleType(parent_name)
    return mod


def _load_module(path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# 伪 cache 对象（模拟 django-redis，有 delete_pattern）
fake_cache_store: dict = {}


class FakeCache:
    """模拟 Django cache API，含 delete_pattern（仿 django-redis）"""

    def __init__(self):
        self._store: dict = {}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value, timeout=None):
        self._store[key] = value

    def delete(self, key):
        self._store.pop(key, None)

    def delete_many(self, keys):
        for k in keys:
            self._store.pop(k, None)

    def delete_pattern(self, pattern: str):
        """简单前缀匹配实现（去掉末尾 * 做前缀匹配）"""
        prefix = pattern.rstrip("*")
        to_delete = [k for k in list(self._store) if k.startswith(prefix)]
        for k in to_delete:
            self._store.pop(k, None)

    def reset(self):
        self._store.clear()


fake_cache = FakeCache()
_install("django", core=types.ModuleType("django.core"))
_install("django.core", cache=types.ModuleType("django.core.cache"))
_install("django.core.cache", cache=fake_cache)
_install("apps")
_install("apps.core")
_install("apps.core.logger", logger=MagicMock())

import os

_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "utils",
    "permission_cache.py",
)
_MODULE_PATH = os.path.normpath(_MODULE_PATH)

# 清理可能已缓存的旧版本
for key in [k for k in sys.modules if "permission_cache" in k]:
    del sys.modules[key]

pc = _load_module(_MODULE_PATH, "apps.core.utils.permission_cache")


# ──────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────


def _reset():
    fake_cache.reset()


def _set_perm(username="alice", domain="domain.com", team=1, app="cmdb", key="view", data=None):
    pc.set_cached_permission_rules(username, domain, team, app, key, data or {"allow": True})


def _get_perm(username="alice", domain="domain.com", team=1, app="cmdb", key="view"):
    return pc.get_cached_permission_rules(username, domain, team, app, key)


def _clear(username="alice", domain="domain.com"):
    pc.clear_user_permission_cache(username, domain)


# ──────────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────────


def test_set_and_get_basic():
    """基本读写：set 后 get 能拿到数据"""
    _reset()
    _set_perm(key="view", data={"allow": True})
    result = _get_perm(key="view")
    assert result == {"allow": True}, f"期望 {{'allow': True}}，实际 {result}"


def test_clear_removes_cached_key():
    """单键清除：set 后 clear，get 返回 None"""
    _reset()
    _set_perm(key="view", data={"allow": True})
    assert _get_perm(key="view") is not None, "clear 前应有缓存"
    _clear()
    result = _get_perm(key="view")
    assert result is None, f"clear 后缓存应为 None，实际 {result}"


def test_clear_removes_all_keys_for_user():
    """同一用户多键全清：设置三个不同权限，clear 后全部消失"""
    _reset()
    _set_perm(key="view", data={"v": 1})
    _set_perm(key="edit", data={"v": 2})
    _set_perm(key="delete", data={"v": 3})

    assert _get_perm(key="view") is not None
    assert _get_perm(key="edit") is not None
    assert _get_perm(key="delete") is not None

    _clear()

    assert _get_perm(key="view") is None, "clear 后 view 权限应消失"
    assert _get_perm(key="edit") is None, "clear 后 edit 权限应消失"
    assert _get_perm(key="delete") is None, "clear 后 delete 权限应消失"


def test_concurrent_set_no_key_lost_after_clear():
    """
    核心回归：并发 set 不同键后，clear 必须清除所有键（修复前会漏删）

    模拟并发：两个线程同时为同一用户写不同 permission_key，
    随后 clear，验证两个键均已从缓存中移除。
    若把 _get_cache_key 改回旧版（全局 PERM_CACHE_PREFIX + 单 hash），
    并恢复旧版 clear_user_permission_cache（走 index），
    并发写时 index 会被覆盖，导致其中一个键漏删，此测试将失败。
    """
    _reset()

    errors = []

    def write_key(k):
        try:
            _set_perm(key=k, data={"key": k})
        except Exception as e:
            errors.append(e)

    # 并发写两个不同权限键
    t1 = Thread(target=write_key, args=("view",))
    t2 = Thread(target=write_key, args=("edit",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"并发写入出现异常：{errors}"

    # 清除用户所有权限缓存
    _clear()

    # 断言两个键均被清除（修复前并发场景下可能漏删其中一个）
    view_cached = _get_perm(key="view")
    edit_cached = _get_perm(key="edit")

    assert view_cached is None, f"并发 set 后 clear，view 权限应消失，实际: {view_cached}"
    assert edit_cached is None, f"并发 set 后 clear，edit 权限应消失，实际: {edit_cached}"


def test_clear_does_not_affect_other_users():
    """隔离性：清除 alice 的缓存不影响 bob 的缓存"""
    _reset()
    _set_perm(username="alice", key="view", data={"u": "alice"})
    _set_perm(username="bob", key="view", data={"u": "bob"})

    _clear(username="alice")

    assert _get_perm(username="alice", key="view") is None, "alice 的缓存应被清除"
    assert _get_perm(username="bob", key="view") == {"u": "bob"}, "bob 的缓存不应受影响"


def test_cache_key_embeds_user_prefix():
    """
    结构验证：新版 cache key 应包含 per-user 前缀，
    使 delete_pattern(user_prefix + "*") 能精确按用户清除。

    若 _get_cache_key 回退到旧版（perm_rules:{global_hash} 无用户前缀），
    delete_pattern 无法识别 per-user 键，此测试将失败。
    """
    username, domain = "alice", "domain.com"
    user_prefix = pc._get_user_perm_prefix(username, domain)
    cache_key = pc._get_cache_key(username, domain, 1, "cmdb", "view")

    assert cache_key.startswith(user_prefix), (
        f"cache key 应以 per-user 前缀 '{user_prefix}' 开头，实际: '{cache_key}'"
    )
    assert user_prefix.startswith(pc.PERM_CACHE_PREFIX), (
        f"user_prefix 应以全局前缀 '{pc.PERM_CACHE_PREFIX}' 开头"
    )


def test_different_users_have_different_prefixes():
    """不同用户应有不同的 per-user 前缀，避免 pattern 清除时误伤他人"""
    prefix_alice = pc._get_user_perm_prefix("alice", "domain.com")
    prefix_bob = pc._get_user_perm_prefix("bob", "domain.com")
    assert prefix_alice != prefix_bob, "不同用户的 user_prefix 不应相同"


if __name__ == "__main__":
    tests = [
        test_set_and_get_basic,
        test_clear_removes_cached_key,
        test_clear_removes_all_keys_for_user,
        test_concurrent_set_no_key_lost_after_clear,
        test_clear_does_not_affect_other_users,
        test_cache_key_embeds_user_prefix,
        test_different_users_have_different_prefixes,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
