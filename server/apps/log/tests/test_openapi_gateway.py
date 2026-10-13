"""统一 OpenAPI 网关：日志分组与检索双租户契约。"""

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.services.search import SearchService
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

GROUPS_URL = "/openapi/v1/log/groups"
SEARCH_URL = "/openapi/v1/log/search"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant(system_user):
    menu_ids = []
    for name in ("grouping-View", "search-View"):
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="log",
            defaults={"display_name": name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(name="openapi-log-reader", app="log", defaults={"menu_list": menu_ids})
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])


def _make_tenant(*, team_name, username, domain):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(username=user.username, domain=user.domain, group_list=[team.id])
    _grant(system_user)
    token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        api_secret=UserAPISecret.hash_api_secret(token),
        team=team.id,
    )
    return SimpleNamespace(team=team, user=user, token=token)


@pytest.fixture
def tenants():
    return SimpleNamespace(
        a=_make_tenant(team_name="log-gw-a", username="log-gw-a", domain="a.test.com"),
        b=_make_tenant(team_name="log-gw-b", username="log-gw-b", domain="b.test.com"),
    )


def _group(name, organization=None):
    group = LogGroup.objects.create(id=f"group-{uuid.uuid4().hex[:8]}", name=name)
    if organization is not None:
        LogGroupOrganization.objects.create(log_group=group, organization=organization)
    return group


def test_api_tenant_can_list_own_groups(tenants):
    own = _group("own-logs", tenants.a.team.id)
    other = _group("other-logs", tenants.b.team.id)
    unassigned = _group("loose-logs")

    response = APIClient().get(GROUPS_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert own.id in ids
    assert other.id not in ids
    assert unassigned.id not in ids
    assert "rule" not in response.json()["data"]["items"][0]


def test_groups_forged_team_is_rejected(tenants):
    response = APIClient().get(GROUPS_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_search_own_group(tenants, monkeypatch):
    group = _group("own-logs", tenants.a.team.id)
    monkeypatch.setattr(
        SearchService,
        "search_logs",
        staticmethod(lambda *args, **kwargs: [{"_time": "2026-01-01T00:10:00Z", "message": "hello", "_msg": "secret-body"}]),
    )

    response = APIClient().get(
        SEARCH_URL,
        {
            "log_group_id": group.id,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T00:30:00Z",
            "query": "message:hello",
        },
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    item = response.json()["data"]["items"][0]
    assert item["message"] == "hello"
    assert item["time"] == "2026-01-01T00:10:00Z"
    assert "_msg" not in item["fields"]


def test_api_tenant_cannot_search_other_org_group(tenants, monkeypatch):
    group = _group("other-logs", tenants.a.team.id)
    monkeypatch.setattr(
        SearchService,
        "search_logs",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("searched"))),
    )

    response = APIClient().get(
        SEARCH_URL,
        {
            "log_group_id": group.id,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T00:30:00Z",
        },
        **_auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "日志分组不存在"


def test_search_rejects_window_over_one_hour(tenants):
    response = APIClient().get(
        SEARCH_URL,
        {
            "log_group_id": "group-1",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T02:00:00Z",
        },
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "查询时间范围不能超过 1 小时"


def test_search_truncates_long_message(tenants, monkeypatch):
    group = _group("own-logs", tenants.a.team.id)
    monkeypatch.setattr(
        SearchService,
        "search_logs",
        staticmethod(lambda *args, **kwargs: [{"message": "x" * 3000}]),
    )

    response = APIClient().get(
        SEARCH_URL,
        {
            "log_group_id": group.id,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T00:10:00Z",
        },
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    item = response.json()["data"]["items"][0]
    assert len(item["message"]) == 2048
    assert item["truncated"] is True
