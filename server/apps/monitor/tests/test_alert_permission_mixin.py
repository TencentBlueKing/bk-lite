"""
Tests for AlertPermissionMixin — Issue #3608.

验证：
1. DRY：_get_all_accessible_policy_ids 只在 AlertPermissionMixin 中定义一处，
   MonitorAlertViewSet / MonitorEventViewSet 均从 Mixin 继承，不再各自重复实现。
2. 性能优化：当 policy_permissions 不包含 "all" 键时，DB 查询使用
   monitor_object_id__in 预过滤，而非 MonitorPolicy.objects.all()。
3. 管理员路径（"all" 键存在）：降级到全量查询，保持行为不变。
4. 无权限时返回空列表。

测试策略：Django-free，通过 sys.modules 注入伪依赖后 importlib 加载被测模块，
直接对 AlertPermissionMixin 的方法进行单元测试，revert 修复后断言必须失败。
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

_MISSING = object()


def _build_fake_modules():
    """向 sys.modules 注入最小伪依赖，使 monitor_alert.py 可被 import。"""
    mods = {}
    originals = {}

    def add(name, **attrs):
        if name not in originals:
            originals[name] = sys.modules.get(name, _MISSING)
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        mods[name] = m
        return m

    # Django stubs
    add("django")
    add("django.db")
    add("django.db.models", Q=MagicMock())

    # rest_framework stubs — use distinct base classes to avoid MRO "duplicate base class" error
    class _ViewSet:
        pass

    class _GenericViewSet:
        pass

    class _RetrieveModelMixin:
        pass

    class _UpdateModelMixin:
        pass

    class _ListModelMixin:
        pass

    rf = add("rest_framework")
    add("rest_framework.viewsets", ViewSet=_ViewSet, GenericViewSet=_GenericViewSet)
    add("rest_framework.mixins",
        RetrieveModelMixin=_RetrieveModelMixin,
        UpdateModelMixin=_UpdateModelMixin,
        ListModelMixin=_ListModelMixin)
    add("rest_framework.decorators", action=lambda **kw: (lambda f: f))
    add("rest_framework.response", Response=MagicMock())

    # apps.core stubs
    add("apps")
    add("apps.core")
    add("apps.core.logger", monitor_logger=MagicMock())
    add("apps.core.utils")
    add("apps.core.utils.permission_utils",
        get_permission_rules=MagicMock(),
        permission_filter=MagicMock(),
        get_permissions_rules=MagicMock(),
        check_instance_permission=MagicMock())
    add("apps.core.utils.web_utils", WebUtils=MagicMock())
    add("apps.core.utils.team_utils", get_current_team=MagicMock(return_value=1))

    # apps.monitor stubs
    add("apps.monitor")
    add("apps.monitor.constants")
    add("apps.monitor.constants.permission",
        PermissionConstants=MagicMock(POLICY_MODULE="policy"))
    add("apps.monitor.models",
        MonitorAlert=MagicMock(),
        MonitorEvent=MagicMock(),
        MonitorPolicy=MagicMock(),
        MonitorEventRawData=MagicMock(),
        MonitorAlertMetricSnapshot=MagicMock(),
        PolicyInstanceBaseline=MagicMock())
    add("apps.monitor.filters")
    add("apps.monitor.filters.monitor_alert", MonitorAlertFilter=MagicMock())
    add("apps.monitor.serializers")
    add("apps.monitor.serializers.monitor_alert", MonitorAlertSerializer=MagicMock())
    add("apps.monitor.serializers.monitor_policy", MonitorPolicySerializer=MagicMock())
    add("apps.monitor.services")
    add("apps.monitor.services.alert_lifecycle_notify", AlertLifecycleNotifier=MagicMock())
    add("apps.monitor.services.policy_baseline", PolicyBaselineService=MagicMock())
    add("apps.monitor.utils")
    add("apps.monitor.utils.dimension", parse_instance_id=MagicMock())
    add("apps.monitor.utils.pagination", parse_page_params=MagicMock())
    add("config")
    add("config.drf")
    add("config.drf.pagination", CustomPageNumberPagination=MagicMock())

    return mods, originals


def _load_monitor_alert(mods, originals):
    """Load monitor_alert module using importlib with fake dependencies in place."""
    module_name = "apps.monitor.views.monitor_alert"
    if module_name not in originals:
        originals[module_name] = sys.modules.get(module_name, _MISSING)
    spec = importlib.util.spec_from_file_location(
        module_name,
        Path(__file__).resolve().parents[1] / "views" / "monitor_alert.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _restore_modules(originals):
    for name, original in reversed(list(originals.items())):
        if original is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


class TestAlertPermissionMixin(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._mods, cls._original_modules = _build_fake_modules()
        cls._module = _load_monitor_alert(cls._mods, cls._original_modules)
        cls.AlertPermissionMixin = cls._module.AlertPermissionMixin
        cls.MonitorAlertViewSet = cls._module.MonitorAlertViewSet
        cls.MonitorEventViewSet = cls._module.MonitorEventViewSet

    @classmethod
    def tearDownClass(cls):
        _restore_modules(cls._original_modules)

    # -----------------------------------------------------------------
    # 1. DRY：两个 ViewSet 都继承自 AlertPermissionMixin
    # -----------------------------------------------------------------

    def test_monitor_alert_viewset_inherits_mixin(self):
        """MonitorAlertViewSet 必须继承 AlertPermissionMixin。"""
        self.assertTrue(
            issubclass(self.MonitorAlertViewSet, self.AlertPermissionMixin),
            "MonitorAlertViewSet 未继承 AlertPermissionMixin"
        )

    def test_monitor_event_viewset_inherits_mixin(self):
        """MonitorEventViewSet 必须继承 AlertPermissionMixin。"""
        self.assertTrue(
            issubclass(self.MonitorEventViewSet, self.AlertPermissionMixin),
            "MonitorEventViewSet 未继承 AlertPermissionMixin"
        )

    def test_method_defined_only_in_mixin(self):
        """_get_all_accessible_policy_ids 只在 Mixin 中定义，不在子类字典中单独存在。"""
        self.assertNotIn(
            "_get_all_accessible_policy_ids",
            self.MonitorAlertViewSet.__dict__,
            "_get_all_accessible_policy_ids 不应在 MonitorAlertViewSet.__dict__ 中（应由 Mixin 提供）"
        )
        self.assertNotIn(
            "_get_all_accessible_policy_ids",
            self.MonitorEventViewSet.__dict__,
            "_get_all_accessible_policy_ids 不应在 MonitorEventViewSet.__dict__ 中（应由 Mixin 提供）"
        )
        self.assertIn(
            "_get_all_accessible_policy_ids",
            self.AlertPermissionMixin.__dict__,
            "_get_all_accessible_policy_ids 应在 AlertPermissionMixin.__dict__ 中"
        )

    # -----------------------------------------------------------------
    # 2. 性能优化：无 "all" 键时使用 monitor_object_id__in 预过滤
    # -----------------------------------------------------------------

    def test_db_filter_by_object_type_when_no_all_key(self):
        """
        当 policy_permissions 不含 "all" 键时，MonitorPolicy.objects.filter 必须被调用
        且参数为 monitor_object_id__in，而非 MonitorPolicy.objects.all()。

        revert 修复（即恢复全量查询）后此断言会失败。
        """
        mixin = self.AlertPermissionMixin()
        fake_request = MagicMock()
        fake_request.COOKIES.get.return_value = "0"

        # 权限数据：有两个 object_type（1 和 2），无 "all" 键
        fake_permissions = {
            "1": {"instance": [{"id": 10}], "team": []},
            "2": {"instance": [{"id": 20}], "team": []},
        }
        permissions_result = {"data": fake_permissions, "team": [1]}

        # Mock get_permissions_rules
        self._module.get_permissions_rules.return_value = permissions_result
        self._module.get_current_team.return_value = 1

        # Mock check_instance_permission to return False (no accessible policies)
        self._module.check_instance_permission.return_value = False

        # Mock MonitorPolicy queryset chain
        fake_qs = MagicMock()
        fake_qs.select_related.return_value = fake_qs
        fake_qs.prefetch_related.return_value = fake_qs
        fake_qs.__iter__ = MagicMock(return_value=iter([]))
        self._module.MonitorPolicy.objects.filter.return_value = fake_qs
        self._module.MonitorPolicy.objects.all.return_value = fake_qs

        result = mixin._get_all_accessible_policy_ids(fake_request)

        # Must use filter with monitor_object_id__in, not all()
        self._module.MonitorPolicy.objects.filter.assert_called_once_with(
            monitor_object_id__in=[1, 2]
        )
        self._module.MonitorPolicy.objects.all.assert_not_called()
        self.assertEqual(result, [])

    # -----------------------------------------------------------------
    # 3. 管理员路径（"all" 键存在）：使用 all()
    # -----------------------------------------------------------------

    def test_db_uses_all_when_admin_all_key_present(self):
        """
        当 policy_permissions 含 "all" 键时，降级为 MonitorPolicy.objects.all()，
        保持原有管理员权限行为不变。
        """
        mixin = self.AlertPermissionMixin()
        fake_request = MagicMock()
        fake_request.COOKIES.get.return_value = "0"

        fake_permissions = {
            "all": {"team": [1]},
            "1": {"instance": [], "team": []},
        }
        permissions_result = {"data": fake_permissions, "team": [1]}

        self._module.get_permissions_rules.return_value = permissions_result
        self._module.get_current_team.return_value = 1
        self._module.check_instance_permission.return_value = False

        fake_qs = MagicMock()
        fake_qs.select_related.return_value = fake_qs
        fake_qs.prefetch_related.return_value = fake_qs
        fake_qs.__iter__ = MagicMock(return_value=iter([]))
        self._module.MonitorPolicy.objects.all.return_value = fake_qs
        self._module.MonitorPolicy.objects.filter.reset_mock()

        mixin._get_all_accessible_policy_ids(fake_request)

        self._module.MonitorPolicy.objects.all.assert_called_once()
        # filter should NOT have been called with monitor_object_id__in
        for c in self._module.MonitorPolicy.objects.filter.call_args_list:
            self.assertNotIn("monitor_object_id__in", c.kwargs,
                             "admin 路径不应调用 monitor_object_id__in 过滤")

    # -----------------------------------------------------------------
    # 4. 无权限时返回空列表
    # -----------------------------------------------------------------

    def test_empty_policy_permissions_returns_empty_list(self):
        """policy_permissions 为空时，不查 DB，直接返回 []。"""
        mixin = self.AlertPermissionMixin()
        fake_request = MagicMock()
        fake_request.COOKIES.get.return_value = "0"

        self._module.get_permissions_rules.return_value = {"data": {}, "team": []}
        self._module.get_current_team.return_value = 1
        self._module.MonitorPolicy.objects.filter.reset_mock()
        self._module.MonitorPolicy.objects.all.reset_mock()

        result = mixin._get_all_accessible_policy_ids(fake_request)

        self.assertEqual(result, [])
        self._module.MonitorPolicy.objects.filter.assert_not_called()
        self._module.MonitorPolicy.objects.all.assert_not_called()

    # -----------------------------------------------------------------
    # 5. 有权限时返回正确 ID 列表
    # -----------------------------------------------------------------

    def test_returns_accessible_policy_ids(self):
        """check_instance_permission 返回 True 的策略 ID 应出现在结果中。"""
        mixin = self.AlertPermissionMixin()
        fake_request = MagicMock()
        fake_request.COOKIES.get.return_value = "0"

        fake_permissions = {"3": {"instance": [{"id": 100}], "team": []}}
        permissions_result = {"data": fake_permissions, "team": [1]}

        self._module.get_permissions_rules.return_value = permissions_result
        self._module.get_current_team.return_value = 1

        # Two mock policies: one passes permission check, one fails
        policy_pass = MagicMock()
        policy_pass.monitor_object_id = 3
        policy_pass.id = 100
        policy_pass.policyorganization_set.all.return_value = []

        policy_fail = MagicMock()
        policy_fail.monitor_object_id = 3
        policy_fail.id = 999
        policy_fail.policyorganization_set.all.return_value = []

        fake_qs = MagicMock()
        fake_qs.select_related.return_value = fake_qs
        fake_qs.prefetch_related.return_value = fake_qs
        fake_qs.__iter__ = MagicMock(return_value=iter([policy_pass, policy_fail]))
        self._module.MonitorPolicy.objects.filter.return_value = fake_qs

        # policy_pass passes, policy_fail doesn't
        self._module.check_instance_permission.side_effect = (
            lambda obj_id, pol_id, teams, perms, cur_team: pol_id == 100
        )

        result = mixin._get_all_accessible_policy_ids(fake_request)

        self.assertEqual(result, [100])
        self.assertNotIn(999, result)


if __name__ == "__main__":
    unittest.main()
