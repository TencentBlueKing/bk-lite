"""统一 OpenAPI 网关：日志分组与检索双租户契约。"""

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType
from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.services.collect_type import CollectTypeService
from apps.log.services.k8s_collect import K8sLogCollectService
from apps.log.services.search import SearchService
from apps.node_mgmt.models import CloudRegion, Node, NodeOrganization
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

GROUPS_URL = "/openapi/v1/log/groups"
SEARCH_URL = "/openapi/v1/log/search"
TYPES_URL = "/openapi/v1/log/collect-types"
INSTANCES_URL = "/openapi/v1/log/collect-instances"
CONFIG_URL = "/openapi/v1/log/collect-instances/config"
K8S_URL = "/openapi/v1/log/k8s-collectors"
K8S_COMMAND_URL = "/openapi/v1/log/k8s-collectors/install-command"
K8S_STATUS_URL = "/openapi/v1/log/k8s-collectors/status"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant(system_user):
    menu_ids = []
    for name in ("grouping-View", "search-View", "integration_list-View", "integration_configure-Add"):
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


def _collect_type(name="file"):
    return CollectType.objects.create(name=name, collector="vector", attrs=[{"name": "path"}])


def _log_node(organization):
    region = CloudRegion.objects.create(name=f"region-{uuid.uuid4().hex[:6]}")
    node = Node.objects.create(
        id=f"node-{uuid.uuid4().hex[:8]}",
        name="node",
        ip="10.0.0.9",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=organization)
    return node


def test_api_tenant_can_list_collect_types(tenants):
    collect_type = _collect_type()

    response = APIClient().get(TYPES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    item = next(row for row in response.json()["data"]["items"] if row["id"] == collect_type.id)
    assert item["fields"] == [{"name": "path"}]


def test_api_tenant_can_create_collect_instance_on_own_node(tenants, monkeypatch):
    collect_type = _collect_type()
    node = _log_node(tenants.a.team.id)
    seen = {}

    def _create(data):
        seen["group_ids"] = data["instances"][0]["group_ids"]

    monkeypatch.setattr(CollectTypeService, "batch_create_collect_configs", staticmethod(_create))
    response = APIClient().post(
        INSTANCES_URL,
        {
            "collect_type_id": collect_type.id,
            "instances": [{"instance_id": "log-1", "instance_name": "app", "node_ids": [node.id]}],
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert seen["group_ids"] == [tenants.a.team.id]


def test_api_tenant_cannot_create_collect_instance_on_other_org_node(tenants, monkeypatch):
    collect_type = _collect_type()
    node = _log_node(tenants.b.team.id)
    called = {"value": False}

    def _create(data):
        called["value"] = True

    monkeypatch.setattr(CollectTypeService, "batch_create_collect_configs", staticmethod(_create))
    response = APIClient().post(
        INSTANCES_URL,
        {
            "collect_type_id": collect_type.id,
            "instances": [{"instance_id": "log-1", "instance_name": "app", "node_ids": [node.id]}],
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "节点不存在"
    assert called["value"] is False


def test_api_tenant_cannot_update_other_org_collect_config(tenants, monkeypatch):
    collect_type = _collect_type()
    instance = CollectInstance.objects.create(id=f"log-{uuid.uuid4().hex[:6]}", name="other", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=tenants.b.team.id)
    called = {"value": False}

    def _update(*args, **kwargs):
        called["value"] = True

    monkeypatch.setattr(CollectTypeService, "update_instance_config_v2", staticmethod(_update))
    response = APIClient().put(
        CONFIG_URL,
        {"instance_id": instance.id, "collect_type_id": collect_type.id, "child": {"id": "cfg", "content": {}}},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "采集实例不存在"
    assert called["value"] is False


def test_api_tenant_can_delete_own_collect_instance(tenants):
    collect_type = _collect_type()
    instance = CollectInstance.objects.create(id=f"log-{uuid.uuid4().hex[:6]}", name="own", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=tenants.a.team.id)

    response = APIClient().delete(INSTANCES_URL, {"instance_ids": [instance.id]}, format="json", **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    assert not CollectInstance.objects.filter(id=instance.id).exists()


def test_api_tenant_can_create_log_k8s_collector(tenants):
    collect_type = _collect_type("kubernetes")

    response = APIClient().post(
        K8S_URL,
        {"collect_type_id": collect_type.id, "name": f"cluster-{uuid.uuid4().hex[:6]}"},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    instance_id = response.json()["data"]["instance_id"]
    assert CollectInstanceOrganization.objects.filter(collect_instance_id=instance_id, organization=tenants.a.team.id).exists()


def test_api_tenant_cannot_read_other_org_k8s_status(tenants, monkeypatch):
    collect_type = _collect_type("kubernetes")
    instance = CollectInstance.objects.create(id=f"k8s-{uuid.uuid4().hex[:6]}", name="other", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=tenants.b.team.id)
    called = {"value": False}

    def _status(instance_id):
        called["value"] = True
        return True

    monkeypatch.setattr(K8sLogCollectService, "check_collect_status", staticmethod(_status))
    response = APIClient().get(K8S_STATUS_URL, {"instance_id": instance.id}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["message"] == "采集实例不存在"
    assert called["value"] is False


def test_api_tenant_cannot_save_other_org_k8s_setting(tenants, monkeypatch):
    collect_type = _collect_type("kubernetes")
    instance = CollectInstance.objects.create(id=f"k8s-{uuid.uuid4().hex[:6]}", name="other", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=tenants.b.team.id)
    called = {"value": False}

    def _save(instance_id, data):
        called["value"] = True
        return {}

    monkeypatch.setattr(K8sLogCollectService, "save_setting", classmethod(lambda cls, instance_id, data: _save(instance_id, data)))
    response = APIClient().put(
        "/openapi/v1/log/k8s-collectors/setting",
        {"instance_id": instance.id, "runtime_profile": "standard"},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "采集实例不存在"
    assert called["value"] is False


def test_k8s_command_forged_team_is_rejected(tenants):
    response = APIClient().post(
        K8S_COMMAND_URL,
        {"instance_id": "x", "cloud_region_id": 1, "team": 9},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
