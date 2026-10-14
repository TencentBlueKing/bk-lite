"""统一 OpenAPI 网关：监控只读目录双租户契约。"""

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.base.models import User, UserAPISecret
from apps.monitor.models import (
    Metric,
    MetricGroup,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPlugin,
    MonitorPluginUITemplate,
    MonitorPolicy,
    PolicyGroup,
    PolicyOrganization,
)
from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.services.metrics import Metrics
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.node_mgmt.models import CloudRegion, Node, NodeOrganization
from apps.monitor.openapi_serializers import MonitorObjectQuerySerializer
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

OBJECTS_URL = "/openapi/v1/monitor/objects"
INSTANCES_URL = "/openapi/v1/monitor/instances"
POLICIES_URL = "/openapi/v1/monitor/policies"
METRICS_URL = "/openapi/v1/monitor/metrics"
INSTANT_URL = "/openapi/v1/monitor/metrics/instant"
RANGE_URL = "/openapi/v1/monitor/metrics/range"
PLUGINS_URL = "/openapi/v1/monitor/plugins"
PLUGIN_FORM_URL = "/openapi/v1/monitor/plugins/form"
POLICY_GROUPS_URL = "/openapi/v1/monitor/policy-groups"
INTEGRATIONS_URL = "/openapi/v1/monitor/integrations"
CLUSTER_URL = "/openapi/v1/monitor/cluster-collectors"
CLUSTER_COMMAND_URL = "/openapi/v1/monitor/cluster-collectors/install-command"
CLUSTER_STATUS_URL = "/openapi/v1/monitor/cluster-collectors/status"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant(system_user, app, names):
    menu_ids = []
    for name in names:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app=app,
            defaults={"display_name": name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(
        name=f"openapi-{app}-reader",
        app=app,
        defaults={"menu_list": menu_ids},
    )
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])


def _make_tenant(*, team_name, username, domain, grant=True):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(username=user.username, domain=user.domain, group_list=[team.id])
    if grant:
        _grant(
            system_user,
            "monitor",
            [
                "object-View",
                "asset-View",
                "strategy_list-View",
                "view_list-View",
                "integration_list-View",
                "integration_configure-View",
                "integration_configure-Add",
                "asset-Delete",
            ],
        )
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
        a=_make_tenant(team_name="mon-gw-a", username="mon-gw-a", domain="a.test.com"),
        b=_make_tenant(team_name="mon-gw-b", username="mon-gw-b", domain="b.test.com"),
    )


def _object(name, visible=True):
    return MonitorObject.objects.create(name=name, display_name=name, is_visible=visible)


def test_object_schema_documents_page_bounds():
    fields = MonitorObjectQuerySerializer().fields
    assert fields["page"].min_value == 1
    assert fields["page"].default == 1
    assert fields["page_size"].min_value == 1
    assert fields["page_size"].default == 20
    assert "team" not in fields


def test_api_tenant_can_list_visible_objects(tenants):
    visible = _object(f"host-{uuid.uuid4().hex[:6]}")
    hidden = _object(f"hidden-{uuid.uuid4().hex[:6]}", visible=False)

    response = APIClient().get(OBJECTS_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert visible.id in ids
    assert hidden.id not in ids


def test_other_tenant_sees_the_same_visible_objects(tenants):
    visible = _object(f"shared-{uuid.uuid4().hex[:6]}")

    response = APIClient().get(OBJECTS_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert visible.id in ids


def test_objects_forged_team_is_rejected(tenants):
    response = APIClient().get(OBJECTS_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_instances(tenants):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    own = MonitorInstance.objects.create(id=f"inst-a-{uuid.uuid4().hex[:6]}", name="own", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=own, organization=tenants.a.team.id)
    other = MonitorInstance.objects.create(id=f"inst-b-{uuid.uuid4().hex[:6]}", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=tenants.b.team.id)
    unassigned = MonitorInstance.objects.create(id=f"inst-u-{uuid.uuid4().hex[:6]}", name="none", monitor_object=obj)
    deleted = MonitorInstance.objects.create(
        id=f"inst-d-{uuid.uuid4().hex[:6]}",
        name="deleted",
        monitor_object=obj,
        is_deleted=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=deleted, organization=tenants.a.team.id)

    response = APIClient().get(INSTANCES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert own.id in ids
    assert other.id not in ids
    assert unassigned.id not in ids
    assert deleted.id not in ids


def test_api_tenant_cannot_list_other_org_instances(tenants):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    other = MonitorInstance.objects.create(id=f"inst-x-{uuid.uuid4().hex[:6]}", name="hidden", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=tenants.a.team.id)

    response = APIClient().get(INSTANCES_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert other.id not in ids


def test_instances_forged_team_is_rejected(tenants):
    response = APIClient().get(INSTANCES_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_policies(tenants):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    own = MonitorPolicy.objects.create(name="own-policy", monitor_object=obj, algorithm="avg")
    PolicyOrganization.objects.create(policy=own, organization=tenants.a.team.id)
    other = MonitorPolicy.objects.create(name="other-policy", monitor_object=obj, algorithm="avg")
    PolicyOrganization.objects.create(policy=other, organization=tenants.b.team.id)
    unassigned = MonitorPolicy.objects.create(name="loose-policy", monitor_object=obj, algorithm="avg")

    response = APIClient().get(POLICIES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert own.id in ids
    assert other.id not in ids
    assert unassigned.id not in ids


def test_api_tenant_cannot_list_other_org_policies(tenants):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    other = MonitorPolicy.objects.create(name="hidden-policy", monitor_object=obj, algorithm="avg")
    PolicyOrganization.objects.create(policy=other, organization=tenants.a.team.id)

    response = APIClient().get(POLICIES_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert other.id not in ids


def test_policies_forged_team_is_rejected(tenants):
    response = APIClient().get(POLICIES_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def _metric(obj):
    group = MetricGroup.objects.create(monitor_object=obj, name=f"group-{uuid.uuid4().hex[:6]}")
    return Metric.objects.create(
        monitor_object=obj,
        metric_group=group,
        name="cpu_usage",
        display_name="CPU",
        unit="%",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
        dimensions=[{"name": "instance_id"}],
    )


def test_api_tenant_can_list_metrics_without_query(tenants):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    metric = _metric(obj)
    hidden = _object(f"hidden-{uuid.uuid4().hex[:6]}", visible=False)
    _metric(hidden)

    response = APIClient().get(METRICS_URL, {"monitor_object_id": obj.id}, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    items = response.json()["data"]["items"]
    assert [item["id"] for item in items] == [metric.id]
    assert "query" not in items[0]
    assert items[0]["dimensions"] == ["instance_id"]


def test_hidden_object_metrics_are_rejected(tenants):
    hidden = _object(f"hidden-{uuid.uuid4().hex[:6]}", visible=False)

    response = APIClient().get(METRICS_URL, {"monitor_object_id": hidden.id}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["message"] == "监控对象不存在"


def test_api_tenant_can_query_own_metric_instant(tenants, monkeypatch):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    metric = _metric(obj)
    instance = MonitorInstance.objects.create(id=f"inst-{uuid.uuid4().hex[:6]}", name="own", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=tenants.a.team.id)
    monkeypatch.setattr(
        Metrics,
        "get_metrics",
        lambda query, time=None: {
            "status": "success",
            "data": {"result": [{"metric": {"instance_id": "own", "__name__": "cpu_usage"}, "value": [1, "12"]}]},
        },
    )

    response = APIClient().get(
        INSTANT_URL,
        {"instance_id": instance.id, "metric_id": metric.id},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["series"] == [{"labels": {"instance_id": "own"}, "point": {"timestamp": 1, "value": "12"}}]
    assert "query" not in data


def test_api_tenant_cannot_query_other_org_metric(tenants, monkeypatch):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    metric = _metric(obj)
    instance = MonitorInstance.objects.create(id=f"inst-{uuid.uuid4().hex[:6]}", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=tenants.a.team.id)
    monkeypatch.setattr(Metrics, "get_metrics", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("queried")))

    response = APIClient().get(
        INSTANT_URL,
        {"instance_id": instance.id, "metric_id": metric.id},
        **_auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "监控实例不存在"


def test_metric_query_rejects_raw_query(tenants):
    response = APIClient().get(INSTANT_URL, {"instance_id": "x", "metric_id": 1, "query": "up"}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_cannot_query_other_org_metric_range(tenants, monkeypatch):
    obj = _object(f"obj-{uuid.uuid4().hex[:6]}")
    metric = _metric(obj)
    instance = MonitorInstance.objects.create(id=f"inst-{uuid.uuid4().hex[:6]}", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=tenants.a.team.id)
    monkeypatch.setattr(
        Metrics,
        "get_metrics_range",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("queried")),
    )

    response = APIClient().get(
        RANGE_URL,
        {
            "instance_id": instance.id,
            "metric_id": metric.id,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T01:00:00Z",
        },
        **_auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "监控实例不存在"


def test_metric_range_rejects_window_over_six_hours(tenants):
    response = APIClient().get(
        RANGE_URL,
        {
            "instance_id": "x",
            "metric_id": 1,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T07:00:00Z",
        },
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "查询时间范围不能超过 6 小时"


def test_missing_permission_is_denied():
    tenant = _make_tenant(team_name="mon-gw-none", username="mon-gw-none", domain="none.test.com", grant=False)

    response = APIClient().get(OBJECTS_URL, **_auth(tenant.token))

    assert response.status_code == 403
    assert response.json()["code"] == "PERM_MISSING"


def _plugin(obj, name="host"):
    plugin = MonitorPlugin.objects.create(name=f"{name}-{uuid.uuid4().hex[:6]}", display_name=name, collector="telegraf", collect_type="exec")
    plugin.monitor_object.add(obj)
    MonitorPluginUITemplate.objects.create(plugin=plugin, content={"fields": ["interval"]})
    return plugin


def _node(organization):
    region = CloudRegion.objects.create(name=f"region-{uuid.uuid4().hex[:6]}")
    node = Node.objects.create(
        id=f"node-{uuid.uuid4().hex[:8]}",
        name="node",
        ip="10.0.0.8",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=organization)
    return node


def test_api_tenant_can_list_plugins_and_form(tenants):
    obj = _object("host")
    plugin = _plugin(obj)

    listed = APIClient().get(PLUGINS_URL, {"monitor_object_id": obj.id}, **_auth(tenants.a.token))
    form = APIClient().get(PLUGIN_FORM_URL, {"plugin_id": plugin.id}, **_auth(tenants.a.token))

    assert listed.status_code == 200, listed.json()
    assert plugin.id in {item["id"] for item in listed.json()["data"]["items"]}
    assert "status_query" not in listed.json()["data"]["items"][0]
    assert form.status_code == 200, form.json()
    assert form.json()["data"]["form"] == {"fields": ["interval"]}


def test_hidden_object_plugins_are_rejected(tenants):
    hidden = _object("hidden", visible=False)

    response = APIClient().get(PLUGINS_URL, {"monitor_object_id": hidden.id}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["message"] == "监控对象不存在"


def test_api_tenant_can_list_own_policy_groups(tenants):
    obj = _object("host")
    own = PolicyGroup.objects.create(organization=tenants.a.team.id, monitor_object=obj, name="own-group")
    PolicyGroup.objects.create(organization=tenants.b.team.id, monitor_object=obj, name="other-group")

    response = APIClient().get(POLICY_GROUPS_URL, {"monitor_object_id": obj.id}, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert ids == {own.id}


def test_policy_groups_forged_team_is_rejected(tenants):
    obj = _object("host")

    response = APIClient().get(
        POLICY_GROUPS_URL,
        {"monitor_object_id": obj.id, "team": str(tenants.b.team.id)},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_save_integration_for_own_node(tenants, monkeypatch):
    obj = _object("host")
    plugin = _plugin(obj)
    node = _node(tenants.a.team.id)
    seen = {}

    def _create(data, actor_context=None):
        seen["data"] = data
        seen["actor"] = actor_context
        return ["inst-1"]

    monkeypatch.setattr(InstanceConfigService, "create_monitor_instance_by_node_mgmt", staticmethod(_create))
    response = APIClient().post(
        INTEGRATIONS_URL,
        {
            "monitor_object_id": obj.id,
            "monitor_plugin_id": plugin.id,
            "instances": [{"instance_name": "web", "node_ids": [node.id]}],
            "policy_group": {"join": False},
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["instance_ids"] == ["inst-1"]
    assert seen["actor"]["data_team_ids"] == [tenants.a.team.id]
    assert seen["data"]["instances"][0]["node_ids"] == [node.id]


def test_api_tenant_cannot_save_integration_for_other_org_node(tenants, monkeypatch):
    obj = _object("host")
    plugin = _plugin(obj)
    node = _node(tenants.b.team.id)
    called = {"value": False}

    def _create(data, actor_context=None):
        called["value"] = True
        return []

    monkeypatch.setattr(InstanceConfigService, "create_monitor_instance_by_node_mgmt", staticmethod(_create))
    response = APIClient().post(
        INTEGRATIONS_URL,
        {
            "monitor_object_id": obj.id,
            "monitor_plugin_id": plugin.id,
            "instances": [{"instance_name": "web", "node_ids": [node.id]}],
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "节点不存在"
    assert called["value"] is False


def test_api_tenant_can_delete_own_integration(tenants, monkeypatch):
    obj = _object("host")
    own = MonitorInstance.objects.create(id=f"inst-del-{uuid.uuid4().hex[:6]}", name="own", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=own, organization=tenants.a.team.id)
    seen = {}
    original = MonitorInstanceRemovalService.remove

    def _remove(instance_ids, **kwargs):
        seen["ids"] = list(instance_ids)
        seen["kwargs"] = kwargs
        return original(instance_ids, **kwargs)

    monkeypatch.setattr(MonitorInstanceRemovalService, "remove", _remove)
    response = APIClient().delete(
        INTEGRATIONS_URL,
        {"instance_ids": [own.id]},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["instance_ids"] == [own.id]
    assert seen["ids"] == [own.id]
    assert seen["kwargs"]["operator"] == tenants.a.user.username
    assert seen["kwargs"]["reason"] == "manual_instance_deleted"
    assert not MonitorInstance.objects.filter(id=own.id).exists()


def test_api_tenant_cannot_delete_other_org_integration(tenants, monkeypatch):
    obj = _object("host")
    other = MonitorInstance.objects.create(id=f"inst-other-{uuid.uuid4().hex[:6]}", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=tenants.b.team.id)
    called = {"value": False}

    def _remove(*args, **kwargs):
        called["value"] = True

    monkeypatch.setattr(MonitorInstanceRemovalService, "remove", _remove)
    response = APIClient().delete(
        INTEGRATIONS_URL,
        {"instance_ids": [other.id]},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "监控实例不存在"
    assert called["value"] is False
    assert MonitorInstance.objects.filter(id=other.id).exists()


def test_delete_integration_keeps_own_instance_when_batch_includes_other_org(tenants, monkeypatch):
    obj = _object("host")
    own = MonitorInstance.objects.create(id=f"inst-keep-{uuid.uuid4().hex[:6]}", name="own", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=own, organization=tenants.a.team.id)
    other = MonitorInstance.objects.create(id=f"inst-mix-{uuid.uuid4().hex[:6]}", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=tenants.b.team.id)
    called = {"value": False}

    def _remove(*args, **kwargs):
        called["value"] = True

    monkeypatch.setattr(MonitorInstanceRemovalService, "remove", _remove)
    response = APIClient().delete(
        INTEGRATIONS_URL,
        {"instance_ids": [own.id, other.id]},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "监控实例不存在"
    assert called["value"] is False
    assert MonitorInstance.objects.filter(id__in=[own.id, other.id]).count() == 2


def test_delete_integration_forged_team_is_rejected(tenants):
    response = APIClient().delete(
        INTEGRATIONS_URL,
        {"instance_ids": ["inst-x"], "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_create_kubernetes_collector(tenants, monkeypatch):
    obj = _object("k8s")
    seen = {}

    def _create(data, actor_context=None, allow_flow_fields=False):
        seen["organizations"] = data["organizations"]
        return {"instance_id": "('cluster',)"}

    monkeypatch.setattr(ManualCollectService, "create_manual_collect_instance", staticmethod(_create))
    response = APIClient().post(
        CLUSTER_URL,
        {
            "collector_type": "kubernetes",
            "monitor_object_id": obj.id,
            "name": "cluster",
            "instance_id": "cluster",
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert seen["organizations"] == [tenants.a.team.id]


def test_api_tenant_cannot_generate_other_org_cluster_command(tenants, monkeypatch):
    obj = _object("k8s")
    other = MonitorInstance.objects.create(id=f"('k8s-{uuid.uuid4().hex[:6]}',)", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=tenants.b.team.id)
    called = {"value": False}

    def _command(*args, **kwargs):
        called["value"] = True
        return "kubectl apply"

    monkeypatch.setattr(ManualCollectService, "generate_install_command", staticmethod(_command))
    response = APIClient().post(
        CLUSTER_COMMAND_URL,
        {"collector_type": "kubernetes", "instance_id": other.id, "cloud_region_id": 1},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "采集实例不存在"
    assert called["value"] is False


def test_cluster_command_rejects_k3s_tolerations(tenants):
    response = APIClient().post(
        CLUSTER_COMMAND_URL,
        {
            "collector_type": "k3s",
            "instance_id": "cluster-a",
            "cloud_region_id": 1,
            "tolerations": [{"key": "dedicated"}],
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_cannot_read_other_org_cluster_status(tenants, monkeypatch):
    obj = _object("k8s")
    other = MonitorInstance.objects.create(id=f"('k8s-{uuid.uuid4().hex[:6]}',)", name="other", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=other, organization=tenants.b.team.id)
    called = {"value": False}

    def _check(object_id, instance_id):
        called["value"] = True
        return True

    monkeypatch.setattr(ManualCollectService, "check_collect_status", staticmethod(_check))
    response = APIClient().get(
        CLUSTER_STATUS_URL,
        {"collector_type": "kubernetes", "instance_id": other.id, "monitor_object_id": obj.id},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "采集实例不存在"
    assert called["value"] is False
