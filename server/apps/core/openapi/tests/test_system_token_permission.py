"""系统 Token 鉴权契约（T3）：钥匙名单、超管仍受名单约束、缓存不污染、锚点注入。"""

import pytest
from django.core.cache import cache

from apps.base.tests.factories import UserAPISecretFactory
from apps.core.backends import APISecretAuthBackend
from apps.core.openapi.registry import default_registry
from apps.core.openapi.testing import bearer
from apps.core.openapi.tests.test_system_token_auth import (
    _acting,
    _create_acting_user,
    _create_system_token,
)
from apps.system_mgmt.models import Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

CLASSIFICATIONS_URL = "/openapi/v1/cmdb/classifications"
INSTANCES_URL = "/openapi/v1/cmdb/instances"
CMDB_MODULE_URL = "/openapi/v1/cmdb/module-data"
PATCH_URL = "/openapi/v1/patch-mgmt/module-data"

VIEW_CLASSIFICATIONS = "model_management-View"
VIEW_INSTANCES = "asset_info-View"
SCOPE_ALL = {"mode": "all"}
SCOPE_CLASSIFICATIONS = {
    "mode": "allowlist",
    "endpoints": ["GET cmdb/classifications"],
}
SCOPE_BOTH = {
    "mode": "allowlist",
    "endpoints": ["GET cmdb/classifications", "GET cmdb/instances"],
}
SCOPE_INSTANCES = {
    "mode": "allowlist",
    "endpoints": ["GET cmdb/instances"],
}
SCOPE_MODULE = {
    "mode": "allowlist",
    "endpoints": ["GET cmdb/module-data"],
}


def _stub_endpoint(monkeypatch, service, sub_path, method, result):
    endpoint = default_registry.find(service, sub_path, method)
    assert endpoint is not None
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(endpoint, "func", fake)
    return endpoint, captured


def _grant_cmdb_menus(user, menu_names):
    menus = []
    for name in menu_names:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="cmdb",
            defaults={"display_name": name, "url": f"/{name}"},
        )
        menus.append(menu)
    role = Role.objects.create(
        name=f"cmdb-op-{user.username}",
        app="cmdb",
        menu_list=[menu.id for menu in menus],
    )
    SystemUser.objects.filter(username=user.username, domain=user.domain).update(
        role_list=[role.id],
    )


def _grant_admin_role(user):
    role, _ = Role.objects.get_or_create(name="admin", app="")
    SystemUser.objects.filter(username=user.username, domain=user.domain).update(
        role_list=[role.id],
    )


@pytest.fixture
def locmem_cache(settings):
    """DummyCache 无法观测写回；本用例改用 locmem 断言原始权限快照未被交集覆盖。"""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "t3-system-token-perm",
        }
    }
    from django.core.cache import caches

    caches.close_all()
    yield
    caches.close_all()


def _permission_cache(user, team_id):
    backend = APISecretAuthBackend()
    key = backend._get_permission_cache_key(user.username, user.domain, team_id)
    return cache.get(key)


@pytest.fixture
def stub_cmdb_catalog(monkeypatch):
    _stub_endpoint(monkeypatch, "cmdb", "classifications", "GET", [])
    _stub_endpoint(monkeypatch, "cmdb", "instances", "GET", {"count": 0, "inst_list": []})


@pytest.fixture
def captured_cmdb_module(monkeypatch):
    endpoint, captured = _stub_endpoint(
        monkeypatch, "cmdb", "module-data", "GET", {"count": 0, "items": []}
    )
    monkeypatch.setattr(endpoint, "permission", VIEW_INSTANCES)
    monkeypatch.setattr(endpoint, "permission_app", "cmdb")
    return captured


def test_system_token_scope_excludes_owned_permission(client, stub_cmdb_catalog):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS, VIEW_INSTANCES])
    token = _create_system_token(scope=SCOPE_CLASSIFICATIONS)

    allowed = client.get(CLASSIFICATIONS_URL, **_acting(token, user, 40))
    denied = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))

    assert allowed.status_code == 200, allowed.json()
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"
    assert denied.json()["message"] == "endpoint not in token scope"


def test_system_token_cannot_grant_unowned_permission(client, stub_cmdb_catalog):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS])
    token = _create_system_token(scope=SCOPE_BOTH)

    allowed = client.get(CLASSIFICATIONS_URL, **_acting(token, user, 40))
    denied = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))

    assert allowed.status_code == 200, allowed.json()
    assert denied.status_code == 403
    assert denied.json()["code"] == "PERM_MISSING"
    assert denied.json()["message"] == "permission denied"


def test_allowlist_denied_before_user_permission(client, stub_cmdb_catalog):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS])
    token = _create_system_token(scope=SCOPE_CLASSIFICATIONS)

    denied = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"
    assert denied.json()["message"] == "endpoint not in token scope"


def test_system_token_superuser_uses_scope_not_bypass(client, stub_cmdb_catalog):
    user = _create_acting_user(40)
    _grant_admin_role(user)
    token = _create_system_token(scope=SCOPE_CLASSIFICATIONS)

    allowed = client.get(CLASSIFICATIONS_URL, **_acting(token, user, 40))
    denied = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))

    assert allowed.status_code == 200, allowed.json()
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"
    assert denied.json()["message"] == "endpoint not in token scope"


def test_system_token_cached_superuser_snapshot_does_not_bypass(
    client, stub_cmdb_catalog, locmem_cache
):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS])
    token = _create_system_token(scope=SCOPE_CLASSIFICATIONS)
    backend = APISecretAuthBackend()
    cache.set(
        backend._get_permission_cache_key(user.username, user.domain, 40),
        {
            "roles": ["admin"],
            "permission": {},
            "is_superuser": True,
            "role_ids": [],
            "group_list": user.group_list,
        },
    )

    allowed = client.get(CLASSIFICATIONS_URL, **_acting(token, user, 40))
    denied = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))
    no_perm = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 40},
        **_acting(token, user, 40),
    )

    assert allowed.status_code == 200, allowed.json()
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"
    assert denied.json()["message"] == "endpoint not in token scope"
    assert no_perm.status_code == 403
    assert no_perm.json()["code"] == "SCOPE_DENIED"
    assert no_perm.json()["message"] == "endpoint not in token scope"


def test_system_token_permission_version_bump_refreshes_effective_perms(
    client, stub_cmdb_catalog, locmem_cache
):
    from apps.core.utils.permission_cache import _advance_user_permission_versions

    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS, VIEW_INSTANCES])
    token = _create_system_token(scope=SCOPE_BOTH)

    before = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))
    assert before.status_code == 200, before.json()

    sys_user = SystemUser.objects.get(username=user.username, domain=user.domain)
    role = Role.objects.get(id=sys_user.role_list[0])
    menu = Menu.objects.get(name=VIEW_CLASSIFICATIONS, app="cmdb")
    role.menu_list = [menu.id]
    role.save(update_fields=["menu_list"])
    _advance_user_permission_versions(
        [{"username": user.username, "domain": user.domain}]
    )

    after = client.get(INSTANCES_URL, {"model_id": "host"}, **_acting(token, user, 40))
    still_allowed = client.get(CLASSIFICATIONS_URL, **_acting(token, user, 40))
    assert after.status_code == 403
    assert after.json()["code"] == "PERM_MISSING"
    assert after.json()["message"] == "permission denied"
    assert still_allowed.status_code == 200, still_allowed.json()


def test_system_token_does_not_pollute_permission_cache(client, stub_cmdb_catalog, locmem_cache):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS, VIEW_INSTANCES])
    personal = UserAPISecretFactory(
        username=user.username, domain=user.domain, team=40
    ).api_secret
    token = _create_system_token(scope=SCOPE_CLASSIFICATIONS)

    scoped = client.get(CLASSIFICATIONS_URL, **_acting(token, user, 40))
    assert scoped.status_code == 200, scoped.json()

    cached = _permission_cache(user, 40)
    assert cached is not None
    assert VIEW_CLASSIFICATIONS in cached["permission"].get("cmdb", [])
    assert VIEW_INSTANCES in cached["permission"].get("cmdb", [])

    personal_instances = client.get(
        INSTANCES_URL, {"model_id": "host"}, **bearer(personal)
    )
    assert personal_instances.status_code == 200, personal_instances.json()


def test_system_token_allowlist_blocks_undeclared_permission_endpoint(client):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_INSTANCES])
    token = _create_system_token(scope=SCOPE_INSTANCES)

    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 40},
        **_acting(token, user, 40),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "SCOPE_DENIED"
    assert resp.json()["message"] == "endpoint not in token scope"


def test_system_token_all_allows_undeclared_permission_endpoint(client):
    user = _create_acting_user(40)
    token = _create_system_token(scope=SCOPE_ALL)

    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 40},
        **_acting(token, user, 40),
    )
    assert resp.status_code == 200, resp.json()


def test_me_and_docs_ignore_allowlist(client):
    user = _create_acting_user(40)
    token = _create_system_token(scope=SCOPE_CLASSIFICATIONS)

    me = client.get("/openapi/v1/_me", **_acting(token, user, 40))
    docs = client.get("/openapi/v1/_docs", **_acting(token, user, 40))

    assert me.status_code == 200, me.json()
    assert docs.status_code == 200, docs.json()


def test_system_token_user_info_anchor_forced_to_acting_team(client, captured_cmdb_module):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_INSTANCES])
    token = _create_system_token(scope=SCOPE_MODULE)

    resp = client.get(
        CMDB_MODULE_URL,
        {"module": "instances", "child_module": "host", "group_id": 40, "team": "999"},
        **_acting(token, user, 40),
    )
    assert resp.status_code == 200, resp.json()
    assert captured_cmdb_module["user_info"]["user"] == user.username
    assert captured_cmdb_module["user_info"]["team"] == 40
    assert "team" not in captured_cmdb_module


def _personal_secret(user, team_id, **kwargs):
    from apps.base.models.user import UserAPISecret

    raw = UserAPISecret.generate_api_secret()
    UserAPISecretFactory(
        username=user.username,
        domain=user.domain,
        team=team_id,
        api_secret=UserAPISecret.hash_api_secret(raw),
        **kwargs,
    )
    return raw


def test_personal_token_scope_excludes_owned_permission(client, stub_cmdb_catalog):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_CLASSIFICATIONS, VIEW_INSTANCES])
    token = _personal_secret(user, 40, scope=SCOPE_CLASSIFICATIONS)

    allowed = client.get(CLASSIFICATIONS_URL, **bearer(token))
    denied = client.get(INSTANCES_URL, {"model_id": "host"}, **bearer(token))

    assert allowed.status_code == 200, allowed.json()
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"
    assert denied.json()["message"] == "endpoint not in token scope"


def test_personal_token_empty_scope_allows_no_permission_endpoint(client):
    user = _create_acting_user(40)
    token = _personal_secret(user, 40, scope=None)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 40},
        **bearer(token),
    )
    assert resp.status_code == 200, resp.json()


def test_personal_token_nonempty_scope_no_permission_endpoint_403(client):
    user = _create_acting_user(40)
    _grant_cmdb_menus(user, [VIEW_INSTANCES])
    token = _personal_secret(user, 40, scope=SCOPE_INSTANCES)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 40},
        **bearer(token),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "SCOPE_DENIED"
    assert resp.json()["message"] == "endpoint not in token scope"
