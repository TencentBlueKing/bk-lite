# -*- coding: utf-8 -*-
"""
NodeFilterHandler 单元测试（Issue #3623）

覆盖 build_standard_filters、normalize_bool_value 以及安全修复（#3609）
的白名单校验逻辑，确保修复有效且不被回归。

所有测试均不依赖 Django ORM / 数据库（纯函数范围），通过
sys.modules 注入伪依赖后直接 importlib 加载被测模块运行，
与 Django settings 完全解耦（规避本地 license_mgmt 缺失导致的
EnterpriseFootprintError）。
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 伪依赖注入（让 views/node.py 可以在无 Django settings 的环境下 import）
# ---------------------------------------------------------------------------

def _install_stub(name, **attrs):
    """向 sys.modules 注入一个带任意属性的伪模块。"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _ensure_package(dotted: str):
    """确保 dotted 路径上每个父包都在 sys.modules 中存在（避免 import 时找不到父包）。"""
    parts = dotted.split(".")
    for i in range(1, len(parts) + 1):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            _install_stub(pkg)


def _load_node_view():
    """加载 apps/node_mgmt/views/node.py，注入最小伪依赖，返回模块对象。"""
    # Django Q object — 用真实 django.db.models.Q（无 settings 依赖）
    from django.db.models import Q  # noqa: F401 (available without settings)

    for pkg in [
        "apps", "apps.core", "apps.core.decorators", "apps.core.utils",
        "apps.node_mgmt", "apps.node_mgmt.constants", "apps.node_mgmt.models",
        "apps.node_mgmt.serializers", "apps.node_mgmt.services",
        "apps.node_mgmt.tasks", "apps.node_mgmt.utils",
        "config", "config.drf",
        "rest_framework", "rest_framework.mixins",
        "rest_framework.decorators", "rest_framework.viewsets",
    ]:
        _ensure_package(pkg)

    # 最小 stub —— 只声明被 views/node.py 顶层 import 用到的符号
    _install_stub("apps.core.decorators.api_permission", HasPermission=lambda *a, **kw: (lambda f: f))
    _install_stub("apps.core.utils.loader", LanguageLoader=object)
    _install_stub("apps.core.utils.web_utils", WebUtils=object)
    _install_stub("apps.node_mgmt.constants.cloudregion_service", CloudRegionServiceConstants=object)
    _install_stub("apps.node_mgmt.constants.collector", CollectorConstants=object)
    _install_stub("apps.node_mgmt.constants.controller", ControllerConstants=object)
    _install_stub("apps.node_mgmt.constants.language", LanguageConstants=object)
    _install_stub("apps.node_mgmt.constants.node", NodeConstants=object)
    _install_stub("config.drf.pagination", CustomPageNumberPagination=object)
    _install_stub(
        "apps.node_mgmt.serializers.node",
        NodeSerializer=object,
        BatchBindingNodeConfigurationSerializer=object,
        BatchOperateNodeCollectorSerializer=object,
        TaskNodesQuerySerializer=object,
    )
    _install_stub("apps.node_mgmt.services.node", NodeService=object)
    _install_stub("apps.node_mgmt.tasks.sidecar_config", sync_node_properties_to_sidecar=None)
    _install_stub("apps.node_mgmt.models.action", CollectorActionTaskNode=object, CollectorActionTask=object)
    _install_stub(
        "apps.node_mgmt.utils.permission",
        add_node_permissions=None,
        authorize_mutable_collector_configuration_ids=None,
        authorize_node_ids=None,
        authorize_target_organizations=None,
        get_authorized_node_queryset=None,
        get_node_permission=None,
    )
    _install_stub("apps.node_mgmt.utils.task_result_schema", normalize_task_result_for_read=None)
    _install_stub("rest_framework.decorators", action=lambda *a, **kw: (lambda f: f))

    # rest_framework.viewsets / mixins stub
    class _FakeViewSet:
        pass

    class _FakeDestroyMixin:
        pass

    sys.modules["rest_framework.viewsets"].GenericViewSet = _FakeViewSet
    sys.modules["rest_framework.mixins"].DestroyModelMixin = _FakeDestroyMixin

    # Node / NodeOrganization 需要 .objects manager（NodeViewSet class body 会调用）
    class _FakeQS:
        def all(self): return self
        def prefetch_related(self, *a): return self
        def order_by(self, *a): return self

    class _FakeManager:
        def all(self): return _FakeQS()

    class _FakeNode:
        objects = _FakeManager()

    class _FakeNodeOrg:
        objects = _FakeManager()

    _install_stub("apps.node_mgmt.models.sidecar", Node=_FakeNode, NodeOrganization=_FakeNodeOrg)

    # 加载模块
    repo_root = Path(__file__).resolve().parents[4]  # wt-issue-scan/
    view_path = repo_root / "server" / "apps" / "node_mgmt" / "views" / "node.py"
    spec = importlib.util.spec_from_file_location("_node_view_under_test", view_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def node_view():
    """模块级 fixture：加载被测模块（耗时操作只做一次）。"""
    return _load_node_view()


# ---------------------------------------------------------------------------
# 测试：build_standard_filters
# ---------------------------------------------------------------------------

class TestBuildStandardFilters:
    """验证 NodeFilterHandler.build_standard_filters 的行为与安全保证。"""

    def _call(self, node_view, params):
        return node_view.NodeFilterHandler.build_standard_filters(params)

    # ── 基础行为 ────────────────────────────────────────────────────────────

    def test_empty_params_returns_empty_q(self, node_view):
        """空 params 应返回空 Q（bool(Q()) == False）。"""
        from django.db.models import Q
        result = self._call(node_view, {})
        assert result == Q()

    def test_none_params_returns_empty_q(self, node_view):
        from django.db.models import Q
        result = self._call(node_view, None)
        assert result == Q()

    def test_valid_field_icontains_builds_q(self, node_view):
        """合法 field + icontains → 正确 Q 对象。"""
        from django.db.models import Q
        params = {"name": [{"lookup_expr": "icontains", "value": "web"}]}
        result = self._call(node_view, params)
        assert result == Q(name__icontains="web")

    def test_valid_field_exact_builds_q(self, node_view):
        """合法 field + exact → Q 对象包含正确 key。"""
        from django.db.models import Q
        params = {"ip": [{"lookup_expr": "exact", "value": "10.0.0.1"}]}
        result = self._call(node_view, params)
        assert result == Q(ip__exact="10.0.0.1")

    def test_default_lookup_expr_is_exact(self, node_view):
        """条件中省略 lookup_expr 时应默认使用 exact。"""
        from django.db.models import Q
        params = {"name": [{"value": "server-01"}]}
        result = self._call(node_view, params)
        assert result == Q(name__exact="server-01")

    def test_multiple_valid_fields_combined_with_and(self, node_view):
        """多个合法字段条件应以 & 组合。"""
        from django.db.models import Q
        params = {
            "name": [{"lookup_expr": "icontains", "value": "web"}],
            "ip": [{"lookup_expr": "exact", "value": "10.0.0.1"}],
        }
        result = self._call(node_view, params)
        assert result == Q(name__icontains="web") & Q(ip__exact="10.0.0.1")

    # ── 安全：字段名白名单校验（#3609 修复验证）────────────────────────────

    def test_unlisted_field_name_is_rejected(self, node_view):
        """非白名单字段名必须被拒绝，不出现在最终 Q 中。

        若把此处白名单校验 revert（删除 `if field_name not in ALLOWED_FILTER_FIELDS`），
        返回的 Q 将包含 ORM 注入路径，断言 result == Q() 将失败。
        """
        from django.db.models import Q
        params = {
            "collectorconfiguration__env_config": [{"lookup_expr": "icontains", "value": "secret"}]
        }
        result = self._call(node_view, params)
        assert result == Q()

    def test_deep_relation_traversal_is_rejected(self, node_view):
        """多层关联跨越（ORM 注入探测路径）应被拒绝。"""
        from django.db.models import Q
        params = {
            "nodeorganization__organization": [{"lookup_expr": "exact", "value": 1}]
        }
        result = self._call(node_view, params)
        assert result == Q()

    def test_mixed_valid_and_invalid_fields_only_valid_survives(self, node_view):
        """合法字段正常过滤，非白名单字段被丢弃。"""
        from django.db.models import Q
        params = {
            "name": [{"lookup_expr": "icontains", "value": "server"}],
            "collectorconfiguration__env_config": [{"lookup_expr": "icontains", "value": "secret"}],
        }
        result = self._call(node_view, params)
        assert result == Q(name__icontains="server")

    # ── 安全：lookup 表达式白名单校验（#3609 修复验证）─────────────────────

    def test_unlisted_lookup_expr_is_rejected(self, node_view):
        """非白名单 lookup_expr 必须被拒绝。

        若把 lookup 校验 revert，`regex` 等危险 lookup 会被透传到 ORM，
        断言 result == Q() 将失败。
        """
        from django.db.models import Q
        params = {"name": [{"lookup_expr": "regex", "value": "^admin.*"}]}
        result = self._call(node_view, params)
        assert result == Q()

    def test_arbitrary_lookup_traversal_rejected(self, node_view):
        """通过 lookup 字段进行跨表探测应被拒绝。"""
        from django.db.models import Q
        params = {"name": [{"lookup_expr": "nodeorganization__organization__exact", "value": "1"}]}
        result = self._call(node_view, params)
        assert result == Q()

    # ── 边界条件 ─────────────────────────────────────────────────────────

    def test_empty_value_skipped(self, node_view):
        """空字符串 value 应被跳过。"""
        from django.db.models import Q
        params = {"name": [{"lookup_expr": "icontains", "value": ""}]}
        result = self._call(node_view, params)
        assert result == Q()

    def test_none_value_skipped(self, node_view):
        """None value 应被跳过。"""
        from django.db.models import Q
        params = {"name": [{"lookup_expr": "exact", "value": None}]}
        result = self._call(node_view, params)
        assert result == Q()

    def test_non_dict_condition_skipped(self, node_view):
        """conditions 列表中非 dict 元素应被静默跳过。"""
        from django.db.models import Q
        params = {"name": ["not-a-dict", None, 42]}
        result = self._call(node_view, params)
        assert result == Q()

    def test_non_list_conditions_skipped(self, node_view):
        """conditions 不是 list 时整个字段应被跳过。"""
        from django.db.models import Q
        params = {"name": "should-be-a-list"}
        result = self._call(node_view, params)
        assert result == Q()

    # ── bool 规范化 ────────────────────────────────────────────────────────

    def test_bool_lookup_expr_normalizes_string_true(self, node_view):
        """lookup_expr='bool' + value='true' → exact + True。"""
        from django.db.models import Q
        params = {"node_type": [{"lookup_expr": "bool", "value": "true"}]}
        result = self._call(node_view, params)
        assert result == Q(node_type__exact=True)

    def test_bool_lookup_expr_normalizes_string_false(self, node_view):
        """lookup_expr='bool' + value='false' → exact + False。"""
        from django.db.models import Q
        params = {"node_type": [{"lookup_expr": "bool", "value": "false"}]}
        result = self._call(node_view, params)
        assert result == Q(node_type__exact=False)

    def test_bool_lookup_expr_normalizes_string_1(self, node_view):
        """lookup_expr='bool' + value='1' → exact + True。"""
        from django.db.models import Q
        params = {"node_type": [{"lookup_expr": "bool", "value": "1"}]}
        result = self._call(node_view, params)
        assert result == Q(node_type__exact=True)


# ---------------------------------------------------------------------------
# 测试：normalize_bool_value
# ---------------------------------------------------------------------------

class TestNormalizeBoolValue:
    @pytest.mark.parametrize("v,expected", [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (None, None),
    ])
    def test_normalize_bool_value(self, node_view, v, expected):
        result = node_view.NodeFilterHandler.normalize_bool_value(v)
        assert result == expected


# ---------------------------------------------------------------------------
# 测试：ALLOWED_FILTER_FIELDS 和 ALLOWED_LOOKUP_EXPRS 常量完整性
# ---------------------------------------------------------------------------

class TestWhitelistConstants:
    def test_allowed_fields_contains_expected_node_fields(self, node_view):
        h = node_view.NodeFilterHandler
        for field in ("id", "name", "ip", "operating_system", "cpu_architecture",
                      "install_method", "node_type", "cloud_region_id"):
            assert field in h.ALLOWED_FILTER_FIELDS, f"预期字段 {field!r} 不在白名单中"

    def test_allowed_lookup_exprs_contains_common_exprs(self, node_view):
        h = node_view.NodeFilterHandler
        for expr in ("exact", "icontains", "startswith", "in", "gt", "gte"):
            assert expr in h.ALLOWED_LOOKUP_EXPRS, f"预期 lookup {expr!r} 不在白名单中"

    def test_dangerous_lookups_not_in_whitelist(self, node_view):
        h = node_view.NodeFilterHandler
        for dangerous in ("regex", "iregex", "range", "date", "year"):
            assert dangerous not in h.ALLOWED_LOOKUP_EXPRS, \
                f"危险 lookup {dangerous!r} 意外出现在白名单中"
