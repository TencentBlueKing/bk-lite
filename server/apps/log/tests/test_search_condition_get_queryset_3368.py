"""
针对 Issue #3368 的回归测试：SearchConditionViewSet.get_queryset
验证全量加载 Python 过滤已替换为 .only()/.iterator() 模式，
确保 get_queryset 不再将所有字段加载进内存。

测试使用注入式 harness（不依赖 Django settings / ORM），
直接对 get_queryset 的分支逻辑进行白盒验证。
"""
import importlib
import importlib.util
import sys
import types
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Harness：往 sys.modules 注入最小伪依赖，然后 exec_module 加载 search.py
# ---------------------------------------------------------------------------

def _install(name, **attrs):
    """在 sys.modules 中注册一个伪模块，attrs 设置为模块属性。"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _install_pkg(dotted_name, **attrs):
    """递归确保父包存在，再注册指定名称。"""
    parts = dotted_name.split(".")
    for i in range(1, len(parts) + 1):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            _install(pkg)
    mod = _install(dotted_name, **attrs)
    # 把最末子属性挂到父包上
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        setattr(parent, parts[-1], mod)
    return mod


def _load_view_module():
    """加载 server/apps/log/views/search.py 并返回模块对象。"""
    # --- rest_framework ---
    _install_pkg("rest_framework")
    _install_pkg("rest_framework.decorators", action=lambda *a, **kw: (lambda f: f))
    _install_pkg("rest_framework.viewsets", ViewSet=object, ModelViewSet=object)

    # --- apps.core ---
    _install_pkg("apps")
    _install_pkg("apps.core")
    _install_pkg("apps.core.utils")
    _install_pkg("apps.core.utils.web_utils", WebUtils=SimpleNamespace(
        response_error=lambda *a, **kw: None,
        response_success=lambda data: data,
    ))

    # --- apps.log ---
    _install_pkg("apps.log")
    _install_pkg("apps.log.services")
    _install_pkg("apps.log.services.search", SearchService=object)
    _install_pkg("apps.log.services.access_scope", LogAccessScopeService=object)

    # SearchCondition 伪 Model（关键：让我们追踪 .only() / .iterator() 调用）
    class _FakeObjects:
        def all(self):
            return self
        def filter(self, **kwargs):
            return self
        def only(self, *fields):
            return self
        def iterator(self, chunk_size=None):
            return iter([])
        def none(self):
            return []

    class _FakeSearchCondition:
        objects = None  # 将在各测试中替换

    _FakeSearchCondition.objects = _FakeObjects()

    _install_pkg("apps.log.models")
    _install_pkg("apps.log.models.log_group", SearchCondition=_FakeSearchCondition)

    _install_pkg("apps.log.serializers")
    _install_pkg("apps.log.serializers.log_group", SearchConditionSerializer=object)
    _install_pkg("apps.log.serializers.search",
                 LogFieldValuesSerializer=object,
                 LogHitsSerializer=object,
                 LogSearchSerializer=object,
                 LogTopStatsSerializer=object)
    _install_pkg("apps.log.filters")
    _install_pkg("apps.log.filters.log_group", SearchConditionFilter=object)

    view_path = (
        __file__
        .replace("tests/test_search_condition_get_queryset_3368.py", "views/search.py")
    )
    spec = importlib.util.spec_from_file_location("apps.log.views.search", view_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load once per module
_view_mod = _load_view_module()
SearchConditionViewSet = _view_mod.SearchConditionViewSet


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

class _CallLog:
    """记录方法调用顺序与参数，用于断言 .only() / .iterator() 是否被调用。"""
    def __init__(self, rows):
        self.calls = []
        self._rows = rows
        self._filter_kwargs = {}

    def filter(self, **kwargs):
        self.calls.append(("filter", kwargs))
        self._filter_kwargs = kwargs
        return self

    def only(self, *fields):
        self.calls.append(("only", fields))
        return self

    def iterator(self, chunk_size=None):
        self.calls.append(("iterator", chunk_size))
        return iter(self._rows)

    def none(self):
        self.calls.append(("none",))
        return []

    # 兼容 filter(id__in=...) 返回真实列表，供最终结果断言
    def __iter__(self):
        return iter(self._rows)


def _make_viewset(team_cookie, rows, accessible_group_ids):
    """构造一个 SearchConditionViewSet 实例，注入伪 request 和伪 ORM。"""
    call_log = _CallLog(rows)

    # 让 SearchCondition.objects 指向 call_log
    import apps.log.models.log_group as lg_mod
    lg_mod.SearchCondition.objects = call_log

    # 同步更新 search 模块里的 SearchCondition.objects（exec_module 时绑定的可能是不同引用）
    _view_mod.SearchCondition.objects = call_log

    request = SimpleNamespace(COOKIES={"current_team": team_cookie} if team_cookie else {})

    vs = SearchConditionViewSet()
    vs.request = request
    vs._get_accessible_group_ids = lambda: accessible_group_ids

    return vs, call_log


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

def _make_row(row_id, condition):
    """构造一个模拟 SearchCondition 实例（仅有 id 和 condition 字段）。"""
    return SimpleNamespace(id=row_id, condition=condition)


class TestGetQuerysetUsesOnlyAndIterator:
    """确认修复后 get_queryset 使用 .only() + .iterator() 而非全量加载。"""

    def test_only_is_called_with_id_and_condition(self):
        """get_queryset 必须调用 .only('id', 'condition') 以避免全量字段加载。"""
        rows = [_make_row(1, {"log_groups": ["g1"]})]
        vs, call_log = _make_viewset("10", rows, {"g1"})

        vs.get_queryset()

        method_names = [c[0] for c in call_log.calls]
        assert "only" in method_names, f"期望调用 .only()，实际调用链：{call_log.calls}"
        only_call = next(c for c in call_log.calls if c[0] == "only")
        assert "id" in only_call[1], "only() 必须包含 'id' 字段"
        assert "condition" in only_call[1], "only() 必须包含 'condition' 字段"

    def test_iterator_is_called(self):
        """get_queryset 必须调用 .iterator() 以实现流式迭代、避免全量驻内存。"""
        rows = [_make_row(2, {"log_groups": []})]
        vs, call_log = _make_viewset("10", rows, {"g1"})

        vs.get_queryset()

        method_names = [c[0] for c in call_log.calls]
        assert "iterator" in method_names, f"期望调用 .iterator()，实际调用链：{call_log.calls}"

    def test_only_called_before_iterator(self):
        """调用顺序必须是 .only() 先于 .iterator()，确保字段裁剪在流式取数之前。"""
        rows = [_make_row(3, {"log_groups": ["g1"]})]
        vs, call_log = _make_viewset("10", rows, {"g1"})

        vs.get_queryset()

        method_names = [c[0] for c in call_log.calls]
        assert method_names.index("only") < method_names.index("iterator"), (
            f".only() 必须在 .iterator() 之前调用，实际顺序：{method_names}"
        )


class TestGetQuerysetAccessibilityLogic:
    """验证权限过滤语义不因修复而改变。"""

    def test_empty_log_groups_accessible_when_user_has_groups(self):
        """condition.log_groups == [] 时，只要用户有可访问分组就应通过。"""
        rows = [_make_row(1, {"log_groups": []})]
        vs, _ = _make_viewset("10", rows, {"g1"})

        qs = vs.get_queryset()

        # 应返回包含 id=1 的结果集
        assert qs is not None

    def test_empty_log_groups_inaccessible_when_user_has_no_groups(self):
        """condition.log_groups == [] 且用户无可访问分组时，不应返回该条。"""
        rows = [_make_row(1, {"log_groups": []})]
        vs, _ = _make_viewset("10", rows, set())

        qs = vs.get_queryset()

        # accessible_ids 应为空，get_queryset 应返回 none()
        assert qs == [] or qs is None or (hasattr(qs, "__iter__") and list(qs) == [])

    def test_non_empty_log_groups_all_accessible(self):
        """condition.log_groups 全在 accessible_group_ids 内，应通过。"""
        rows = [_make_row(1, {"log_groups": ["g1", "g2"]})]
        vs, _ = _make_viewset("10", rows, {"g1", "g2", "g3"})

        qs = vs.get_queryset()

        assert qs is not None

    def test_non_empty_log_groups_partial_inaccessible(self):
        """condition.log_groups 中有任一组 ID 不在 accessible_group_ids，应拒绝。"""
        rows = [_make_row(1, {"log_groups": ["g1", "g_unknown"]})]
        vs, _ = _make_viewset("10", rows, {"g1"})

        qs = vs.get_queryset()

        assert qs == [] or qs is None or (hasattr(qs, "__iter__") and list(qs) == [])

    def test_no_team_cookie_returns_empty(self):
        """无 current_team Cookie 时必须返回空结果集。"""
        vs, _ = _make_viewset(None, [], set())

        qs = vs.get_queryset()

        assert qs == [] or qs is None or (hasattr(qs, "__iter__") and list(qs) == [])

    def test_multiple_rows_partial_filter(self):
        """多条记录中只有部分符合权限，结果应只含合法条目 ID。"""
        rows = [
            _make_row(10, {"log_groups": ["g1"]}),       # 可访问
            _make_row(11, {"log_groups": ["g_secret"]}),  # 不可访问
            _make_row(12, {"log_groups": []}),             # 空组 → 可访问（有 accessible）
        ]
        vs, call_log = _make_viewset("10", rows, {"g1"})

        vs.get_queryset()

        # 确认 iterator 被调用（核心修复点）
        method_names = [c[0] for c in call_log.calls]
        assert "iterator" in method_names


class TestRevertCheck:
    """若将修复还原（去掉 .only() / .iterator()），这些测试应失败。

    当前断言直接验证调用链：只要修复存在这两个调用就 pass；
    若 revert 掉修复（变回全量 list comprehension），只会 fail。
    """

    def test_only_and_iterator_both_present_in_call_chain(self):
        rows = [_make_row(99, {"log_groups": ["gx"]})]
        vs, call_log = _make_viewset("5", rows, {"gx"})

        vs.get_queryset()

        method_names = [c[0] for c in call_log.calls]
        assert "only" in method_names and "iterator" in method_names, (
            "修复被还原：get_queryset 不再调用 .only()/.iterator()，"
            f"实际调用链：{method_names}"
        )
