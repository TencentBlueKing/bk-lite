"""达梦 cursor.execute 串行化补丁的行为回归测试。

覆盖 CursorWrapper.replace_sql_params 缺失时的降级路径：
补丁必须照常装配（否则 settings 加载期直接 AttributeError，达梦启动即失败），
且 -70005 不再走参数内联重试，而是原样抛出原异常。
"""

import sys
import types

import pytest

from apps.core.db_patches import dameng


class _DMError(Exception):
    pass


class _ErrArg:
    def __init__(self, code):
        self.code = code


def _make_dm_error(code):
    return _DMError(_ErrArg(code))


class _BaseCursorWrapper:
    """替身：dmDjango.base.CursorWrapper。"""

    # 由每个用例按需覆盖，记录 base_execute 收到的 (sql, params)
    calls = None
    raise_code = None

    def execute(self, sql, params=None):
        type(self).calls.append((sql, params))
        if type(self).raise_code is not None and params is not None:
            raise _make_dm_error(type(self).raise_code)
        return "ok"


@pytest.fixture
def dm_modules(monkeypatch):
    """注入 dmPython / cw_cornerstone / dmDjango 替身，返回可配置的 CursorWrapper 类。"""

    dm_python = types.ModuleType("dmPython")
    dm_python.DatabaseError = _DMError

    class _CursorWrapper(_BaseCursorWrapper):
        calls = []
        raise_code = None

    wrapper_mod = types.ModuleType("cw_cornerstone.db.dameng.backend.wrapper")
    wrapper_mod.CursorWrapper = _CursorWrapper

    dm_django_base = types.ModuleType("dmDjango.base")
    dm_django_base.CursorWrapper = _BaseCursorWrapper

    for name, mod in {
        "dmPython": dm_python,
        "cw_cornerstone": types.ModuleType("cw_cornerstone"),
        "cw_cornerstone.db": types.ModuleType("cw_cornerstone.db"),
        "cw_cornerstone.db.dameng": types.ModuleType("cw_cornerstone.db.dameng"),
        "cw_cornerstone.db.dameng.backend": types.ModuleType("cw_cornerstone.db.dameng.backend"),
        "cw_cornerstone.db.dameng.backend.wrapper": wrapper_mod,
        "dmDjango": types.ModuleType("dmDjango"),
        "dmDjango.base": dm_django_base,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    original_execute = _BaseCursorWrapper.execute
    yield _CursorWrapper
    _BaseCursorWrapper.execute = original_execute


def test_patch_applies_when_replace_sql_params_missing(dm_modules):
    """缺失 replace_sql_params 时补丁仍完成装配，不抛 AttributeError。"""
    assert not hasattr(dm_modules, "replace_sql_params")

    dameng._patch_cursor_execute_with_lock()

    assert dm_modules.execute is not _BaseCursorWrapper.execute
    assert dm_modules.execute.__name__ == "locked_execute"


def test_normal_execute_passes_through_patched_cursor(dm_modules):
    dm_modules.calls = []
    dameng._patch_cursor_execute_with_lock()

    assert dm_modules().execute("SELECT 1", None) == "ok"
    assert dm_modules.calls == [("SELECT 1", None)]


def test_error_70005_reraises_when_replace_sql_params_missing(dm_modules):
    """降级路径：不做参数内联重试，原异常原样抛出，且不产生第二次 execute。"""
    dm_modules.calls = []
    dm_modules.raise_code = -70005
    dameng._patch_cursor_execute_with_lock()

    with pytest.raises(_DMError) as exc_info:
        dm_modules().execute("INSERT INTO t VALUES (%s)", ("x",))

    assert exc_info.value.args[0].code == -70005
    assert len(dm_modules.calls) == 1, "缺失 replace_sql_params 时不应重试"


def test_error_70005_retries_inline_when_replace_sql_params_available(dm_modules):
    """有 replace_sql_params 的 cw_cornerstone 版本上，原内联重试行为保持不变。"""
    dm_modules.calls = []
    dm_modules.raise_code = -70005
    dm_modules.replace_sql_params = staticmethod(lambda sql: sql)

    dameng._patch_cursor_execute_with_lock()

    cursor = dm_modules()
    # 第二次调用 params=None，替身不再抛错，返回 "ok"
    assert cursor.execute("INSERT INTO t VALUES (%s)", ("x",)) == "ok"
    assert len(dm_modules.calls) == 2
    assert dm_modules.calls[1] == ("INSERT INTO t VALUES (x)", None)


def test_other_error_code_always_reraises(dm_modules):
    dm_modules.calls = []
    dm_modules.raise_code = -6602
    dm_modules.replace_sql_params = staticmethod(lambda sql: sql)

    dameng._patch_cursor_execute_with_lock()

    with pytest.raises(_DMError):
        dm_modules().execute("INSERT INTO t VALUES (%s)", ("x",))
    assert len(dm_modules.calls) == 1
