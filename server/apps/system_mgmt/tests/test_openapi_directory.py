"""系统 Token 双租户：ITSM 用户目录 / 组织目录 OpenAPI 契约。"""

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.core.openapi.testing import acting_headers, create_system_tenant
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

USERS_URL = "/openapi/v1/system-mgmt/users"
GROUPS_URL = "/openapi/v1/system-mgmt/groups"
SCOPE = {"mode": "all"}

_SENSITIVE_USER_FIELDS = {"password", "otp_secret", "phone", "temporary_pwd", "user_id"}
_SENSITIVE_GROUP_FIELDS = {"description", "external_id", "roles", "is_delete"}


def _tenant(user, team, token):
    return SimpleNamespace(
        user=user,
        team=team,
        token=token,
        system_user=SystemUser.objects.get(username=user.username, domain=user.domain),
    )


def _acting(tenant):
    return acting_headers(tenant.token, tenant.user, tenant.team.id)


def _grant_user_group_view(system_user):
    menu, _ = Menu.objects.get_or_create(
        name="user_group-View",
        app="system-manager",
        defaults={"display_name": "user_group-View", "url": "", "menu_type": "button"},
    )
    role, _ = Role.objects.update_or_create(
        name=f"openapi-user-group-{system_user.username}",
        app="system-manager",
        defaults={"menu_list": [menu.id]},
    )
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])
    return role


def _create_directory_user(*, username, group_ids, disabled=False, display_name="", email="", locale=""):
    return SystemUser.objects.create(
        username=username,
        domain="domain.com",
        display_name=display_name,
        email=email or f"{username}@example.com",
        password="x",
        locale=locale or "zh-Hans",
        disabled=disabled,
        group_list=list(group_ids),
        phone="13800000000",
        otp_secret="otp-secret",
    )


@pytest.fixture
def tenants():
    team_a = Group.objects.create(name=f"dir-a-{uuid.uuid4().hex[:8]}")
    team_b = Group.objects.create(name=f"dir-b-{uuid.uuid4().hex[:8]}")
    user_a, token = create_system_tenant(
        team_a.id,
        username=f"dir-a-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
    )
    user_b, reused = create_system_tenant(
        team_b.id,
        username=f"dir-b-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
        plaintext_token=token,
    )
    assert reused == token
    a = _tenant(user_a, team_a, token)
    b = _tenant(user_b, team_b, token)
    _grant_user_group_view(a.system_user)
    _grant_user_group_view(b.system_user)
    a.member = _create_directory_user(
        username=f"member-a-{uuid.uuid4().hex[:8]}",
        group_ids=[team_a.id],
        display_name="Alice",
        email="alice@example.com",
        locale="en",
    )
    a.disabled_member = _create_directory_user(
        username=f"disabled-a-{uuid.uuid4().hex[:8]}",
        group_ids=[team_a.id],
        disabled=True,
        display_name="Disabled",
        email="disabled@example.com",
    )
    b.member = _create_directory_user(
        username=f"member-b-{uuid.uuid4().hex[:8]}",
        group_ids=[team_b.id],
        display_name="Bob",
        email="bob@example.com",
    )
    return SimpleNamespace(a=a, b=b, token=token)


def _user_ids(payload):
    return [item["id"] for item in payload["data"]["results"]]


def _group_ids(payload):
    return [item["id"] for item in payload["data"]["results"]]


def test_system_tenant_can_read_own_org_users(tenants):
    response = APIClient().get(USERS_URL, **_acting(tenants.a))

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["result"] is True
    data = body["data"]
    assert data["page"] == 1
    assert data["page_size"] == 200
    assert data["count"] >= 2
    ids = set(_user_ids(body))
    assert str(tenants.a.member.id) in ids
    assert str(tenants.a.disabled_member.id) in ids
    assert str(tenants.b.member.id) not in ids
    own = next(item for item in data["results"] if item["id"] == str(tenants.a.member.id))
    assert own == {
        "id": str(tenants.a.member.id),
        "username": tenants.a.member.username,
        "domain": "domain.com",
        "display_name": "Alice",
        "email": "alice@example.com",
        "disabled": False,
        "locale": "en",
        "group_list": [str(tenants.a.team.id)],
    }
    assert _SENSITIVE_USER_FIELDS.isdisjoint(own)


def test_system_tenant_cannot_read_other_org_users(tenants):
    response = APIClient().get(USERS_URL, **_acting(tenants.b))

    assert response.status_code == 200, response.json()
    ids = set(_user_ids(response.json()))
    assert str(tenants.a.member.id) not in ids
    assert str(tenants.b.member.id) in ids


def test_system_tenant_forged_acting_team_is_rejected(tenants):
    response = APIClient().get(
        USERS_URL,
        **acting_headers(tenants.token, tenants.a.user, tenants.b.team.id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_system_tenant_can_read_own_org_groups(tenants):
    response = APIClient().get(GROUPS_URL, **_acting(tenants.a))

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["result"] is True
    data = body["data"]
    assert data["page"] == 1
    assert data["page_size"] == 200
    assert data["count"] == 1
    assert data["results"] == [
        {
            "id": str(tenants.a.team.id),
            "name": tenants.a.team.name,
            "parent_id": None,
            "is_virtual": False,
        }
    ]
    assert _SENSITIVE_GROUP_FIELDS.isdisjoint(data["results"][0])
    assert str(tenants.b.team.id) not in _group_ids(body)


def test_system_tenant_cannot_read_other_org_groups(tenants):
    response = APIClient().get(GROUPS_URL, **_acting(tenants.b))

    assert response.status_code == 200, response.json()
    ids = set(_group_ids(response.json()))
    assert str(tenants.a.team.id) not in ids
    assert str(tenants.b.team.id) in ids


def test_system_tenant_groups_forged_acting_team_is_rejected(tenants):
    response = APIClient().get(
        GROUPS_URL,
        **acting_headers(tenants.token, tenants.a.user, tenants.b.team.id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_group_id_out_of_scope_is_forbidden(tenants):
    response = APIClient().get(
        GROUPS_URL,
        {"group_id": tenants.b.team.id},
        **_acting(tenants.a),
    )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "TEAM_OUT_OF_SCOPE"
    assert "无权访问该组织" in body["message"]


def test_missing_group_id_is_business_rejected(tenants):
    response = APIClient().get(
        USERS_URL,
        {"group_id": 9_999_999},
        **_acting(tenants.a),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"


def test_archived_group_id_is_business_rejected(tenants):
    archived = Group.objects.create(name=f"archived-{uuid.uuid4().hex[:8]}", is_delete=True)
    response = APIClient().get(
        GROUPS_URL,
        {"group_id": archived.id},
        **_acting(tenants.a),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"


@pytest.mark.parametrize("params", [{"page": "0"}, {"page": "-1"}, {"page": "abc"}, {"page_size": "0"}, {"page_size": "-2"}, {"page_size": "1.5"}])
def test_illegal_pagination_is_schema_invalid(tenants, params):
    response = APIClient().get(USERS_URL, params, **_acting(tenants.a))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_page_size_over_max_is_clamped(tenants):
    response = APIClient().get(USERS_URL, {"page_size": "501"}, **_acting(tenants.a))

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["page_size"] == 500


def test_boolean_must_be_true_or_false(tenants):
    response = APIClient().get(USERS_URL, {"include_children": "1"}, **_acting(tenants.a))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_users_exact_query_does_not_leak_invisible_user(tenants):
    visible = APIClient().get(
        USERS_URL,
        {"user_id": str(tenants.a.member.id)},
        **_acting(tenants.a),
    )
    hidden = APIClient().get(
        USERS_URL,
        {"user_id": str(tenants.b.member.id)},
        **_acting(tenants.a),
    )

    assert visible.status_code == 200, visible.json()
    assert _user_ids(visible.json()) == [str(tenants.a.member.id)]
    assert hidden.status_code == 200, hidden.json()
    assert hidden.json()["data"] == {
        "count": 0,
        "page": 1,
        "page_size": 200,
        "results": [],
    }


def test_users_batch_query_does_not_leak_invisible_users(tenants):
    response = APIClient().get(
        USERS_URL,
        {"usernames": f"{tenants.a.member.username},{tenants.b.member.username},missing-user"},
        **_acting(tenants.a),
    )

    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["count"] == 1
    assert _user_ids(response.json()) == [str(tenants.a.member.id)]
    payload = str(response.json())
    assert tenants.b.member.username not in payload
    assert "missing-user" not in payload


def test_search_stays_inside_authorized_org(tenants):
    response = APIClient().get(
        USERS_URL,
        {"search": "Alice"},
        **_acting(tenants.a),
    )
    other = APIClient().get(
        USERS_URL,
        {"search": "Bob"},
        **_acting(tenants.a),
    )

    assert response.status_code == 200, response.json()
    assert str(tenants.a.member.id) in _user_ids(response.json())
    assert other.status_code == 200, other.json()
    assert other.json()["data"]["results"] == []


def test_groups_reject_name_search(tenants):
    response = APIClient().get(
        GROUPS_URL,
        {"search": tenants.a.team.name},
        **_acting(tenants.a),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_username_query_and_selector_conflict(tenants):
    matched = APIClient().get(
        USERS_URL,
        {"username": tenants.a.member.username},
        **_acting(tenants.a),
    )
    domain_rejected = APIClient().get(
        USERS_URL,
        {"username": tenants.a.member.username, "domain": "domain.com"},
        **_acting(tenants.a),
    )
    conflict = APIClient().get(
        USERS_URL,
        {"username": tenants.a.member.username, "search": "Alice"},
        **_acting(tenants.a),
    )

    assert matched.status_code == 200, matched.json()
    assert _user_ids(matched.json()) == [str(tenants.a.member.id)]
    assert domain_rejected.status_code == 400
    assert domain_rejected.json()["code"] == "SCHEMA_INVALID"
    assert conflict.status_code == 400
    assert conflict.json()["code"] == "SCHEMA_INVALID"


def test_group_list_only_contains_authorized_orgs(tenants):
    shared = _create_directory_user(
        username=f"shared-{uuid.uuid4().hex[:8]}",
        group_ids=[tenants.a.team.id, tenants.b.team.id],
        display_name="Shared",
        email="shared@example.com",
    )

    response = APIClient().get(
        USERS_URL,
        {"user_id": str(shared.id)},
        **_acting(tenants.a),
    )

    assert response.status_code == 200, response.json()
    item = response.json()["data"]["results"][0]
    assert item["group_list"] == [str(tenants.a.team.id)]
    assert str(tenants.b.team.id) not in item["group_list"]


def test_include_children_does_not_expand_unauthorized_child(tenants):
    child = Group.objects.create(name=f"child-{uuid.uuid4().hex[:8]}", parent_id=tenants.a.team.id)
    outsider = Group.objects.create(name=f"out-{uuid.uuid4().hex[:8]}", parent_id=tenants.a.team.id)
    tenants.a.system_user.group_list = [tenants.a.team.id, child.id]
    tenants.a.system_user.save(update_fields=["group_list"])
    child_user = _create_directory_user(
        username=f"child-user-{uuid.uuid4().hex[:8]}",
        group_ids=[child.id],
        display_name="Child",
        email="child@example.com",
    )
    outsider_user = _create_directory_user(
        username=f"out-user-{uuid.uuid4().hex[:8]}",
        group_ids=[outsider.id],
        display_name="Out",
        email="out@example.com",
    )

    without_children = APIClient().get(
        GROUPS_URL,
        {"include_children": "false"},
        **_acting(tenants.a),
    )
    with_children = APIClient().get(
        GROUPS_URL,
        {"include_children": "true"},
        **_acting(tenants.a),
    )
    users = APIClient().get(
        USERS_URL,
        {"include_children": "true"},
        **_acting(tenants.a),
    )

    assert without_children.status_code == 200, without_children.json()
    assert _group_ids(without_children.json()) == [str(tenants.a.team.id)]
    assert with_children.status_code == 200, with_children.json()
    assert set(_group_ids(with_children.json())) == {str(tenants.a.team.id), str(child.id)}
    assert str(outsider.id) not in _group_ids(with_children.json())
    user_ids = set(_user_ids(users.json()))
    assert str(child_user.id) in user_ids
    assert str(outsider_user.id) not in user_ids


def test_scope_root_parent_id_null_and_preserved_across_pages(tenants):
    children = [
        Group.objects.create(name=f"page-child-{index}-{uuid.uuid4().hex[:8]}", parent_id=tenants.a.team.id)
        for index in range(4)
    ]
    tenants.a.system_user.group_list = [tenants.a.team.id, *[child.id for child in children]]
    tenants.a.system_user.save(update_fields=["group_list"])

    page1 = APIClient().get(
        GROUPS_URL,
        {"include_children": "true", "page": "1", "page_size": "2"},
        **_acting(tenants.a),
    )
    page2 = APIClient().get(
        GROUPS_URL,
        {"include_children": "true", "page": "2", "page_size": "2"},
        **_acting(tenants.a),
    )
    page3 = APIClient().get(
        GROUPS_URL,
        {"include_children": "true", "page": "9", "page_size": "2"},
        **_acting(tenants.a),
    )

    assert page1.status_code == 200, page1.json()
    assert page2.status_code == 200, page2.json()
    data1 = page1.json()["data"]
    data2 = page2.json()["data"]
    expected_count = 5
    assert data1["count"] == expected_count
    assert data2["count"] == expected_count
    assert data1["results"][0]["id"] == str(tenants.a.team.id)
    assert data1["results"][0]["parent_id"] is None
    child_on_page2 = data2["results"][0]
    assert child_on_page2["id"] != str(tenants.a.team.id)
    assert child_on_page2["parent_id"] == str(tenants.a.team.id)
    assert page3.status_code == 200, page3.json()
    assert page3.json()["data"]["count"] == expected_count
    assert page3.json()["data"]["results"] == []
