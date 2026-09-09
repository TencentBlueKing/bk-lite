"""日志策略 / 告警 handlers 序列化。"""

import json

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models.policy import Alert, Policy, PolicyOrganization
from apps.log.serializers.policy import PolicySerializer
from apps.log.views.policy import AlertViewSet
from apps.system_mgmt.models import Group, User

pytestmark = pytest.mark.django_db


def _policy(**overrides):
    values = {
        "name": "handler-policy",
        "alert_type": "keyword",
        "alert_name": "handler-policy",
        "alert_level": "warning",
        "alert_condition": {"query": "error"},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "notice": False,
    }
    values.update(overrides)
    policy = Policy.objects.create(**values)
    PolicyOrganization.objects.create(policy=policy, organization=1)
    return policy


def _request(user, path="/api/v1/log/alert/"):
    request = APIRequestFactory().get(path)
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def grant_all(authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    return authenticated_user


def test_policy_serializer_exposes_and_persists_handlers():
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
    )
    policy = _policy()
    serializer = PolicySerializer(policy, data={"handlers": [user.id]}, partial=True)

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    policy.refresh_from_db()

    assert policy.handlers == [user.id]
    assert PolicySerializer(policy).data["handlers"] == [user.id]


def test_policy_serializer_defaults_handlers_to_empty_list():
    policy = _policy()

    assert policy.handlers == []
    assert PolicySerializer(policy).data["handlers"] == []


def test_alert_list_exposes_handlers_and_display(grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
    )
    policy = _policy()
    Alert.objects.create(
        id="handler-alert-1",
        policy=policy,
        source_id="src-1",
        level="warning",
        status="new",
        start_event_time=timezone.now(),
        organizations=[1],
        handlers=[user.id],
    )

    listed = AlertViewSet.as_view({"get": "list"})(_request(grant_all))

    assert listed.status_code == 200
    item = json.loads(listed.content)["data"]["items"][0]
    assert item["handlers"] == [user.id]
    assert item["handlers_display"] == ["处理人甲(handler1)"]
