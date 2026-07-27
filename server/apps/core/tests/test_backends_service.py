import pydantic.root_model  # noqa
import pytest
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.db import transaction

from apps.base.models import User as BaseUser
from apps.base.models import UserAPISecret
from apps.core import backends as be
from apps.core.backends import APISecretAuthBackend, AuthBackend, _collect_ancestor_group_ids
from apps.core.constants import VERIFY_TOKEN_USER_NOT_FOUND_CODE, VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE
from apps.core.utils import permission_cache
from apps.core.utils.custom_error import DoesNotExist
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SysUser

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class _Req:
    def __init__(self, path="/api/v1/cmdb/instances/", cookies=None, resolver_match=None):
        self.path = path
        self.COOKIES = cookies or {}
        self.resolver_match = resolver_match


class TestCollectAncestorGroupIds:
    def test_empty(self):
        assert _collect_ancestor_group_ids([]) == set()

    def test_walks_parent_chain(self):
        g1 = Group.objects.create(name="root", parent_id=0, allow_inherit_roles=True)
        g2 = Group.objects.create(name="child", parent_id=g1.id, allow_inherit_roles=True)
        g3 = Group.objects.create(name="leaf", parent_id=g2.id, allow_inherit_roles=True)
        result = _collect_ancestor_group_ids([g3.id])
        assert result == {g1.id, g2.id, g3.id}


class TestAPISecretAuthBackend:
    def test_no_token_returns_none(self):
        assert APISecretAuthBackend().authenticate(api_token=None) is None

    def test_unknown_token_returns_none(self):
        assert APISecretAuthBackend().authenticate(api_token="nope") is None

    def test_token_for_missing_system_user_is_rejected(self):
        BaseUser.objects.create(username="deleted-user", domain="domain.com")
        UserAPISecret.objects.create(
            username="deleted-user",
            domain="domain.com",
            api_secret="deleted-secret",
            team=1,
        )

        assert APISecretAuthBackend().authenticate(api_token="deleted-secret") is None

    def test_valid_token_populates_permissions(self):
        BaseUser.objects.create(username="apiuser", domain="domain.com")
        UserAPISecret.objects.create(username="apiuser", domain="domain.com", api_secret="sec123", team=5)
        role = Role.objects.create(name="admin", app="")
        sys_user = SysUser.objects.create(username="apiuser", domain="domain.com", role_list=[role.id], email="a@x.com")
        assert sys_user.pk

        user = APISecretAuthBackend().authenticate(api_token="sec123")
        assert user is not None
        assert user.group_list == [5]
        assert user.is_superuser is True  # admin 角色
        assert "admin" in user.roles

    def test_non_superuser_collects_menu_permissions(self):
        BaseUser.objects.create(username="puser", domain="domain.com")
        UserAPISecret.objects.create(username="puser", domain="domain.com", api_secret="psec", team=1)
        menu = Menu.objects.create(name="view_x", display_name="X", url="/x", app="cmdb")
        role = Role.objects.create(name="viewer", app="cmdb", menu_list=[menu.id])
        SysUser.objects.create(username="puser", domain="domain.com", role_list=[role.id], email="p@x.com")

        user = APISecretAuthBackend().authenticate(api_token="psec")
        assert user.is_superuser is False
        assert "view_x" in user.permission.get("cmdb", set())

    def test_permission_cache_hit(self, mocker):
        BaseUser.objects.create(username="cuser", domain="domain.com")
        SysUser.objects.create(username="cuser", domain="domain.com", email="c@x.com")
        secret = UserAPISecret.objects.create(username="cuser", domain="domain.com", api_secret="csec", team=2)
        backend = APISecretAuthBackend()
        # 直接 mock 缓存边界返回命中值，验证命中分支不再查 DB 角色
        mocker.patch.object(
            be.cache,
            "get",
            return_value={"roles": ["r1"], "permission": {"app": ["m1"]}, "is_superuser": True, "role_ids": [9]},
        )

        user = backend.authenticate(api_token="csec")
        assert user.roles == ["r1"]
        assert user.is_superuser is True
        assert user.permission == {"app": {"m1"}}
        assert user.role_ids == [9]
        assert secret.team == 2

    def test_next_auth_after_revocation_ignores_other_worker_snapshot(self, mocker):
        BaseUser.objects.create(username="revoked-user", domain="domain.com")
        UserAPISecret.objects.create(
            username="revoked-user",
            domain="domain.com",
            api_secret="revoked-secret",
            team=2,
        )
        admin_role = Role.objects.create(name="admin", app="")
        sys_user = SysUser.objects.create(
            username="revoked-user",
            domain="domain.com",
            role_list=[admin_role.id],
            email="revoked@example.com",
        )
        backend = APISecretAuthBackend()
        worker_a_cache = LocMemCache("api-secret-worker-a", {})
        worker_b_cache = LocMemCache("api-secret-worker-b", {})
        mocker.patch.object(be, "cache", worker_a_cache)

        first_auth = backend.authenticate(api_token="revoked-secret")
        old_cache_key = backend._get_permission_cache_key("revoked-user", "domain.com", 2)
        assert first_auth.is_superuser is True
        assert worker_a_cache.get(old_cache_key)["is_superuser"] is True

        mocker.patch.object(permission_cache, "cache", worker_b_cache)
        with transaction.atomic():
            SysUser.objects.filter(pk=sys_user.pk).update(role_list=[])
            permission_cache.clear_user_permission_cache("revoked-user", "domain.com")

        second_auth = backend.authenticate(api_token="revoked-secret")
        assert worker_a_cache.get(old_cache_key)["is_superuser"] is True
        assert second_auth is not None
        assert second_auth.is_superuser is False
        assert second_auth.roles == []

    def test_permission_version_survives_user_delete_and_recreate(self):
        user = SysUser.objects.create(
            username="recreated-user",
            domain="domain.com",
            email="recreated@example.com",
        )
        first_version = permission_cache.get_user_permission_version(user.username, user.domain)

        with transaction.atomic():
            user.delete()
            permission_cache.clear_user_permission_cache("recreated-user", "domain.com")
        deleted_version = permission_cache.get_user_permission_version("recreated-user", "domain.com")

        recreated = SysUser.objects.create(
            username="recreated-user",
            domain="domain.com",
            email="recreated-again@example.com",
        )
        recreated_version = permission_cache.get_user_permission_version(
            recreated.username,
            recreated.domain,
        )

        assert deleted_version > first_version
        assert recreated_version > deleted_version

    def test_stale_user_instance_cannot_move_permission_version_backwards(self):
        user = SysUser.objects.create(
            username="concurrent-save-user",
            domain="domain.com",
            email="concurrent@example.com",
        )
        first_copy = SysUser.objects.get(pk=user.pk)
        second_copy = SysUser.objects.get(pk=user.pk)
        initial_version = permission_cache.get_user_permission_version(user.username, user.domain)

        first_copy.display_name = "first"
        first_copy.save()
        first_version = permission_cache.get_user_permission_version(user.username, user.domain)
        second_copy.display_name = "second"
        second_copy.save()
        second_version = permission_cache.get_user_permission_version(user.username, user.domain)

        assert first_version > initial_version
        assert second_version > first_version

    def test_group_role_inheritance(self):
        BaseUser.objects.create(username="guser", domain="domain.com")
        # 父组允许继承、有角色；子组属于用户
        parent_role = Role.objects.create(name="parent_role", app="")
        child_role = Role.objects.create(name="child_role", app="")
        parent = Group.objects.create(name="P", parent_id=0, allow_inherit_roles=True)
        parent.roles.add(parent_role)
        child = Group.objects.create(name="C", parent_id=parent.id, allow_inherit_roles=True)
        child.roles.add(child_role)
        UserAPISecret.objects.create(username="guser", domain="domain.com", api_secret="gsec", team=child.id)
        SysUser.objects.create(username="guser", domain="domain.com", role_list=[], email="g@x.com")

        backend = APISecretAuthBackend()
        user = backend.authenticate(api_token="gsec")
        # 角色名包含子组与父组(因父允许继承)的角色
        assert "child_role" in user.roles
        assert "parent_role" in user.roles


class TestAuthBackendVerifyToken:
    def test_no_token_returns_none(self):
        assert AuthBackend().authenticate(token=None) is None

    def test_invalid_result_type_returns_none(self, mocker):
        client = mocker.MagicMock()
        client.verify_token.return_value = "not-a-dict"
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        assert AuthBackend().authenticate(request=_Req(), token="t") is None

    def test_user_not_found_raises_does_not_exist(self, mocker):
        client = mocker.MagicMock()
        client.verify_token.return_value = {
            "result": False,
            "error_code": VERIFY_TOKEN_USER_NOT_FOUND_CODE,
            "message": "x",
        }
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        with pytest.raises(DoesNotExist):
            AuthBackend().authenticate(request=_Req(), token="t")

    def test_user_not_found_by_message(self, mocker):
        client = mocker.MagicMock()
        client.verify_token.return_value = {
            "result": False,
            "message": VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE,
        }
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        with pytest.raises(DoesNotExist):
            AuthBackend().authenticate(request=_Req(), token="t")

    def test_result_false_other_returns_none(self, mocker):
        client = mocker.MagicMock()
        client.verify_token.return_value = {"result": False, "message": "bad token"}
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        assert AuthBackend().authenticate(request=_Req(), token="t") is None

    def test_empty_user_info_returns_none(self, mocker):
        client = mocker.MagicMock()
        client.verify_token.return_value = {"result": True, "data": None}
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        assert AuthBackend().authenticate(request=_Req(), token="t") is None

    def test_success_creates_user(self, mocker):
        client = mocker.MagicMock()
        client.verify_token.return_value = {
            "result": True,
            "data": {
                "username": "tok_user",
                "domain": "domain.com",
                "email": "t@x.com",
                "is_superuser": True,
                "roles": ["admin"],
                "group_list": [{"id": 1}],
                "locale": "zh-CN",
            },
        }
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        req = _Req(cookies={})  # 无 current_team -> rules 为空
        user = AuthBackend().authenticate(request=req, token="t")
        assert user is not None
        assert user.username == "tok_user"
        assert user.is_superuser is True
        assert user.rules == {}
        assert BaseUser.objects.filter(username="tok_user").exists()


class TestHandleUserLocale:
    def test_chinese_locale_mapping(self):
        info = {"locale": "zh-CN"}
        AuthBackend()._handle_user_locale(info)
        assert info["locale"] == "zh-Hans"

    def test_invalid_timezone_ignored(self):
        # 不抛异常即可
        AuthBackend()._handle_user_locale({"locale": "en", "timezone": "Not/AZone"})

    def test_no_locale_noop(self):
        AuthBackend()._handle_user_locale({})


class TestGetUserRules:
    def test_no_request_returns_empty(self):
        assert AuthBackend()._get_user_rules(None, {"username": "u"}) == {}

    def test_no_current_group_returns_empty(self):
        assert AuthBackend()._get_user_rules(_Req(cookies={}), {"username": "u"}) == {}

    def test_fetches_rules(self, mocker):
        client = mocker.MagicMock()
        client.get_user_rules.return_value = {"team": [1]}
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        req = _Req(cookies={"current_team": "3"})
        assert AuthBackend()._get_user_rules(req, {"username": "u"}) == {"team": [1]}

    def test_non_dict_rules_returns_empty(self, mocker):
        client = mocker.MagicMock()
        client.get_user_rules.return_value = "oops"
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        req = _Req(cookies={"current_team": "3"})
        assert AuthBackend()._get_user_rules(req, {"username": "u"}) == {}

    def test_exception_returns_empty(self, mocker):
        client = mocker.MagicMock()
        client.get_user_rules.side_effect = RuntimeError("rpc")
        mocker.patch.object(be, "SystemMgmt", return_value=client)
        req = _Req(cookies={"current_team": "3"})
        assert AuthBackend()._get_user_rules(req, {"username": "u"}) == {}


class TestExtractAppNameAndSuperuser:
    def test_extract_from_path(self):
        assert AuthBackend._extract_app_name_from_request(_Req(path="/api/v1/monitor/x/")) == "monitor"

    def test_extract_from_resolver_route(self, mocker):
        rm = mocker.MagicMock()
        rm.route = "api/v1/cmdb/instances/"
        req = _Req(path="/wrong/", resolver_match=rm)
        assert AuthBackend._extract_app_name_from_request(req) == "cmdb"

    def test_extract_no_match_returns_empty(self):
        assert AuthBackend._extract_app_name_from_request(_Req(path="/health/")) == ""

    def test_superuser_flag_short_circuits(self):
        assert AuthBackend.get_is_superuser(_Req(), {"is_superuser": True}) is True

    def test_app_admin_role_grants_superuser(self):
        req = _Req(path="/api/v1/system_mgmt/x/")
        info = {"is_superuser": False, "roles": ["system-manager--admin"]}
        assert AuthBackend.get_is_superuser(req, info) is True

    def test_no_app_admin_role(self):
        req = _Req(path="/api/v1/cmdb/x/")
        info = {"is_superuser": False, "roles": ["cmdb--viewer"]}
        assert AuthBackend.get_is_superuser(req, info) is False

    def test_no_app_name_returns_false(self):
        req = _Req(path="/health/")
        assert AuthBackend.get_is_superuser(req, {"is_superuser": False, "roles": []}) is False


class TestSetUserInfo:
    def test_no_username_returns_none(self):
        assert AuthBackend().set_user_info(_Req(), {}, {}) is None

    def test_creates_and_sets_runtime_attrs(self):
        info = {
            "username": "newu",
            "domain": "domain.com",
            "email": "n@x.com",
            "is_superuser": False,
            "roles": ["r"],
            "group_list": [{"id": 1}],
            "locale": "en",
            "permission": {"app": ["m1", "m2"]},
            "role_ids": [3],
            "display_name": "New U",
        }
        user = AuthBackend().set_user_info(_Req(path="/health/"), info, {"k": "v"})
        assert user.email == "n@x.com"
        assert user.rules == {"k": "v"}
        assert user.permission == {"app": {"m1", "m2"}}
        assert user.role_ids == [3]
        assert user.display_name == "New U"

    def test_update_only_changed_fields(self):
        BaseUser.objects.create(username="existing", domain="domain.com", email="old@x.com", is_active=True)
        info = {"username": "existing", "domain": "domain.com", "email": "new@x.com", "locale": "en"}
        user = AuthBackend().set_user_info(_Req(path="/health/"), info, {})
        user.refresh_from_db()
        assert user.email == "new@x.com"
