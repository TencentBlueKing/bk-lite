"""
API Token 权限填充和权限检查的单元测试

测试覆盖：
- _collect_ancestor_group_ids: 有界祖先组 ID 收集（两步查询修复 thundering herd）
- APISecretAuthBackend._get_user_all_roles: 直接角色、组织角色、继承角色
- APISecretAuthBackend._populate_user_permissions: 普通用户、超级用户
- HasRole 装饰器: API Token 请求的权限检查
- HasPermission 装饰器: API Token 请求的权限检查
- 缓存命中和缓存未命中
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from django.core.cache.backends.locmem import LocMemCache

from apps.core.backends import APISecretAuthBackend, _collect_ancestor_group_ids
from apps.core.decorators.api_permission import HasPermission, HasRole
from apps.core.utils import permission_cache
from apps.core.utils.web_utils import WebUtils


class MockUser:
    """模拟用户对象"""

    def __init__(self, username="testuser", domain="domain.com", group_list=None, role_list=None):
        self.username = username
        self.domain = domain
        self.group_list = group_list or []
        self.role_list = role_list or []
        self.roles = []
        self.permission = {}
        self.is_superuser = False
        self.role_ids = []
        self.locale = "en"


class MockGroup:
    """模拟组织对象"""

    def __init__(self, id, parent_id=None, allow_inherit_roles=True, role_ids=None):
        self.id = id
        self.parent_id = parent_id
        self.allow_inherit_roles = allow_inherit_roles
        self._role_ids = role_ids or []

    def roles_all(self):
        return [MockRole(rid) for rid in self._role_ids]


class MockRole:
    """模拟角色对象"""

    def __init__(self, id, app="", name="role"):
        self.id = id
        self.app = app
        self.name = name
        self.menu_list = []


class MockGroupWithRoles:
    """带 roles 关系的模拟组织"""

    def __init__(self, id, parent_id=None, allow_inherit_roles=True, roles=None):
        self.id = id
        self.parent_id = parent_id
        self.allow_inherit_roles = allow_inherit_roles
        self._roles = roles or []

    @property
    def roles(self):
        return SimpleNamespace(all=lambda: self._roles)


# ============================================================================
# _collect_ancestor_group_ids 测试（两步查询修复核心）
# ============================================================================


class TestCollectAncestorGroupIds:
    """测试 _collect_ancestor_group_ids：有界祖先 ID 收集，不触发 prefetch_related().all()"""

    def _make_values_list(self, rows):
        """构造 Group.objects.values_list(...) 返回值"""
        mock_qs = MagicMock()
        mock_qs.__iter__ = lambda s: iter(rows)
        return mock_qs

    def test_empty_seed_returns_empty(self):
        """空种子 ID 不查 DB"""
        result = _collect_ancestor_group_ids([])
        assert result == set()

    def test_single_group_no_parent(self):
        """单个无父组：只返回自身 ID"""
        rows = [(10, 0, True)]
        with patch("apps.core.backends.Group") as MockGroup:
            MockGroup.objects.values_list.return_value = self._make_values_list(rows)
            result = _collect_ancestor_group_ids([10])
        assert result == {10}

    def test_ancestor_chain_collected(self):
        """沿 parent_id 链向上收集祖先 ID"""
        # 10 -> 20 -> 30 (根)，所有层都 allow_inherit_roles=True
        rows = [(10, 20, True), (20, 30, True), (30, 0, True)]
        with patch("apps.core.backends.Group") as MockGroup:
            MockGroup.objects.values_list.return_value = self._make_values_list(rows)
            result = _collect_ancestor_group_ids([10])
        assert result == {10, 20, 30}

    def test_collects_all_ancestors_regardless_of_allow_inherit(self):
        """
        _collect_ancestor_group_ids 收集所有物理祖先（含 allow_inherit_roles=False 的节点），
        allow_inherit 的角色继承过滤由 collect_roles 负责（职责分离）。
        """
        # 10 -> 20 (allow=False) -> 30
        rows = [(10, 20, True), (20, 30, False), (30, 0, True)]
        with patch("apps.core.backends.Group") as MockGroup:
            MockGroup.objects.values_list.return_value = self._make_values_list(rows)
            result = _collect_ancestor_group_ids([10])
        # 所有祖先均被收入，以确保有界加载包含完整父链供 collect_roles 判断
        assert result == {10, 20, 30}

    def test_only_values_list_called_not_prefetch_all(self):
        """修复验证：_collect_ancestor_group_ids 只用 values_list，不调用 prefetch_related().all()"""
        rows = [(10, 0, True)]
        with patch("apps.core.backends.Group") as MockGroup:
            MockGroup.objects.values_list.return_value = self._make_values_list(rows)
            _collect_ancestor_group_ids([10])
        # 必须调用过 values_list
        MockGroup.objects.values_list.assert_called_once_with("id", "parent_id", "allow_inherit_roles")
        # 不能调用 prefetch_related（那是全表扫描的旧路径）
        MockGroup.objects.prefetch_related.assert_not_called()


# ============================================================================
# APISecretAuthBackend._get_user_all_roles 测试
# ============================================================================


def _make_group_qs(groups):
    """构造 Group.objects.prefetch_related('roles').filter(id__in=...) 返回值"""
    mock_qs = MagicMock()
    mock_qs.__iter__ = lambda s: iter(groups)
    return mock_qs


def _patch_two_step_query(groups, ancestor_ids=None):
    """
    同时 patch values_list（轻量查询）和 prefetch_related+filter（有界加载）。

    groups: MockGroupWithRoles 列表（这些就是要被加载的 Group 对象）
    ancestor_ids: 若为 None 则自动从 groups 推断
    """
    if ancestor_ids is None:
        ancestor_ids = {g.id for g in groups}

    # 构造 values_list 返回值：(id, parent_id, allow_inherit_roles)
    vl_rows = [(g.id, g.parent_id or 0, g.allow_inherit_roles) for g in groups]
    vl_mock = MagicMock()
    vl_mock.__iter__ = lambda s: iter(vl_rows)

    # 构造 prefetch_related().filter() 返回值
    pf_mock = MagicMock()
    pf_mock.filter.return_value = _make_group_qs(groups)

    group_mock = MagicMock()
    group_mock.objects.values_list.return_value = vl_mock
    group_mock.objects.prefetch_related.return_value = pf_mock

    return group_mock


@pytest.mark.django_db
class TestGetUserAllRoles:
    """测试 _get_user_all_roles 方法（使用两步有界查询）"""

    def test_user_direct_roles_only(self):
        """测试用户只有直接授权的角色（无 group_list，不触发 Group 查询）。

        个人角色取自 system_mgmt.User.role_list（按 username+domain 查库），
        而非 base.User 对象上的属性，故需创建真实 SystemUser 行。
        """
        from apps.system_mgmt.models import User as SystemUser

        SystemUser.objects.create(
            username="directuser", domain="domain.com", role_list=[1, 2, 3]
        )
        backend = APISecretAuthBackend()
        user = MockUser(username="directuser", group_list=[])

        with patch("apps.core.backends.Group") as MockGroupModel:
            result = backend._get_user_all_roles(user)
            # group_list 为空，不应查询 Group 表
            MockGroupModel.objects.values_list.assert_not_called()
            MockGroupModel.objects.prefetch_related.assert_not_called()

        assert result == {1, 2, 3}

    def test_user_group_roles(self):
        """测试用户通过组织获得的角色"""
        backend = APISecretAuthBackend()
        user = MockUser(role_list=[], group_list=[10])

        group = MockGroupWithRoles(id=10, roles=[MockRole(100), MockRole(101)])

        with patch("apps.core.backends.Group", _patch_two_step_query([group])):
            result = backend._get_user_all_roles(user)

        assert result == {100, 101}

    def test_user_combined_roles(self):
        """测试用户直接角色（来自 system_mgmt.User.role_list）和组织角色的合并"""
        from apps.system_mgmt.models import User as SystemUser

        SystemUser.objects.create(
            username="combineduser", domain="domain.com", role_list=[1, 2]
        )
        backend = APISecretAuthBackend()
        user = MockUser(username="combineduser", group_list=[10])

        group = MockGroupWithRoles(id=10, roles=[MockRole(100)])

        with patch("apps.core.backends.Group", _patch_two_step_query([group])):
            result = backend._get_user_all_roles(user)

        assert result == {1, 2, 100}

    def test_role_inheritance_chain(self):
        """测试角色继承链：有界加载仅包含祖先组"""
        backend = APISecretAuthBackend()
        user = MockUser(role_list=[], group_list=[10])

        # 组织结构: 10 -> 20 -> 30 (根)
        group10 = MockGroupWithRoles(id=10, parent_id=20, allow_inherit_roles=True, roles=[MockRole(100)])
        group20 = MockGroupWithRoles(id=20, parent_id=30, allow_inherit_roles=True, roles=[MockRole(200)])
        group30 = MockGroupWithRoles(id=30, parent_id=None, allow_inherit_roles=True, roles=[MockRole(300)])

        with patch("apps.core.backends.Group", _patch_two_step_query([group10, group20, group30])):
            result = backend._get_user_all_roles(user)

        assert result == {100, 200, 300}

    def test_inheritance_stops_when_disabled(self):
        """测试继承在父级 allow_inherit_roles=False 时停止"""
        backend = APISecretAuthBackend()
        user = MockUser(role_list=[], group_list=[10])

        # 组织结构: 10 -> 20 (allow_inherit_roles=False) -> 30
        # collect_roles(10) 收集 role100，检查 parent(20).allow_inherit_roles=False → 不追 20
        group10 = MockGroupWithRoles(id=10, parent_id=20, allow_inherit_roles=True, roles=[MockRole(100)])
        group20 = MockGroupWithRoles(id=20, parent_id=30, allow_inherit_roles=False, roles=[MockRole(200)])
        group30 = MockGroupWithRoles(id=30, parent_id=None, allow_inherit_roles=True, roles=[MockRole(300)])

        with patch("apps.core.backends.Group", _patch_two_step_query([group10, group20, group30])):
            result = backend._get_user_all_roles(user)

        # collect_roles 检查父级的 allow_inherit_roles：group20.allow_inherit=False → 停止
        # 所以只收集 group10 的 role100
        assert result == {100}

    def test_group_list_with_dict_format(self):
        """测试 group_list 为 [{"id": 1}] 格式"""
        backend = APISecretAuthBackend()
        user = MockUser(role_list=[], group_list=[{"id": 10}])

        group = MockGroupWithRoles(id=10, roles=[MockRole(100)])

        with patch("apps.core.backends.Group", _patch_two_step_query([group])):
            result = backend._get_user_all_roles(user)

        assert result == {100}

    def test_bounded_query_not_full_table_scan(self):
        """
        修复核心验证：有 group_list 时必须使用 filter(id__in=...)，
        不能使用 .all()（全表扫描）。若 revert 修复此测试将失败。
        """
        backend = APISecretAuthBackend()
        user = MockUser(role_list=[], group_list=[10])

        group = MockGroupWithRoles(id=10, roles=[MockRole(100)])
        mock_group_cls = _patch_two_step_query([group])

        with patch("apps.core.backends.Group", mock_group_cls):
            backend._get_user_all_roles(user)

        # 必须调用 prefetch_related("roles").filter(id__in=...)
        mock_group_cls.objects.prefetch_related.assert_called_once_with("roles")
        pf_mock = mock_group_cls.objects.prefetch_related.return_value
        # filter 被调用且参数包含 id__in（有界查询）
        pf_mock.filter.assert_called_once()
        call_kwargs = pf_mock.filter.call_args[1]
        assert "id__in" in call_kwargs, "必须使用 filter(id__in=...) 有界查询，而非 .all() 全表扫描"
        # .all() 不应被直接调用（全表扫描的旧路径）
        pf_mock.all.assert_not_called()


# ============================================================================
# APISecretAuthBackend._populate_user_permissions 测试
# ============================================================================


@pytest.mark.django_db
class TestPopulateUserPermissions:
    """测试 _populate_user_permissions 方法"""

    def test_superuser_detection(self):
        """测试超级用户检测：无 app 的 admin 角色 → is_superuser=True。

        _populate_user_permissions 内部用 apps.core.backends 命名空间的 Role，
        故使用真实 Role 行（而非 patch apps.system_mgmt.models.Role）。
        """
        from apps.system_mgmt.models import Role

        role = Role.objects.create(app="", name="admin", menu_list=[])

        backend = APISecretAuthBackend()
        user = MockUser(username="admin", group_list=[1])

        with patch.object(backend, "_get_user_all_roles", return_value={role.id}):
            backend._populate_user_permissions(user, 1)

        assert user.is_superuser is True
        assert user.role_ids == [role.id]
        # 超级用户不计算菜单权限
        assert user.permission == {}

    def test_system_manager_admin_is_superuser(self):
        """测试 system-manager--admin 角色被识别为超级用户"""
        from apps.system_mgmt.models import Role

        role = Role.objects.create(app="system-manager", name="admin", menu_list=[])

        backend = APISecretAuthBackend()
        user = MockUser(username="sysadmin", group_list=[1])

        with patch.object(backend, "_get_user_all_roles", return_value={role.id}):
            backend._populate_user_permissions(user, 1)

        assert user.is_superuser is True
        assert "system-manager--admin" in user.roles

    def test_normal_user_permissions(self):
        """测试普通用户权限填充：角色名拼接 + 菜单权限聚合"""
        from apps.system_mgmt.models import Menu, Role

        menu1 = Menu.objects.create(app="ops-analysis", name="view-View", display_name="查看", url="/v")
        menu2 = Menu.objects.create(app="ops-analysis", name="view-AddView", display_name="新增", url="/a")
        menu3 = Menu.objects.create(app="system-manager", name="user-View", display_name="用户", url="/u")

        role1 = Role.objects.create(app="ops-analysis", name="viewer", menu_list=[menu1.id, menu2.id])
        role2 = Role.objects.create(app="system-manager", name="editor", menu_list=[menu3.id])

        backend = APISecretAuthBackend()
        user = MockUser(username="normaluser", group_list=[1])

        with patch.object(backend, "_get_user_all_roles", return_value={role1.id, role2.id}):
            backend._populate_user_permissions(user, 1)

        assert user.is_superuser is False
        assert "ops-analysis--viewer" in user.roles
        assert "system-manager--editor" in user.roles
        assert user.permission.get("ops-analysis") == {"view-View", "view-AddView"}
        assert user.permission.get("system-manager") == {"user-View"}
        assert sorted(user.role_ids) == sorted([role1.id, role2.id])

    def test_cache_hit(self):
        """测试缓存命中"""
        backend = APISecretAuthBackend()
        user = MockUser(username="cacheduser", domain="test.com", group_list=[1])

        # Mock cache.get 返回缓存数据
        cached_data = {
            "roles": ["cached-role"],
            "permission": {"app": ["perm1"]},
            "is_superuser": True,
            "role_ids": [999],
        }

        with patch("apps.core.backends.cache") as mock_cache:
            mock_cache.get.return_value = cached_data

            # 不应该调用数据库查询
            with patch.object(backend, "_get_user_all_roles") as mock_get_roles:
                backend._populate_user_permissions(user, 1)
                mock_get_roles.assert_not_called()

        assert user.roles == ["cached-role"]
        assert user.is_superuser is True
        assert user.role_ids == [999]

    def test_cache_miss_then_set(self):
        """测试缓存未命中后设置缓存"""
        backend = APISecretAuthBackend()
        user = MockUser(username="newuser", domain="test.com", group_list=[1])

        with patch("apps.core.backends.cache") as mock_cache, patch(
            "apps.core.backends.register_api_token_permission_cache_key"
        ) as mock_register_cache_key:
            mock_cache.get.return_value = None  # 缓存未命中

            with patch.object(backend, "_get_user_all_roles", return_value=set()):
                with patch("apps.system_mgmt.models.Role") as MockRoleModel:
                    mock_queryset = MagicMock()
                    mock_queryset.__iter__ = lambda self: iter([])
                    mock_queryset.values_list.return_value = []
                    MockRoleModel.objects.filter.return_value = mock_queryset

                    backend._populate_user_permissions(user, 1)

            # 验证缓存已设置
            mock_cache.set.assert_called_once()
            call_args = mock_cache.set.call_args
            assert "roles" in call_args[0][1]
            assert "permission" in call_args[0][1]
            mock_register_cache_key.assert_called_once_with(
                "newuser",
                "test.com",
                backend._get_permission_cache_key("newuser", "test.com", 1),
                backend.PERMISSION_CACHE_TTL,
            )

    def test_cache_index_registration_failure_does_not_leave_snapshot(self):
        """索引登记失败时不得先写入无法失效的权限快照。"""
        backend = APISecretAuthBackend()
        user = MockUser(username="newuser", domain="test.com", group_list=[1])

        with patch("apps.core.backends.cache") as mock_cache, patch(
            "apps.core.backends.register_api_token_permission_cache_key", side_effect=RuntimeError("index unavailable")
        ):
            mock_cache.get.return_value = None
            with patch.object(backend, "_get_user_all_roles", return_value=set()), patch(
                "apps.core.backends.Role"
            ) as mock_role:
                mock_role.objects.filter.return_value.__iter__.return_value = iter([])
                mock_role.objects.filter.return_value.values_list.return_value = []
                backend._populate_user_permissions(user, 1)

        mock_cache.set.assert_not_called()
        assert user.permission == {}
        assert user.is_superuser is False

    def test_revocation_prevents_next_api_auth_from_reusing_snapshot(self):
        """撤权统一清理后，下一次 API 鉴权必须重新计算而不能复用旧权限。"""
        backend = APISecretAuthBackend()
        user = MockUser(username="revoked", domain="test.com", group_list=[1])
        cache_backend = LocMemCache("api-token-revocation", {})
        cache_key = backend._get_permission_cache_key("revoked", "test.com", 1)
        cache_backend.set(
            cache_key,
            {
                "roles": ["admin"],
                "permission": {"cmdb": ["secret-View"]},
                "is_superuser": True,
                "role_ids": [1],
            },
            backend.PERMISSION_CACHE_TTL,
        )

        with patch("apps.core.backends.cache", cache_backend), patch.object(permission_cache, "cache", cache_backend):
            permission_cache.register_api_token_permission_cache_key(
                "revoked", "test.com", cache_key, backend.PERMISSION_CACHE_TTL
            )
            backend._populate_user_permissions(user, 1)
            assert user.is_superuser is True

            permission_cache.clear_user_permission_cache("revoked", "test.com")
            with patch.object(backend, "_get_user_all_roles", return_value=set()), patch(
                "apps.core.backends.Role"
            ) as mock_role:
                mock_role.objects.filter.return_value.__iter__.return_value = iter([])
                mock_role.objects.filter.return_value.values_list.return_value = []
                backend._populate_user_permissions(user, 1)

        assert user.is_superuser is False
        assert user.permission == {}
        assert user.role_ids == []

    def test_exception_handling(self):
        """测试异常处理 - 设置空权限"""
        backend = APISecretAuthBackend()
        user = MockUser(username="erroruser", group_list=[1])

        with patch.object(backend, "_get_user_all_roles", side_effect=Exception("DB Error")):
            backend._populate_user_permissions(user, 1)

        # 异常时应该设置空权限
        assert user.roles == []
        assert user.permission == {}
        assert user.is_superuser is False
        assert user.role_ids == []


# ============================================================================
# HasRole 装饰器测试
# ============================================================================


class TestHasRoleDecorator:
    """测试 HasRole 装饰器"""

    def _make_request(self, user, api_pass=False):
        request = SimpleNamespace()
        request.user = user
        request.api_pass = api_pass
        return request

    def test_api_token_with_required_role(self):
        """测试 API Token 请求有所需角色"""

        @HasRole(["ops-analysis--admin"])
        def protected_view(request):
            return "success"

        user = MockUser()
        user.roles = ["ops-analysis--admin", "other-role"]
        user.is_superuser = False
        request = self._make_request(user, api_pass=True)

        result = protected_view(request)
        assert result == "success"

    def test_api_token_without_required_role(self):
        """测试 API Token 请求缺少所需角色"""

        @HasRole(["ops-analysis--admin"])
        def protected_view(request):
            return "success"

        user = MockUser()
        user.roles = ["other-role"]
        user.is_superuser = False
        request = self._make_request(user, api_pass=True)

        with patch.object(WebUtils, "response_403") as mock_403:
            mock_403.return_value = "forbidden"
            result = protected_view(request)

        assert result == "forbidden"
        mock_403.assert_called_once()

    def test_api_token_superuser_bypass(self):
        """测试 API Token 超级用户绕过角色检查"""

        @HasRole(["ops-analysis--admin"])
        def protected_view(request):
            return "success"

        user = MockUser()
        user.roles = []  # 没有任何角色
        user.is_superuser = True
        request = self._make_request(user, api_pass=True)

        result = protected_view(request)
        assert result == "success"

    def test_no_role_requirement(self):
        """测试无角色要求的端点"""

        @HasRole()
        def open_view(request):
            return "success"

        user = MockUser()
        user.roles = []
        user.is_superuser = False
        request = self._make_request(user, api_pass=True)

        result = open_view(request)
        assert result == "success"


# ============================================================================
# HasPermission 装饰器测试
# ============================================================================


class TestHasPermissionDecorator:
    """测试 HasPermission 装饰器"""

    def _make_request(self, user, api_pass=False):
        request = SimpleNamespace()
        request.user = user
        request.api_pass = api_pass
        return request

    def test_api_token_with_required_permission(self):
        """测试 API Token 请求有所需权限"""

        @HasPermission("view-View", app_name="ops-analysis")
        def protected_view(request):
            return "success"

        user = MockUser()
        user.permission = {"ops-analysis": {"view-View", "view-AddView"}}
        user.is_superuser = False
        request = self._make_request(user, api_pass=True)

        result = protected_view(request)
        assert result == "success"

    def test_api_token_without_required_permission(self):
        """测试 API Token 请求缺少所需权限"""

        @HasPermission("view-AddView", app_name="ops-analysis")
        def protected_view(request):
            return "success"

        user = MockUser()
        user.permission = {"ops-analysis": {"view-View"}}  # 只有 View，没有 AddView
        user.is_superuser = False
        request = self._make_request(user, api_pass=True)

        with patch.object(WebUtils, "response_403") as mock_403:
            mock_403.return_value = "forbidden"
            result = protected_view(request)

        assert result == "forbidden"
        mock_403.assert_called_once()

    def test_api_token_superuser_bypass(self):
        """测试 API Token 超级用户绕过权限检查"""

        @HasPermission("view-AddView", app_name="ops-analysis")
        def protected_view(request):
            return "success"

        user = MockUser()
        user.permission = {}  # 没有任何权限
        user.is_superuser = True
        request = self._make_request(user, api_pass=True)

        result = protected_view(request)
        assert result == "success"

    def test_empty_permission_denied(self):
        """测试空权限被拒绝"""

        @HasPermission("view-View", app_name="ops-analysis")
        def protected_view(request):
            return "success"

        user = MockUser()
        user.permission = {}
        user.is_superuser = False
        request = self._make_request(user, api_pass=True)

        with patch.object(WebUtils, "response_403") as mock_403:
            mock_403.return_value = "forbidden"
            result = protected_view(request)

        assert result == "forbidden"
