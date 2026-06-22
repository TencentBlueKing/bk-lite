"""
测试 PolicyViewSet._get_accessible_policy_queryset 的请求级缓存行为。

验证目标（Issue #3358）：
  - 同一 request 内多次调用同一 collect_type_id 时，只执行一次全量 DB 扫描（RPC 调用）。
  - 同一 request 内以不同 collect_type_id 调用时，各自独立缓存，互不污染。
  - 不同 request 之间缓存相互隔离。
  - collect_type_id 指定时，DB 层 filter 在 Python 遍历前已生效。

测试策略：用 unittest.mock 注入伪依赖，用 SimpleNamespace 模拟 request（支持 setattr），
Django-free，可直接用 uv run python 跑。
"""
import sys
import types
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# 最小伪依赖注入
# ---------------------------------------------------------------------------

def _make_fake_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# Global mocks — reset per test
_get_permissions_rules_mock = MagicMock()
_check_instance_permission_mock = MagicMock()
_filter_instances_with_permissions_mock = MagicMock()


def _inject_stubs():
    # django_celery_beat
    sys.modules["django_celery_beat"] = _make_fake_module("django_celery_beat")
    sys.modules["django_celery_beat.models"] = _make_fake_module(
        "django_celery_beat.models", PeriodicTask=MagicMock(), CrontabSchedule=MagicMock()
    )

    # rest_framework
    sys.modules["rest_framework"] = _make_fake_module("rest_framework")
    sys.modules["rest_framework.viewsets"] = _make_fake_module(
        "rest_framework.viewsets", ModelViewSet=object, ReadOnlyModelViewSet=object
    )
    sys.modules["rest_framework.decorators"] = _make_fake_module(
        "rest_framework.decorators", action=lambda **kw: (lambda f: f)
    )

    # django.db.models (available without settings)
    import django.db.models as _djm
    sys.modules.setdefault("django.db.models", _djm)

    # apps.core
    sys.modules["apps"] = _make_fake_module("apps")
    sys.modules["apps.core"] = _make_fake_module("apps.core")
    sys.modules["apps.core.exceptions"] = _make_fake_module("apps.core.exceptions")
    sys.modules["apps.core.exceptions.base_app_exception"] = _make_fake_module(
        "apps.core.exceptions.base_app_exception", BaseAppException=Exception
    )

    # apps.core.utils.permission_utils — key mock point
    perm_mod = _make_fake_module(
        "apps.core.utils.permission_utils",
        get_permission_rules=MagicMock(return_value={}),
        get_permissions_rules=_get_permissions_rules_mock,
        permission_filter=MagicMock(),
        check_instance_permission=_check_instance_permission_mock,
        filter_instances_with_permissions=_filter_instances_with_permissions_mock,
        get_instance_permissions=MagicMock(return_value=[]),
    )
    sys.modules["apps.core.utils"] = _make_fake_module("apps.core.utils")
    sys.modules["apps.core.utils.permission_utils"] = perm_mod

    sys.modules["apps.core.utils.web_utils"] = _make_fake_module(
        "apps.core.utils.web_utils", WebUtils=MagicMock()
    )

    # apps.log.*
    sys.modules["apps.log"] = _make_fake_module("apps.log")
    sys.modules["apps.log.constants"] = _make_fake_module("apps.log.constants")
    sys.modules["apps.log.constants.permission"] = _make_fake_module(
        "apps.log.constants.permission",
        PermissionConstants=SimpleNamespace(POLICY_MODULE="policy", DEFAULT_PERMISSION="Read"),
    )
    sys.modules["apps.log.constants.alert_policy"] = _make_fake_module(
        "apps.log.constants.alert_policy", AlertConstants=MagicMock()
    )
    sys.modules["apps.log.filters"] = _make_fake_module("apps.log.filters")
    sys.modules["apps.log.filters.policy"] = _make_fake_module(
        "apps.log.filters.policy",
        PolicyFilter=MagicMock(),
        AlertFilter=MagicMock(),
        EventFilter=MagicMock(),
        EventRawDataFilter=MagicMock(),
    )
    sys.modules["apps.log.models"] = _make_fake_module("apps.log.models")
    sys.modules["apps.log.models.policy"] = _make_fake_module(
        "apps.log.models.policy",
        Policy=MagicMock(),
        PolicyOrganization=MagicMock(),
        Alert=MagicMock(),
        Event=MagicMock(),
        EventRawData=MagicMock(),
    )
    sys.modules["apps.log.serializers"] = _make_fake_module("apps.log.serializers")
    sys.modules["apps.log.serializers.policy"] = _make_fake_module(
        "apps.log.serializers.policy",
        PolicySerializer=MagicMock(),
        AlertSerializer=MagicMock(),
        EventSerializer=MagicMock(),
        EventRawDataSerializer=MagicMock(),
    )
    sys.modules["config"] = _make_fake_module("config")
    sys.modules["config.drf"] = _make_fake_module("config.drf")
    sys.modules["config.drf.pagination"] = _make_fake_module(
        "config.drf.pagination", CustomPageNumberPagination=MagicMock()
    )


import os as _os

_POLICY_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "views", "policy.py"
)


def _load_policy_module():
    # Always reload so that module-level symbols pick up the latest sys.modules stubs
    spec = importlib.util.spec_from_file_location("apps.log.views.policy", _POLICY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_request():
    """Use SimpleNamespace so setattr/getattr work correctly (unlike MagicMock)."""
    req = SimpleNamespace()
    req.COOKIES = {"current_team": "1", "include_children": "0"}
    req.user = MagicMock()
    return req


def _make_policy_obj(policy_id, collect_type_id=None, org_ids=None):
    obj = MagicMock()
    obj.id = policy_id
    obj.collect_type_id = collect_type_id
    org_rels = []
    for oid in (org_ids or [1]):
        rel = MagicMock()
        rel.organization = oid
        org_rels.append(rel)
    obj.policyorganization_set.all.return_value = org_rels
    return obj


def _patch_db(mod, policies):
    """Patch Policy.objects so that the QuerySet iteration returns `policies`.

    ORM chain: Policy.objects.select_related(...) -> chain
               chain.prefetch_related(...)        -> base_qs
               base_qs.filter(...)                -> filtered_qs  (when collect_type_id given)

    For assertions:
      - DB-filter tests assert on base_qs.filter (the object the code actually calls filter on).
      - No-filter tests assert base_qs.filter.assert_not_called().
    """
    # base_qs: returned by chain.prefetch_related(); iterable for no-filter path
    base_qs = MagicMock()
    base_qs.__iter__ = MagicMock(return_value=iter(policies))

    # filtered_qs: returned by base_qs.filter(); iterable for filtered path
    filtered_qs = MagicMock()
    filtered_qs.__iter__ = MagicMock(return_value=iter(policies))
    base_qs.filter.return_value = filtered_qs

    chain = MagicMock()
    chain.prefetch_related.return_value = base_qs

    mod.Policy.objects.select_related.return_value = chain
    mod.Policy.objects.filter.return_value = MagicMock()
    return chain, base_qs, filtered_qs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPolicyQuerysetCache(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _inject_stubs()
        cls.mod = _load_policy_module()
        cls.PolicyViewSet = cls.mod.PolicyViewSet

    def setUp(self):
        # Reset mocks between tests
        _get_permissions_rules_mock.reset_mock()
        _get_permissions_rules_mock.return_value = {
            "data": {"all": {"team": [1]}},
            "team": [1],
        }
        _check_instance_permission_mock.reset_mock()
        _check_instance_permission_mock.return_value = True
        _filter_instances_with_permissions_mock.reset_mock()
        _filter_instances_with_permissions_mock.return_value = {}

        self.mod.Policy.objects.reset_mock()

        self.policies = [
            _make_policy_obj(1, collect_type_id=10, org_ids=[1]),
            _make_policy_obj(2, collect_type_id=20, org_ids=[2]),
        ]

    def _new_viewset(self):
        return object.__new__(self.PolicyViewSet)

    def test_same_collect_type_id_cached_on_second_call(self):
        """
        Second call with same collect_type_id (None) should NOT invoke get_permissions_rules again.
        If this test fails after reverting the cache code, it means the test is correctly guarding.
        """
        vs = self._new_viewset()
        req = _fake_request()
        _patch_db(self.mod, self.policies[:1])

        vs._get_accessible_policy_queryset(req, collect_type_id=None)
        count_after_first = _get_permissions_rules_mock.call_count  # should be 1

        vs._get_accessible_policy_queryset(req, collect_type_id=None)
        count_after_second = _get_permissions_rules_mock.call_count  # should still be 1

        self.assertEqual(count_after_first, 1, "First call should invoke get_permissions_rules once")
        self.assertEqual(
            count_after_second,
            count_after_first,
            "Cached second call must NOT invoke get_permissions_rules again",
        )

    def test_different_collect_type_ids_have_separate_caches(self):
        """
        Calls with different collect_type_ids each trigger their own DB scan,
        but subsequent calls with the same id are served from cache.
        """
        vs = self._new_viewset()
        req = _fake_request()
        _patch_db(self.mod, self.policies[:1])

        # First call: collect_type_id=None
        vs._get_accessible_policy_queryset(req, collect_type_id=None)
        count_1 = _get_permissions_rules_mock.call_count

        # Second call: different key — must trigger new scan
        vs._get_accessible_policy_queryset(req, collect_type_id="10")
        count_2 = _get_permissions_rules_mock.call_count

        self.assertEqual(count_2, count_1 + 1, "New collect_type_id should trigger a fresh scan")

        # Third call: same key as second — must be cached
        vs._get_accessible_policy_queryset(req, collect_type_id="10")
        count_3 = _get_permissions_rules_mock.call_count

        self.assertEqual(count_3, count_2, "Repeat key should be served from cache")

    def test_different_requests_have_isolated_caches(self):
        """Cache must not leak between separate request objects."""
        vs = self._new_viewset()
        req_a = _fake_request()
        req_b = _fake_request()
        _patch_db(self.mod, self.policies[:1])

        vs._get_accessible_policy_queryset(req_a, collect_type_id=None)
        count_after_a = _get_permissions_rules_mock.call_count

        vs._get_accessible_policy_queryset(req_b, collect_type_id=None)
        count_after_b = _get_permissions_rules_mock.call_count

        self.assertEqual(
            count_after_b,
            count_after_a + 1,
            "Second request must trigger a fresh scan (no cross-request cache leakage)",
        )

    def test_db_filter_applied_before_python_loop_for_specific_collect_type(self):
        """
        When collect_type_id='10' is provided, the ORM chain must call .filter(Q(collect_type_id='10') | Q(collect_type_id__isnull=True))
        on base_qs (result of prefetch_related) BEFORE the Python for-loop so fewer rows are loaded.
        原逻辑：指定 collect_type_id 时同时保留全局策略（collect_type_id IS NULL），语义不变。
        """
        import django.db.models as djm

        vs = self._new_viewset()
        req = _fake_request()
        _, base_qs, _ = _patch_db(self.mod, self.policies[:1])

        vs._get_accessible_policy_queryset(req, collect_type_id="10")

        base_qs.filter.assert_called_once()
        call_args = base_qs.filter.call_args
        self.assertEqual(len(call_args.args), 1, "filter() should be called with a single Q object")
        q_arg = call_args.args[0]
        self.assertIsInstance(q_arg, djm.Q, "filter() argument must be a Q object")
        # Q(collect_type_id='10') | Q(collect_type_id__isnull=True)
        self.assertEqual(q_arg.connector, "OR")
        children = q_arg.children
        self.assertIn(("collect_type_id", "10"), children)
        self.assertIn(("collect_type_id__isnull", True), children)

    def test_db_filter_applied_for_global(self):
        """When collect_type_id='global', filter(collect_type_id__isnull=True) must be applied on base_qs."""
        vs = self._new_viewset()
        req = _fake_request()
        _, base_qs, _ = _patch_db(self.mod, self.policies[:1])

        vs._get_accessible_policy_queryset(req, collect_type_id="global")

        base_qs.filter.assert_called_once_with(collect_type_id__isnull=True)

    def test_no_db_filter_when_no_collect_type_id(self):
        """When collect_type_id is None, no DB filter is applied (all policies loaded)."""
        vs = self._new_viewset()
        req = _fake_request()
        _, base_qs, _ = _patch_db(self.mod, self.policies[:1])

        vs._get_accessible_policy_queryset(req, collect_type_id=None)

        base_qs.filter.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
