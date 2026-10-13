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
    MonitorPolicy,
    PolicyOrganization,
)
from apps.monitor.services.metrics import Metrics
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
        _grant(system_user, "monitor", ["object-View", "asset-View", "strategy_list-View", "view_list-View"])
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
