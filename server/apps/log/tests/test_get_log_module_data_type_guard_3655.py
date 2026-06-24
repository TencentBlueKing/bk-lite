"""
Issue #3655: get_log_module_data 参数无类型校验导致 NATS worker 崩溃

这些测试采用 Django-free 注入方式：直接 importlib 加载被测模块，
用 sys.modules 注入伪依赖，绕过 ORM 及 settings 加载。

验证准则：revert 修复代码（去掉 int() 转换 + 范围校验），
所有测试必须失败——否则测试未覆盖修复点。
"""

import importlib.util
import sys
import types
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# 注入伪依赖（nats_client + apps.log.models.*）
# ---------------------------------------------------------------------------

def _install(name, **attrs):
    """往 sys.modules 注入一个伪模块（支持属性设置）。"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_permission_module():
    """
    每次调用都重新加载 nats/permission.py，避免测试间模块缓存相互污染。
    返回加载后的模块对象。
    """
    # ── nats_client ──────────────────────────────────────────────────────────
    def _register(fn):
        return fn

    _install("nats_client", register=_register)

    # ── apps.log.models（顶层包 + 子模块）─────────────────────────────────────
    _install("apps")
    _install("apps.log")
    _install("apps.log.models")
    _install("apps.log.models.policy", Policy=object)

    # LogGroup / CollectType / CollectInstance 用于 from ... import 语句
    for sym in ("LogGroup", "CollectType", "CollectInstance"):
        setattr(sys.modules["apps.log.models"], sym, object)

    # ── 加载被测文件 ───────────────────────────────────────────────────────────
    import os
    permission_path = os.path.join(
        os.path.dirname(__file__),
        "..", "nats", "permission.py",
    )
    spec = importlib.util.spec_from_file_location(
        "apps.log.nats.permission", permission_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 辅助：构造能被正常执行的伪 queryset
# ---------------------------------------------------------------------------

class _FakeQS:
    """模拟 Django QuerySet 的最小接口。"""

    def __init__(self, items=None):
        self._items = items or [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

    def filter(self, **kwargs):
        return self

    def distinct(self):
        return self

    def count(self):
        return len(self._items)

    def values(self, *fields):
        return self

    def __getitem__(self, sl):
        return self._items[sl]


def _make_handler_with_queryset(qs: _FakeQS):
    """
    返回一个已注入 ORM 的 get_log_module_data 函数。
    通过 monkeypatch LogGroup.objects / Policy.objects / CollectInstance.objects。
    """
    mod = _load_permission_module()

    # patch model managers
    class _Manager:
        def filter(self, **kwargs):
            return qs

    for attr in ("LogGroup", "CollectType", "CollectInstance"):
        fake_model = type(attr, (), {"objects": _Manager()})()
        setattr(mod, attr, fake_model)

    # Policy 同样需要 patch
    fake_policy = type("Policy", (), {"objects": _Manager()})()
    setattr(mod, "Policy", fake_policy)

    return mod.get_log_module_data


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestGetLogModuleDataTypeGuard:
    """修复验证：参数类型错误时返回错误响应，而非崩溃。"""

    def test_string_page_returns_error_not_typeerror(self):
        """page='2'（字符串）在修复前触发 TypeError。修复后返回 result=False 的错误响应。"""
        handler = _make_handler_with_queryset(_FakeQS())
        result = handler("log_group", None, "not-a-number", 10, 1)
        assert result.get("result") is False
        assert "参数类型错误" in result.get("message", "")

    def test_string_page_size_returns_error_not_typeerror(self):
        """page_size='abc'（字符串）在修复前触发 TypeError。修复后返回错误响应。"""
        handler = _make_handler_with_queryset(_FakeQS())
        result = handler("log_group", None, 1, "abc", 1)
        assert result.get("result") is False
        assert "参数类型错误" in result.get("message", "")

    def test_string_group_id_returns_error_not_orm_crash(self):
        """group_id='xyz'（字符串）在修复前导致 ORM TypeError。修复后返回错误响应。"""
        handler = _make_handler_with_queryset(_FakeQS())
        result = handler("log_group", None, 1, 10, "xyz")
        assert result.get("result") is False
        assert "参数类型错误" in result.get("message", "")

    def test_negative_page_size_clamped_to_one(self):
        """page_size=-1 在修复前导致负数切片，返回静默错误数据。修复后 clamp 为 1。"""
        qs = _FakeQS([{"id": i, "name": str(i)} for i in range(1, 6)])
        handler = _make_handler_with_queryset(qs)
        result = handler("log_group", None, 1, -1, 1)
        # 修复后正常返回，page_size 被 clamp 为 1，start=0 end=1
        assert "result" not in result or result.get("result") is not False
        assert result.get("count") == 5
        # 取第一条（切片 [0:1]），不应该从末尾反向取
        assert result["items"] == [{"id": 1, "name": "1"}]

    def test_zero_page_size_clamped_to_one(self):
        """page_size=0 在修复前导致 ZeroDivisionError 或空结果，修复后 clamp 为 1。"""
        qs = _FakeQS([{"id": 1, "name": "a"}])
        handler = _make_handler_with_queryset(qs)
        result = handler("log_group", None, 1, 0, 1)
        assert "result" not in result or result.get("result") is not False
        assert result.get("count") == 1

    def test_page_size_exceeds_max_clamped(self):
        """page_size 超过 _PAGE_SIZE_MAX 时被 clamp 到上限，不崩溃。"""
        qs = _FakeQS([{"id": i, "name": str(i)} for i in range(1, 3)])
        handler = _make_handler_with_queryset(qs)
        result = handler("log_group", None, 1, 99999, 1)
        assert "result" not in result or result.get("result") is not False
        assert result.get("count") == 2

    def test_numeric_strings_are_accepted(self):
        """'1'、'10'、'42' 这类数字字符串（NATS 反序列化常见）应被正常转换为 int。"""
        qs = _FakeQS([{"id": i, "name": str(i)} for i in range(1, 11)])
        handler = _make_handler_with_queryset(qs)
        result = handler("policy", "ctype-1", "1", "5", "42")
        assert result.get("count") == 10
        assert len(result.get("items", [])) == 5

    def test_none_page_returns_error(self):
        """page=None 时返回错误响应，不崩溃。"""
        handler = _make_handler_with_queryset(_FakeQS())
        result = handler("log_group", None, None, 10, 1)
        assert result.get("result") is False
        assert "参数类型错误" in result.get("message", "")
