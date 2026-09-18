"""系统 Token 双租户契约（T8）：两个组织的 acting 用户读隔离与写归属。"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.cmdb.tests.openapi_gateway_support import (
    TEAM_A_UUID,
    TEAM_B_UUID,
    grant_cmdb_openapi_menus,
    start_cmdb_gateway_catalog,
    stop_cmdb_gateway_catalog,
)
from apps.core.openapi.testing import acting_headers, create_system_tenant
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

INSTANCES_URL = "/openapi/v1/cmdb/instances"
CREATE_URL = "/openapi/v1/cmdb/instance-create"
SCOPE = {"mode": "all"}


def _tenant(user, team, token):
    return SimpleNamespace(
        user=user,
        team=team,
        token=token,
        system_user=SystemUser.objects.get(username=user.username, domain=user.domain),
    )


def _acting(tenant):
    return acting_headers(tenant.token, tenant.user, tenant.team.id)


@pytest.fixture
def tenants():
    team_a = Group.objects.create(name=f"sys-a-{uuid.uuid4().hex[:8]}")
    team_b = Group.objects.create(name=f"sys-b-{uuid.uuid4().hex[:8]}")
    user_a, token = create_system_tenant(
        team_a.id,
        username=f"sys-a-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
    )
    user_b, reused = create_system_tenant(
        team_b.id,
        username=f"sys-b-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
        plaintext_token=token,
    )
    assert reused == token
    a = _tenant(user_a, team_a, token)
    b = _tenant(user_b, team_b, token)
    grant_cmdb_openapi_menus(a.system_user)
    grant_cmdb_openapi_menus(b.system_user)
    return SimpleNamespace(a=a, b=b, token=token)


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


@pytest.fixture
def catalog(tenants):
    item = start_cmdb_gateway_catalog(tenants)
    yield item
    stop_cmdb_gateway_catalog(item)


def test_system_tenant_can_list_own_org_instances(tenants, instance_catalog):
    response = APIClient().get(
        INSTANCES_URL, {"model_id": "host"}, **_acting(tenants.a)
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


def test_system_tenant_cannot_list_other_org_instances(tenants, instance_catalog):
    response = APIClient().get(
        INSTANCES_URL, {"model_id": "host"}, **_acting(tenants.b)
    )

    assert response.status_code == 200, response.json()
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


def test_system_tenant_forged_acting_team_is_rejected(tenants, instance_catalog):
    response = APIClient().get(
        INSTANCES_URL,
        {"model_id": "host"},
        **acting_headers(tenants.token, tenants.a.user, tenants.b.team.id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_system_tenant_can_create_instance_in_own_org(tenants, catalog):
    response = APIClient().post(
        CREATE_URL,
        {"model_id": "host", "attrs": {"inst_name": "host-new"}},
        format="json",
        **_acting(tenants.a),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["organization"] == [tenants.a.team.id]
    assert catalog.calls.create[0]["operator"] == tenants.a.user.username
    assert catalog.calls.create[0]["allowed_org_ids"] == [tenants.a.team.id]
    assert catalog.calls.create[0]["data"]["organization"] == [tenants.a.team.id]


def test_system_tenant_create_does_not_belong_to_other_org(tenants, catalog):
    response = APIClient().post(
        CREATE_URL,
        {"model_id": "host", "attrs": {"inst_name": "host-b-new"}},
        format="json",
        **_acting(tenants.b),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["organization"] == [tenants.b.team.id]
    assert catalog.calls.create[0]["operator"] == tenants.b.user.username
    assert tenants.a.team.id not in catalog.calls.create[0]["allowed_org_ids"]
    assert tenants.a.team.id not in catalog.calls.create[0]["data"]["organization"]
    assert catalog.calls.create[0]["operator"] != tenants.a.user.username
