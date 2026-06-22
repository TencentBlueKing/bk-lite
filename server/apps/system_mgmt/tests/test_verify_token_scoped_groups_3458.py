"""
Tests for Issue #3458: verify_token cache-miss 全表扫描修复

验证修复核心：
1. _collect_ancestor_group_ids — 沿 parent_id 链向上收集祖先 ID
2. get_user_all_roles — 仅加载祖先范围内的组（不再全表 prefetch）
3. verify_token cache-miss 路径 — 非超管不再执行全表 Group 扫描

所有测试均为 Django-free 注入式（sys.modules + importlib），不依赖 ORM/settings。
Revert-fail 准则：若回滚修复代码，每个核心断言都会失败（已通过 git stash 验证）。
"""
import importlib.util
import sys
import types
import os


def _install(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_nats_api():
    """加载 nats_api 模块，注入最小伪依赖，返回模块及关键伪类。"""
    base = os.path.join(os.path.dirname(__file__), "..", "nats_api.py")
    base = os.path.abspath(base)

    # 清理旧版本
    for key in list(sys.modules.keys()):
        if "nats_api" in key and "system_mgmt" in key:
            del sys.modules[key]

    _install("django.core.cache",
             cache=types.SimpleNamespace(get=lambda k: None, set=lambda *a, **kw: None))
    _install("django.db.models", Q=lambda **kw: kw)
    _install("django.utils.timezone")
    _install("django.contrib.auth.hashers",
             check_password=lambda a, b: False, make_password=lambda a: a)
    _install("django.db.transaction")

    nc = _install("nats_client")
    nc.register = lambda f: f

    _install("apps.core.constants",
             VERIFY_TOKEN_USER_NOT_FOUND_CODE="USER_NOT_FOUND",
             VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE="user not found")
    _logger = types.SimpleNamespace(info=lambda *a: None, error=lambda *a: None,
                                    warning=lambda *a: None, debug=lambda *a: None)
    _install("apps.core.logger", system_mgmt_logger=_logger)
    _install("apps.core.utils.loader", LanguageLoader=object)
    _install("apps.core.utils.permission_cache",
             get_cached_token_info=lambda *a: None,
             set_cached_token_info=lambda *a: None,
             clear_token_info_cache=lambda *a: None,
             clear_users_permission_cache=lambda *a: None)
    _install("apps.system_mgmt.guest_menus",
             CMDB_MENUS=[], MONITOR_MENUS=[], OPSPILOT_GUEST_MENUS=[])
    _install("apps.system_mgmt.models.system_settings", SystemSettings=object)
    _install("apps.system_mgmt.otp_challenge",
             check_rate_limit=lambda *a: None, create_challenge=lambda *a: None,
             invalidate_challenge=lambda *a: None, record_failed_attempt=lambda *a: None,
             reset_rate_limit=lambda *a: None, verify_challenge=lambda *a: None)
    _install("apps.system_mgmt.services.role_manage", RoleManage=object)
    _install("apps.system_mgmt.utils.bk_user_utils", get_bk_user_info=lambda *a: {})

    class _FakeGroupUtils:
        @staticmethod
        def build_group_tree(groups, is_superuser=False, user_groups=None):
            return []

    _install("apps.system_mgmt.utils.group_utils", GroupUtils=_FakeGroupUtils)
    _install("apps.system_mgmt.utils.password_validator", PasswordValidator=object)
    _install("apps.system_mgmt.utils.pwd_policy_cache", get_pwd_policy_settings=lambda: {})
    _install("apps.system_mgmt.utils.token_blacklist",
             blacklist_token=lambda *a: None, is_blacklisted=lambda *a: False)
    _install("jwt")
    _install("pyotp")
    _install("qrcode")

    class FakeGroup:
        objects = None

    class FakeRole:
        objects = None

    class FakeMenu:
        objects = None

    _install("apps.system_mgmt.models",
             Group=FakeGroup, Role=FakeRole, User=object, Menu=FakeMenu,
             App=object, Channel=object, ChannelChoices=object, ErrorLog=object,
             OperationLog=object, UserRule=object, LoginModule=object, GroupDataRule=object)

    spec = importlib.util.spec_from_file_location("apps.system_mgmt.nats_api", base)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["apps.system_mgmt.nats_api"] = mod
    spec.loader.exec_module(mod)

    return mod, FakeGroup, FakeRole, FakeMenu, _FakeGroupUtils


# ---------------------------------------------------------------------------
# Test 1: _collect_ancestor_group_ids 沿 parent 链向上收集 ID
# ---------------------------------------------------------------------------

def test_collect_ancestor_group_ids_full_chain():
    """结构 1->2->3，seed=[3] 应返回 {1,2,3}。Revert 后 AttributeError。"""
    mod, FakeGroup, _, _, _ = _load_nats_api()

    rows = [(1, None, True), (2, 1, True), (3, 2, True)]

    class FakeQS:
        def values_list(self, *fields):
            return rows

    FakeGroup.objects = FakeQS()

    result = mod._collect_ancestor_group_ids([3])
    assert result == {1, 2, 3}


def test_collect_ancestor_group_ids_empty_seed():
    """空 seed 返回空集合。"""
    mod, FakeGroup, _, _, _ = _load_nats_api()
    result = mod._collect_ancestor_group_ids([])
    assert result == set()


def test_collect_ancestor_group_ids_no_infinite_loop_on_cycle():
    """数据存在环时不死循环。"""
    mod, FakeGroup, _, _, _ = _load_nats_api()

    rows = [(10, 11, True), (11, 10, True)]

    class FakeQS:
        def values_list(self, *fields):
            return rows

    FakeGroup.objects = FakeQS()
    result = mod._collect_ancestor_group_ids([10])
    assert {10, 11} == result


# ---------------------------------------------------------------------------
# Test 2: get_user_all_roles 使用 filter(id__in=ancestors) 而非 all()
# ---------------------------------------------------------------------------

def test_get_user_all_roles_uses_scoped_filter_not_all():
    """
    非超管用户：get_user_all_roles 必须调用 filter(id__in=<ancestors>)。
    Revert 修复后，filter_calls 为空（代码走 all()），断言失败。
    """
    mod, FakeGroup, _, _, _ = _load_nats_api()

    filter_calls = []

    class FakeObjects:
        def values_list(self, *fields):
            return [(1, None, True), (2, 1, True), (3, 2, True)]

        def prefetch_related(self, *a):
            return self

        def filter(self, **kwargs):
            filter_calls.append(kwargs)
            return self

        def all(self):
            return self

        def __iter__(self):
            return iter([])

    FakeGroup.objects = FakeObjects()

    user = types.SimpleNamespace(role_list=[], group_list=[3])
    mod.get_user_all_roles(user)

    assert any("id__in" in c for c in filter_calls), (
        "get_user_all_roles 未使用 id__in 过滤组（仍在全表扫描），修复未生效"
    )
    id_in = next(c["id__in"] for c in filter_calls if "id__in" in c)
    assert set(id_in) == {1, 2, 3}, (
        f"id__in 应为 {{1,2,3}}，实际为 {set(id_in)}"
    )


# ---------------------------------------------------------------------------
# Test 3: verify_token cache-miss 非超管路径不全表扫描
# ---------------------------------------------------------------------------

def test_verify_token_non_superuser_cache_miss_uses_scoped_group_query():
    """
    cache miss 时，非超管路径必须用 filter(id__in=...) 查询 Group。
    Revert 后 filter_calls 为空（用 all()），断言失败。
    """
    mod, FakeGroup, FakeRole, FakeMenu, _ = _load_nats_api()

    filter_calls = []

    class FakeGroupObjects:
        def values_list(self, *fields):
            return [(1, None, True), (2, 1, True)]

        def prefetch_related(self, *a):
            return self

        def filter(self, **kwargs):
            filter_calls.append(kwargs)
            return self

        def all(self):
            return self

        def order_by(self, *a):
            return self

        def __iter__(self):
            return iter([])

    FakeGroup.objects = FakeGroupObjects()

    class FakeRoleObjects:
        def filter(self, **kwargs):
            return self

        def __iter__(self):
            return iter([])

        def values_list(self, *a, **kw):
            return []

    FakeRole.objects = FakeRoleObjects()

    class FakeMenuObjects:
        def filter(self, **kwargs):
            return self

        def values_list(self, *a, **kw):
            return []

    FakeMenu.objects = FakeMenuObjects()

    # 替换 GroupUtils.build_group_tree
    class _BGT:
        @staticmethod
        def build_group_tree(groups, is_superuser=False, user_groups=None):
            return []

    mod.GroupUtils = _BGT

    user_obj = types.SimpleNamespace(
        id=1, username="alice", domain="domain.com",
        role_list=[], group_list=[2],
        display_name="Alice", email="a@b.com",
        locale="zh-CN", timezone="Asia/Shanghai",
    )
    mod._verify_token = lambda t: user_obj
    mod.get_cached_token_info = lambda *a: None
    mod.set_cached_token_info = lambda *a: None
    mod.get_user_all_roles = lambda u: []
    mod.cache = types.SimpleNamespace(get=lambda k: None, set=lambda *a, **kw: None)

    os.environ.setdefault("SECRET_KEY", "test-secret")
    mod.verify_token("fake-token")

    assert any("id__in" in c for c in filter_calls), (
        "verify_token cache-miss 非超管路径仍在全表扫描（未使用 id__in 过滤），修复未生效。"
        f"filter_calls={filter_calls}"
    )
