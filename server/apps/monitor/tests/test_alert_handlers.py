"""监控策略 / 告警 handlers 序列化。"""

import pytest

from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy, PolicyOrganization
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.system_mgmt.models import Group, User

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


@pytest.fixture
def grant_all(mocker):
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )


def _policy(**overrides):
    obj = MonitorObject.objects.create(name="HandlerPolicyObj", level="base")
    values = {
        "monitor_object": obj,
        "name": "handler-policy",
        "algorithm": "max",
        "query_condition": {},
        "source": {},
        "group_by": [],
    }
    values.update(overrides)
    policy = MonitorPolicy.objects.create(organizations=[1], **values)
    PolicyOrganization.objects.create(policy=policy, organization=1)
    return policy


def test_policy_serializer_exposes_and_persists_handlers():
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
    )
    policy = _policy()
    serializer = MonitorPolicySerializer(
        policy,
        data={"handlers": [user.id]},
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    policy.refresh_from_db()

    assert policy.handlers == [user.id]
    assert MonitorPolicySerializer(policy).data["handlers"] == [user.id]


def test_policy_serializer_defaults_handlers_to_empty_list():
    policy = _policy()

    assert policy.handlers == []
    assert MonitorPolicySerializer(policy).data["handlers"] == []


def test_alert_list_exposes_handlers_and_display(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
    )
    policy = _policy()
    MonitorAlert.objects.create(
        policy_id=policy.id,
        organizations=[1],
        monitor_instance_id="h1",
        status="new",
        handlers=[user.id],
        content="memory high",
    )
    api_client.cookies["current_team"] = "1"

    resp = api_client.get(
        f"{BASE}/api/monitor_alert/",
        {"status_in": "new", "page": 1, "page_size": 20},
    )

    assert resp.status_code == 200
    result = resp.json()["data"]["results"][0]
    assert result["handlers"] == [user.id]
    assert result["handlers_display"] == ["处理人甲(handler1)"]
