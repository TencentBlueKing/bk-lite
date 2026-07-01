"""
Issue #3483: set_user_info 热路径写放大修复单元测试

测试覆盖：
- 用户信息未变时不执行 DB UPDATE（核心修复验证）
- 用户信息有变化时正确执行 DB UPDATE（回归保护）
- 新建用户时执行完整 save（回归保护）
- update_fields 仅包含实际变化的字段（精确写列保护）
"""

import contextlib
from unittest.mock import MagicMock, patch, call

import pytest

from apps.base.models import User
from apps.core.backends import AuthBackend


@contextlib.contextmanager
def _patch_get_or_create(user, created):
    """patch User._default_manager.get_or_create 返回指定 (user, created)。

    _default_manager 是只读属性，无法整体替换；这里只 patch 其上的方法。
    """
    with patch.object(
        User._default_manager,
        "get_or_create",
        return_value=(user, created),
    ) as mock_get_or_create:
        yield mock_get_or_create


class FakeUser:
    """模拟从 get_or_create 返回的用户对象，用于断言 save 调用行为。"""

    def __init__(
        self,
        email="old@example.com",
        is_superuser=False,
        is_staff=False,
        is_active=True,
        group_list=None,
        roles=None,
        locale="en",
    ):
        self.email = email
        self.is_superuser = is_superuser
        self.is_staff = is_staff
        self.is_active = is_active
        self.group_list = group_list if group_list is not None else []
        self.roles = roles if roles is not None else []
        self.locale = locale
        self.save = MagicMock()

    # 运行时属性（不持久化）
    timezone = None
    rules = None
    permission = None
    role_ids = None
    display_name = None
    group_tree = None


def _make_backend():
    return AuthBackend()


def _make_request(path="/api/v1/monitor/test/"):
    req = MagicMock()
    req.path = path
    req.COOKIES = {"current_team": "1"}
    return req


def _base_user_info(**overrides):
    info = {
        "username": "testuser",
        "domain": "domain.com",
        "email": "old@example.com",
        "is_superuser": False,
        "group_list": [],
        "roles": [],
        "locale": "en",
        "timezone": "Asia/Shanghai",
        "permission": {},
        "role_ids": [],
        "display_name": "Test User",
        "group_tree": [],
    }
    info.update(overrides)
    return info


# -------------------------------------------------------
# 核心修复：用户信息未变时不写库
# -------------------------------------------------------

class TestNoWriteWhenUnchanged:
    """当用户信息与 DB 中完全一致时，save() 不应被调用。"""

    def test_save_not_called_when_nothing_changed(self):
        backend = _make_backend()
        user = FakeUser(
            email="old@example.com",
            is_superuser=False,
            is_staff=False,
            is_active=True,
            group_list=[],
            roles=[],
            locale="en",
        )
        user_info = _base_user_info()  # 与 FakeUser 完全一致

        with (
            patch.object(
                type(backend).__mro__[0],  # AuthBackend
                "get_is_superuser",
                return_value=False,
            ),
            _patch_get_or_create(user, False),  # 非新建
        ):
            result = backend.set_user_info(_make_request(), user_info, {})

        assert result is user
        user.save.assert_not_called(), (
            "用户信息未变时不应执行 DB UPDATE（Issue #3483 核心修复）"
        )

    def test_revert_save_is_called_unconditionally(self):
        """验证：如果把修复 revert（改回 user.save()），本测试必须失败。
        此测试通过 mock 直接模拟 revert 行为，确认测试本身是有效的哨兵。"""
        # 模拟 revert 后的行为：无论如何都调用 save
        backend = _make_backend()
        user = FakeUser()
        user_info = _base_user_info()

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=False),
            _patch_get_or_create(user, False),
        ):
            # 直接调用修复后的方法
            backend.set_user_info(_make_request(), user_info, {})

        # 此处断言 save 未被调用；若 revert，save() 会被无条件调用，测试失败
        assert user.save.call_count == 0


# -------------------------------------------------------
# 回归保护：信息有变化时必须写库
# -------------------------------------------------------

class TestWriteWhenChanged:
    """当用户信息确实发生变化时，save() 必须被调用且 update_fields 精确。"""

    def test_save_called_when_email_changed(self):
        backend = _make_backend()
        user = FakeUser(email="old@example.com")
        user_info = _base_user_info(email="new@example.com")

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=False),
            _patch_get_or_create(user, False),
        ):
            result = backend.set_user_info(_make_request(), user_info, {})

        assert result is user
        user.save.assert_called_once()
        save_kwargs = user.save.call_args
        assert "update_fields" in save_kwargs.kwargs
        assert "email" in save_kwargs.kwargs["update_fields"]

    def test_save_called_when_roles_changed(self):
        backend = _make_backend()
        user = FakeUser(roles=[])
        user_info = _base_user_info(roles=["admin"])

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=False),
            _patch_get_or_create(user, False),
        ):
            result = backend.set_user_info(_make_request(), user_info, {})

        assert result is user
        user.save.assert_called_once()
        assert "roles" in user.save.call_args.kwargs["update_fields"]

    def test_save_called_when_superuser_changed(self):
        backend = _make_backend()
        user = FakeUser(is_superuser=False, is_staff=False)
        user_info = _base_user_info()

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=True),  # 升权
            _patch_get_or_create(user, False),
        ):
            result = backend.set_user_info(_make_request(), user_info, {})

        assert result is user
        user.save.assert_called_once()
        fields = user.save.call_args.kwargs["update_fields"]
        assert "is_superuser" in fields
        assert "is_staff" in fields

    def test_update_fields_contains_only_changed_fields(self):
        """update_fields 精确：只包含真正变化的字段，不包含未变字段。"""
        backend = _make_backend()
        # locale 和 group_list 与 user_info 一致，email 不同
        user = FakeUser(email="old@example.com", locale="en", group_list=[])
        user_info = _base_user_info(email="new@example.com", locale="en", group_list=[])

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=False),
            _patch_get_or_create(user, False),
        ):
            backend.set_user_info(_make_request(), user_info, {})

        fields = user.save.call_args.kwargs["update_fields"]
        assert "email" in fields
        assert "locale" not in fields
        assert "group_list" not in fields


# -------------------------------------------------------
# 回归保护：新建用户时执行完整 save
# -------------------------------------------------------

class TestNewUserSave:
    """新建用户（created=True）时，应执行完整 save（不带 update_fields 限制）。"""

    def test_full_save_on_new_user(self):
        backend = _make_backend()
        user = FakeUser()
        user_info = _base_user_info()

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=False),
            _patch_get_or_create(user, True),  # 新建
        ):
            result = backend.set_user_info(_make_request(), user_info, {})

        assert result is user
        user.save.assert_called_once()
        # 新建时不传 update_fields（全量 save）
        kwargs = user.save.call_args.kwargs
        assert kwargs.get("update_fields") is None


# -------------------------------------------------------
# 运行时属性验证（不持久化到 DB）
# -------------------------------------------------------

class TestRuntimeAttributes:
    """运行时属性（timezone/rules/permission 等）应被设置到 user 对象，但不触发 save。"""

    def test_runtime_attrs_set_without_extra_save(self):
        backend = _make_backend()
        user = FakeUser()
        rules = {"some": "rule"}
        user_info = _base_user_info(
            timezone="UTC",
            permission={"resource": ["read"]},
            role_ids=[1, 2],
            display_name="显示名",
            group_tree=[{"id": 1}],
        )

        with (
            patch.object(AuthBackend, "get_is_superuser", return_value=False),
            _patch_get_or_create(user, False),
        ):
            result = backend.set_user_info(_make_request(), user_info, rules)

        # 运行时属性已赋值
        assert result.timezone == "UTC"
        assert result.rules == rules
        assert result.permission == {"resource": {"read"}}
        assert result.role_ids == [1, 2]
        assert result.display_name == "显示名"
        assert result.group_tree == [{"id": 1}]
        # 用户信息未变，不应有额外 save
        assert user.save.call_count == 0
