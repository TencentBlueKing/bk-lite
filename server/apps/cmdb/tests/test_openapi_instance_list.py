"""统一 OpenAPI 网关：CMDB 实例列表双租户契约。"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.cmdb.open_api.errors import CMDBOpenAPIError
from apps.cmdb.open_api.services import CMDBOpenAPIService
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

URL = "/openapi/v1/cmdb/instances"

TEAM_A_UUID = "11111111-1111-4111-8111-111111111111"
TEAM_B_UUID = "22222222-2222-4222-8222-222222222222"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant_asset_view(system_user):
    menu, _ = Menu.objects.get_or_create(
        name="asset_info-View",
        app="cmdb",
        defaults={"display_name": "Asset View", "url": "", "menu_type": "button"},
    )
    role, _ = Role.objects.update_or_create(
        name="openapi-asset-reader",
        app="cmdb",
        defaults={"menu_list": [menu.id]},
    )
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])
    return role


def _make_tenant(*, team_name, username, domain, grant_view=True):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(
        username=user.username,
        domain=user.domain,
        group_list=[team.id],
    )
    if grant_view:
        _grant_asset_view(system_user)
    token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        api_secret=UserAPISecret.hash_api_secret(token),
        team=team.id,
    )
    return SimpleNamespace(team=team, user=user, system_user=system_user, token=token)


@pytest.fixture
def tenants():
    return SimpleNamespace(
        a=_make_tenant(team_name="cmdb-openapi-a", username="cmdb-openapi-a", domain="a.test.com"),
        b=_make_tenant(team_name="cmdb-openapi-b", username="cmdb-openapi-b", domain="b.test.com"),
    )


@pytest.fixture
def instance_catalog(tenants):
    store = {
        tenants.a.team.id: [
            {
                "_id": 11,
                "inst_uuid": TEAM_A_UUID,
                "model_id": "host",
                "inst_name": "host-a",
                "organization": [tenants.a.team.id],
                "_labels": "instance",
            }
        ],
        tenants.b.team.id: [
            {
                "_id": 12,
                "inst_uuid": TEAM_B_UUID,
                "model_id": "host",
                "inst_name": "host-b",
                "organization": [tenants.b.team.id],
                "_labels": "instance",
            }
        ],
    }

    def fake_instance_list(model_id, params, page, page_size, order, permission_map, creator=""):
        del model_id, params, page, page_size, order, creator
        team_ids = {int(team_id) for team_id in (permission_map or {})}
        items = []
        for team_id, rows in store.items():
            if team_id in team_ids:
                items.extend(rows)
        return items, len(items)

    patches = [
        patch("apps.cmdb.open_api.services.get_default_group_id", return_value=[1]),
        patch(
            "apps.cmdb.open_api.services.ModelManage.search_model_info",
            lambda model_id: {"model_id": model_id, "is_visible": True},
        ),
        patch(
            "apps.cmdb.open_api.services.ModelManage.search_model_attr",
            return_value=[{"attr_id": "inst_name", "attr_type": "str", "editable": True}],
        ),
        patch(
            "apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission",
            return_value=True,
        ),
        patch("apps.cmdb.open_api.auth.get_permission_rules", return_value={"team": []}),
        patch(
            "apps.cmdb.open_api.services.InstanceManage.instance_list",
            side_effect=fake_instance_list,
        ),
    ]
    for item in patches:
        item.start()
    yield store
    for item in patches:
        item.stop()


def test_api_tenant_can_list_own_org_instances(tenants, instance_catalog):
    response = APIClient().get(
        URL,
        {"model_id": "host"},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["count"] == 1
    assert data["items"] == [
        {
            "inst_uuid": TEAM_A_UUID,
            "model_id": "host",
            "inst_name": "host-a",
            "organization": [tenants.a.team.id],
        }
    ]


def test_api_tenant_cannot_list_other_org_instances(tenants, instance_catalog):
    response = APIClient().get(
        URL,
        {"model_id": "host"},
        **_auth(tenants.b.token),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    names = [item["inst_name"] for item in data["items"]]
    assert "host-a" not in names
    assert data["items"] == [
        {
            "inst_uuid": TEAM_B_UUID,
            "model_id": "host",
            "inst_name": "host-b",
            "organization": [tenants.b.team.id],
        }
    ]


def test_forged_team_is_rejected(tenants, instance_catalog):
    response = APIClient().get(
        URL,
        {"model_id": "host", "team": str(tenants.b.team.id)},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    own = APIClient().get(URL, {"model_id": "host"}, **_auth(tenants.a.token))
    assert [item["inst_name"] for item in own.json()["data"]["items"]] == ["host-a"]


def test_missing_model_id_is_rejected(tenants, instance_catalog):
    response = APIClient().get(URL, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_page_size_over_limit_is_clamped(tenants, instance_catalog):
    response = APIClient().get(
        URL,
        {"model_id": "host", "page_size": 999},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["page_size"] == 200


def test_missing_asset_view_permission_is_forbidden():
    tenant = _make_tenant(
        team_name="cmdb-openapi-noperm",
        username="cmdb-openapi-noperm",
        domain="noperm.test.com",
        grant_view=False,
    )
    response = APIClient().get(
        URL,
        {"model_id": "host"},
        **_auth(tenant.token),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERM_MISSING"


def test_get_model_attrs_still_requires_model_management_view():
    context = MagicMock()
    context.require_feature.side_effect = CMDBOpenAPIError("cmdb.permission.denied", "权限不足", 403)

    with pytest.raises(CMDBOpenAPIError) as exc_info:
        CMDBOpenAPIService(context).get_model_attrs("host")

    assert exc_info.value.status_code == 403
    context.require_feature.assert_called_once_with("model_management-View")
