"""统一 OpenAPI 网关：节点只读目录双租户契约。"""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.node_mgmt.models import CloudRegion, Collector, Node, NodeComponentVersion, NodeOrganization
from apps.node_mgmt.openapi_serializers import NodeListQuerySerializer
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

REGIONS_URL = "/openapi/v1/node/cloud-regions"
NODES_URL = "/openapi/v1/node/nodes"
DETAIL_URL = "/openapi/v1/node/nodes/detail"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant(system_user):
    names = ["cloud_region_list-View", "cloud_region_node-View"]
    menu_ids = []
    for name in names:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="node",
            defaults={"display_name": name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(name="openapi-node-reader", app="node", defaults={"menu_list": menu_ids})
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])


def _make_tenant(*, team_name, username, domain, grant=True):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(username=user.username, domain=user.domain, group_list=[team.id])
    if grant:
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
        a=_make_tenant(team_name="node-gw-a", username="node-gw-a", domain="a.test.com"),
        b=_make_tenant(team_name="node-gw-b", username="node-gw-b", domain="b.test.com"),
    )


def _region():
    return CloudRegion.objects.create(name=f"region-{uuid.uuid4().hex[:6]}", proxy_address="10.1.1.1:8080")


def _node(region, *, name, organization=None):
    node = Node.objects.create(
        id=f"node-{uuid.uuid4().hex[:8]}",
        name=name,
        ip="10.0.0.8",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    if organization is not None:
        NodeOrganization.objects.create(node=node, organization=organization)
    return node


def test_node_list_schema_documents_page_bounds():
    fields = NodeListQuerySerializer().fields
    assert fields["page"].min_value == 1
    assert fields["page_size"].default == 20
    assert "team" not in fields
    assert "user" not in fields


def test_both_tenants_see_the_same_cloud_regions(tenants):
    region = _region()

    first = APIClient().get(REGIONS_URL, **_auth(tenants.a.token))
    second = APIClient().get(REGIONS_URL, **_auth(tenants.b.token))

    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    first_ids = {item["id"] for item in first.json()["data"]["items"]}
    second_ids = {item["id"] for item in second.json()["data"]["items"]}
    assert region.id in first_ids
    assert region.id in second_ids


def test_cloud_regions_omit_proxy_address(tenants):
    _region()

    response = APIClient().get(REGIONS_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    assert all("proxy_address" not in item for item in response.json()["data"]["items"])


def test_cloud_regions_forged_team_is_rejected(tenants):
    response = APIClient().get(REGIONS_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_nodes(tenants):
    region = _region()
    own = _node(region, name="own-node", organization=tenants.a.team.id)
    other = _node(region, name="other-node", organization=tenants.b.team.id)
    unassigned = _node(region, name="loose-node")
    Node.objects.filter(id=own.id).update(updated_at=timezone.now())
    Node.objects.filter(id=other.id).update(updated_at=timezone.now() - timedelta(minutes=5))

    response = APIClient().get(NODES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    items = {item["id"]: item for item in response.json()["data"]["items"]}
    assert own.id in items
    assert items[own.id]["online"] is True
    assert other.id not in items
    assert unassigned.id not in items


def test_api_tenant_cannot_list_other_org_nodes(tenants):
    region = _region()
    other = _node(region, name="hidden-node", organization=tenants.a.team.id)

    response = APIClient().get(NODES_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert other.id not in ids


def test_nodes_forged_team_is_rejected(tenants):
    response = APIClient().get(NODES_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_read_own_node_detail(tenants):
    region = _region()
    node = _node(region, name="detail-node", organization=tenants.a.team.id)
    collector = Collector.objects.create(
        id=f"col-{uuid.uuid4().hex[:6]}",
        name="telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/usr/bin/telegraf",
    )
    node.status = {"collectors": [{"collector_id": collector.id, "status": 0}]}
    node.save(update_fields=["status"])
    NodeComponentVersion.objects.create(node=node, component_type="controller", component_id="sidecar", version="1.2.3")

    response = APIClient().get(DETAIL_URL, {"node_id": node.id}, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["id"] == node.id
    assert data["collectors"] == [{"collector_id": collector.id, "collector_name": "telegraf", "status": 0}]
    assert data["controllers"] == [{"component_id": "sidecar", "version": "1.2.3", "upgradeable": False}]
    assert "collector_configuration_directory" not in data


def test_api_tenant_cannot_read_other_org_node_detail(tenants):
    region = _region()
    node = _node(region, name="secret-node", organization=tenants.a.team.id)

    response = APIClient().get(DETAIL_URL, {"node_id": node.id}, **_auth(tenants.b.token))

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert response.json()["message"] == "节点不存在"


def test_node_detail_forged_team_is_rejected(tenants):
    response = APIClient().get(
        DETAIL_URL,
        {"node_id": "node-1", "team": str(tenants.b.team.id)},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_stale_heartbeat_is_offline(tenants):
    region = _region()
    node = _node(region, name="stale-node", organization=tenants.a.team.id)
    Node.objects.filter(id=node.id).update(updated_at=timezone.now() - timedelta(seconds=120))

    response = APIClient().get(NODES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    item = next(row for row in response.json()["data"]["items"] if row["id"] == node.id)
    assert item["online"] is False
