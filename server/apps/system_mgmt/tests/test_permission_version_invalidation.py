from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import transaction
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.core.utils.permission_cache import clear_user_permission_cache, get_user_permission_version
from apps.system_mgmt.models import Group, GroupDataRule, LoginModule, Role, User, UserRule
from apps.system_mgmt.nats.permissions import delete_rules
from apps.system_mgmt.viewset.login_module_viewset import LoginModuleViewSet

pytestmark = pytest.mark.django_db


def _create_opspilot_guest_rules(group):
    return [
        GroupDataRule.objects.create(name=name, app=app, group_id=group.id, group_name=group.name)
        for name, app in [
            ("OpsPilot内置规则", "opspilot"),
            ("OpsPilotGuest数据权限", "monitor"),
            ("游客数据权限", "cmdb"),
            ("log内置规则", "log"),
            ("节点管理内置数据权限", "node"),
        ]
    ]


def test_wechat_rule_initialization_runs_inside_registration_transaction(monkeypatch):
    from apps.system_mgmt.nats import wechat

    group = Group.objects.create(name="OpsPilotGuest", parent_id=0)
    observed = []
    monkeypatch.setattr(
        wechat,
        "set_opspilot_guest_group_default_rule",
        lambda default_group, user: observed.append(transaction.get_connection().in_atomic_block),
    )
    monkeypatch.setattr(wechat, "_build_jwt_payload", lambda user_id: {})
    monkeypatch.setattr(wechat.jwt, "encode", lambda **kwargs: "token")

    result = wechat.wechat_user_register("wechat-user", "WeChat user")

    assert result["result"] is True
    assert observed == [True]
    assert User.objects.get(username="wechat-user").group_list == [group.id]


def test_opspilot_guest_rules_keep_user_domain():
    from apps.system_mgmt.nats.users import set_opspilot_guest_group_default_rule

    group = Group.objects.create(name="OpsPilotGuest", parent_id=0)
    rules = _create_opspilot_guest_rules(group)
    user = User.objects.create(
        username="cross-domain-guest",
        domain="corp.example",
        display_name="Cross domain guest",
        email="guest@example.com",
        password="",
    )

    set_opspilot_guest_group_default_rule(group, user)

    assert set(
        UserRule.objects.filter(username=user.username).values_list("domain", "group_rule_id"),
    ) == {(user.domain, rule.id) for rule in rules}


def test_login_module_destroy_advances_deleted_domain_and_group_user_versions():
    login_module = LoginModule.objects.create(
        name="bk-lite-source",
        source_type="bk_lite",
        other_config={"domain": "source.example", "root_group": "Source Root"},
    )
    group = Group.objects.create(name="Source Root", parent_id=0, description="source-tree")
    domain_user = User.objects.create(
        username="source-user",
        display_name="Source user",
        email="source@example.com",
        password="",
        domain="source.example",
    )
    grouped_user = User.objects.create(
        username="grouped-user",
        display_name="Grouped user",
        email="grouped@example.com",
        password="",
        domain="domain.com",
        group_list=[group.id],
    )
    domain_version = get_user_permission_version(domain_user.username, domain_user.domain)
    grouped_version = get_user_permission_version(grouped_user.username, grouped_user.domain)

    viewset = LoginModuleViewSet()
    viewset.get_object = lambda: login_module
    request = SimpleNamespace(
        user=SimpleNamespace(
            username="admin",
            is_superuser=True,
            is_authenticated=True,
            permission={},
        ),
        META={},
    )
    with patch("apps.system_mgmt.viewset.login_module_viewset.log_operation"):
        response = viewset.destroy(request)

    assert response.status_code == 204
    assert get_user_permission_version(domain_user.username, domain_user.domain) > domain_version
    assert get_user_permission_version(grouped_user.username, grouped_user.domain) > grouped_version


def test_group_data_rule_update_and_delete_advance_bound_user_version():
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="rule-admin", password="pw", domain="domain.com")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    client.cookies["current_team"] = "1"

    user = User.objects.create(
        username="rule-user",
        display_name="Rule user",
        email="rule-user@example.com",
        password="",
    )
    rule = GroupDataRule.objects.create(
        name="rule",
        app="cmdb",
        group_id=1,
        group_name="Default",
        rules={"host": [{"id": 1}]},
    )
    UserRule.objects.create(username=user.username, domain=user.domain, group_rule=rule)
    initial_version = get_user_permission_version(user.username, user.domain)

    with patch("apps.system_mgmt.viewset.group_data_rule_viewset.log_operation"):
        response = client.put(
            f"/api/v1/system_mgmt/group_data_rule/{rule.id}/",
            {
                "name": "updated-rule",
                "app": "cmdb",
                "group_id": 1,
                "group_name": "Default",
                "rules": {"host": []},
            },
            format="json",
        )

    assert response.status_code == 200
    updated_version = get_user_permission_version(user.username, user.domain)
    assert updated_version > initial_version

    with patch("apps.system_mgmt.viewset.group_data_rule_viewset.log_operation"):
        response = client.delete(f"/api/v1/system_mgmt/group_data_rule/{rule.id}/")

    assert response.status_code in {200, 204}
    assert get_user_permission_version(user.username, user.domain) > updated_version


def test_nats_delete_rules_advances_bound_user_version():
    user = User.objects.create(
        username="nats-rule-user",
        display_name="NATS rule user",
        email="nats-rule-user@example.com",
        password="",
    )
    rule = GroupDataRule.objects.create(
        name="nats-rule",
        app="cmdb",
        group_id=1,
        group_name="Default",
        rules={"host": [{"id": 1}]},
    )
    UserRule.objects.create(username=user.username, domain=user.domain, group_rule=rule)
    initial_version = get_user_permission_version(user.username, user.domain)

    result = delete_rules([1], 1, "cmdb", "host", None)

    assert result["result"] is True
    assert get_user_permission_version(user.username, user.domain) > initial_version


def test_verify_token_reloads_user_after_permission_version_is_read():
    from apps.system_mgmt.nats import auth

    user = User.objects.create(
        username="stale-token-user",
        display_name="Stale token user",
        email="stale-token-user@example.com",
        password="",
        role_list=[101],
    )
    stale_user = User.objects.get(id=user.id)
    User.objects.filter(id=user.id).update(role_list=[])
    clear_user_permission_cache(user.username, user.domain)

    with (
        patch.object(auth, "_verify_token", return_value=stale_user),
        patch.object(auth, "get_cached_token_info", return_value=None),
        patch.object(auth, "set_cached_token_info", return_value=True),
        patch.object(
            auth,
            "build_user_authorization_context",
            side_effect=lambda current_user: {"role_list": current_user.role_list},
        ),
    ):
        result = auth.verify_token("token")

    assert result == {"result": True, "data": {"role_list": []}}


def test_update_user_only_replaces_rules_for_target_domain():
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    Role.objects.get_or_create(name="admin", app="")
    role = Role.objects.create(name="domain-rule-editor", app="")
    group = Group.objects.create(name="domain-rule-group", parent_id=0)
    target = User.objects.create(
        username="same-name",
        domain="corp.example",
        display_name="Corp user",
        email="corp-user@example.com",
        password="",
        group_list=[group.id],
        role_list=[role.id],
    )
    User.objects.create(
        username=target.username,
        domain="domain.com",
        display_name="Default-domain user",
        email="default-user@example.com",
        password="",
    )
    old_target_rule = GroupDataRule.objects.create(
        name="old-target-rule",
        app="cmdb",
        group_id=group.id,
        group_name=group.name,
        rules={},
    )
    new_target_rule = GroupDataRule.objects.create(
        name="new-target-rule",
        app="cmdb",
        group_id=group.id,
        group_name=group.name,
        rules={},
    )
    other_domain_rule = GroupDataRule.objects.create(
        name="other-domain-rule",
        app="cmdb",
        group_id=group.id,
        group_name=group.name,
        rules={},
    )
    UserRule.objects.create(
        username=target.username,
        domain=target.domain,
        group_rule=old_target_rule,
    )
    UserRule.objects.create(
        username=target.username,
        domain="domain.com",
        group_rule=other_domain_rule,
    )

    request = APIRequestFactory().post(
        "/system_mgmt/api/user/update_user/",
        {
            "user_id": target.id,
            "username": target.username,
            "lastName": target.display_name,
            "email": target.email,
            "phone": None,
            "locale": target.locale,
            "timezone": target.timezone,
            "groups": [group.id],
            "roles": [role.id],
            "rules": [new_target_rule.id],
            "is_superuser": False,
        },
        format="json",
    )
    force_authenticate(
        request,
        user=SimpleNamespace(
            username="admin",
            domain="domain.com",
            locale="en",
            is_superuser=True,
            is_authenticated=True,
            permission={"system-manager": {"user_group-Edit User"}},
        ),
    )
    view = UserViewSet.as_view({"post": "update_user"})
    with (
        patch("apps.system_mgmt.viewset.user_viewset.CMDB"),
        patch("apps.system_mgmt.viewset.user_viewset.log_operation"),
    ):
        response = view(request)

    assert response.status_code == 200
    assert list(
        UserRule.objects.filter(
            username=target.username,
            domain=target.domain,
        ).values_list("group_rule_id", flat=True)
    ) == [new_target_rule.id]
    assert UserRule.objects.filter(
        username=target.username,
        domain="domain.com",
        group_rule=other_domain_rule,
    ).exists()


def test_group_data_rule_update_rolls_back_when_version_advance_fails():
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="rollback-admin", password="pw", domain="domain.com")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    client.cookies["current_team"] = "1"
    user = User.objects.create(
        username="rollback-rule-user",
        display_name="Rollback rule user",
        email="rollback-rule-user@example.com",
        password="",
    )
    rule = GroupDataRule.objects.create(
        name="rollback-rule",
        app="cmdb",
        group_id=1,
        group_name="Default",
        rules={"host": [{"id": 1}]},
    )
    UserRule.objects.create(username=user.username, domain=user.domain, group_rule=rule)

    with patch(
        "apps.core.utils.permission_cache._advance_user_permission_versions",
        side_effect=RuntimeError("version update failed"),
    ):
        response = client.put(
            f"/api/v1/system_mgmt/group_data_rule/{rule.id}/",
            {
                "name": "must-rollback",
                "app": "cmdb",
                "group_id": 1,
                "group_name": "Default",
                "rules": {"host": []},
            },
            format="json",
        )

    assert response.status_code == 500
    rule.refresh_from_db()
    assert rule.name == "rollback-rule"
    assert rule.rules == {"host": [{"id": 1}]}
