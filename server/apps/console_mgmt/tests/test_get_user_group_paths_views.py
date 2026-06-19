"""
console_mgmt get_user_group_paths 按需加载规格测试。

规格要点（Issue #3474 修复）：
- get_user_group_paths 不得调用 Group.objects.all()（全表扫描）
- 采用两阶段按需加载：
  Phase 1: Group.objects.filter(id__in=...).values_list("id","parent_id") 逐层向上收集祖先 ID
  Phase 2: Group.objects.filter(id__in=all_group_ids).prefetch_related("roles") 按需加载对象
- 查询范围与路径深度成正比，而非系统组织总数
"""

import importlib.util
import sys
import types
from unittest.mock import MagicMock, call, patch

import pytest

pytestmark = [pytest.mark.unit]


# --------------------------------------------------------------------------- #
# 独立测试 harness：不依赖 Django ORM / settings，直接加载被测函数
# --------------------------------------------------------------------------- #

def _install(name, **attrs):
    """往 sys.modules 注入伪模块（支持多级路径）。"""
    parts = name.split(".")
    parent = None
    for i, part in enumerate(parts):
        full = ".".join(parts[: i + 1])
        if full not in sys.modules:
            mod = types.ModuleType(full)
            sys.modules[full] = mod
            if parent is not None:
                setattr(parent, part, mod)
        parent = sys.modules[full]
    for k, v in attrs.items():
        setattr(sys.modules[name], k, v)
    return sys.modules[name]


# 构建 Group 桩（返回可链式调用的 mock）
_MockGroupClass = MagicMock()


def _load_views():
    """加载 views.py，注入所有外部依赖的桩。"""
    # Django 框架桩
    _install("django")
    _install("django.contrib")
    _install("django.contrib.auth")
    _install("django.contrib.auth.hashers", check_password=lambda pwd, h: pwd == h, make_password=lambda pwd: f"hashed:{pwd}")
    _install("django.core")
    _install("django.core.cache", cache=MagicMock())
    _install("django.db")
    _install("django.db.transaction", atomic=lambda: __import__("contextlib").contextmanager(lambda f: f)())
    _install("django.http", JsonResponse=lambda d, **kw: d)
    _install("django.utils")
    _install("django.utils.timezone")
    _install("zoneinfo", ZoneInfo=lambda tz: tz)

    # 应用级桩
    _install("apps")
    _install("apps.core")
    _install("apps.core.utils")
    _install("apps.core.utils.loader", LanguageLoader=lambda **kw: MagicMock(get=lambda k, d="": d))
    _install("apps.rpc")
    _install("apps.rpc.system_mgmt", SystemMgmt=MagicMock)
    _install("apps.system_mgmt")
    _install("apps.system_mgmt.models", Group=_MockGroupClass, Role=MagicMock(), User=MagicMock())
    _install("apps.system_mgmt.models.app", App=MagicMock())
    _install("apps.system_mgmt.utils")
    _install("apps.system_mgmt.utils.group_utils", GroupUtils=MagicMock())
    _install("apps.system_mgmt.utils.operation_log_utils", log_operation=MagicMock())

    spec = importlib.util.spec_from_file_location(
        "console_mgmt_views_group_paths",
        "/Users/justin/bklite-loops/wt-issue-scan/server/apps/console_mgmt/views.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_views = _load_views()


# --------------------------------------------------------------------------- #
# 辅助：构建假 Group 对象
# --------------------------------------------------------------------------- #

def _make_group(gid, parent_id=None, name=None):
    g = MagicMock()
    g.id = gid
    g.parent_id = parent_id or 0
    g.name = name or f"Group{gid}"
    g.roles.all.return_value = []
    return g


# --------------------------------------------------------------------------- #
# 核心测试：修复后不得调用 Group.objects.all()
# --------------------------------------------------------------------------- #

class TestGetUserGroupPaths:

    def test_不调用全表查询(self):
        """修复后 get_user_group_paths 不得调用 Group.objects.all()。"""
        mock_group_qs = MagicMock()
        # Phase 1 filter 返回轻量行
        mock_group_qs.filter.return_value.values_list.return_value = [(1, 0)]
        # Phase 2 filter 返回完整对象
        mock_group_qs.filter.return_value.prefetch_related.return_value = [_make_group(1)]

        mock_group_class = MagicMock()
        mock_group_class.objects = mock_group_qs

        _views.GroupUtils.build_group_paths.return_value = ["Root"]

        with patch.object(_views, "Group", mock_group_class):
            result = _views.get_user_group_paths([1])

        # 核心断言：不得调用 .all()
        mock_group_qs.all.assert_not_called(), "修复后不得使用全表 Group.objects.all()"

    def test_空列表直接返回空(self):
        """user_group_list 为空时应直接返回 []，不触发任何 DB 查询。"""
        mock_group_class = MagicMock()
        with patch.object(_views, "Group", mock_group_class):
            result = _views.get_user_group_paths([])

        assert result == []
        mock_group_class.objects.filter.assert_not_called()
        mock_group_class.objects.all.assert_not_called()

    def test_phase1用filter按id集合查询(self):
        """Phase 1 必须用 filter(id__in=...) + values_list('id','parent_id') 查询，不加载完整对象。"""
        mock_group_qs = MagicMock()
        # Phase 1 返回：用户在 group 2，其 parent 为 1，group 1 的 parent 为 0（根）
        def filter_side_effect(**kwargs):
            ids = set(kwargs.get("id__in", []))
            qs = MagicMock()
            if ids == {2}:
                qs.values_list.return_value = [(2, 1)]  # group 2 的 parent 是 1
                qs.prefetch_related.return_value = []
            elif ids == {1}:
                qs.values_list.return_value = [(1, 0)]  # group 1 的 parent 是 0（根）
                qs.prefetch_related.return_value = []
            else:
                # Phase 2: filter(id__in={1,2})
                qs.values_list.return_value = []
                qs.prefetch_related.return_value = [_make_group(1), _make_group(2, parent_id=1)]
            return qs

        mock_group_qs.filter.side_effect = filter_side_effect

        mock_group_class = MagicMock()
        mock_group_class.objects = mock_group_qs

        _views.GroupUtils.build_group_paths.return_value = ["Root/Group2"]

        with patch.object(_views, "Group", mock_group_class):
            result = _views.get_user_group_paths([2])

        # 验证 filter 被调用（而非 all），且第一次调用包含 Phase 1 的 values_list 参数
        assert mock_group_qs.filter.called, "应调用 filter(id__in=...) 而非 all()"
        # 取第一次 filter 调用的参数
        first_call_kwargs = mock_group_qs.filter.call_args_list[0][1]
        assert "id__in" in first_call_kwargs, "Phase 1 的 filter 必须使用 id__in 参数"

    def test_phase2用filter按需加载完整对象(self):
        """Phase 2 必须用 filter(id__in=all_ids).prefetch_related('roles')，且传入的 ID 集合
        只包含路径上的祖先组，而非系统所有组。"""
        # 树结构：Root(id=100) -> Parent(id=200) -> UserGroup(id=300)
        # 系统还有无关组 id=999，但不应被查询
        call_record = []

        def filter_side_effect(**kwargs):
            ids = set(kwargs.get("id__in", []))
            call_record.append(ids)
            qs = MagicMock()
            if ids == {300}:
                # Phase 1 第一轮：user group 300 的 parent 是 200
                qs.values_list.return_value = [(300, 200)]
                qs.prefetch_related.return_value = []
            elif ids == {200}:
                # Phase 1 第二轮：group 200 的 parent 是 100
                qs.values_list.return_value = [(200, 100)]
                qs.prefetch_related.return_value = []
            elif ids == {100}:
                # Phase 1 第三轮：group 100 的 parent 是 0（根）
                qs.values_list.return_value = [(100, 0)]
                qs.prefetch_related.return_value = []
            else:
                # Phase 2：加载完整对象（id__in={100,200,300}）
                qs.values_list.return_value = []
                qs.prefetch_related.return_value = [
                    _make_group(100, parent_id=0, name="Root"),
                    _make_group(200, parent_id=100, name="Parent"),
                    _make_group(300, parent_id=200, name="UserGroup"),
                ]
            return qs

        mock_group_qs = MagicMock()
        mock_group_qs.filter.side_effect = filter_side_effect

        mock_group_class = MagicMock()
        mock_group_class.objects = mock_group_qs

        _views.GroupUtils.build_group_paths.return_value = ["Root/Parent/UserGroup"]

        with patch.object(_views, "Group", mock_group_class):
            _views.get_user_group_paths([300])

        # Phase 2 的 filter 必须只包含路径上的 ID（100, 200, 300），不含无关的 999
        phase2_ids = call_record[-1]  # 最后一次 filter 调用是 Phase 2
        assert 999 not in phase2_ids, "Phase 2 不应查询无关的组 id=999（全表问题未修复）"
        assert {100, 200, 300} == phase2_ids, f"Phase 2 应只包含路径上的组 ID，实际: {phase2_ids}"

    def test_revert修复后all被调用(self):
        """回归保护：若将修复 revert 回 Group.objects.all()，此测试应失败。
        （本测试是元测试，用于文档目的；实际运行时修复已应用，此处验证 all 未被调用。）"""
        mock_group_qs = MagicMock()
        mock_group_qs.filter.return_value.values_list.return_value = [(1, 0)]
        mock_group_qs.filter.return_value.prefetch_related.return_value = [_make_group(1)]

        mock_group_class = MagicMock()
        mock_group_class.objects = mock_group_qs

        _views.GroupUtils.build_group_paths.return_value = ["Root"]

        with patch.object(_views, "Group", mock_group_class):
            _views.get_user_group_paths([1])

        # 修复后 all() 不应被调用；若 revert 回旧实现，all() 会被调用，此断言失败
        mock_group_qs.all.assert_not_called()
