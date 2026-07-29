"""告警分派/屏蔽策略视图集覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：分派与屏蔽策略支持增删改查，操作写入操作日志。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_operator import AlertAssignment, AlertShield
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.views.assignment_shield import AlertAssignmentModelViewSet, AlertShieldModelViewSet


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# --------------------------------------------------------------------------
# AlertAssignment
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_assignment_create_writes_log(superuser):
    data = {
        "name": "分派策略1",
        "match_type": "all",
        "match_rules": [],
        "personnel": [],
        "notify_channels": [],
        "notification_scenario": [],
        "config": {},
        "notification_frequency": {},
    }
    request = _request("post", "/assignment/", superuser, data=data)
    response = AlertAssignmentModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert AlertAssignment.objects.filter(name="分派策略1").exists()
    assert OperatorLog.objects.filter(operator_object="告警分派策略-创建").exists()


@pytest.mark.django_db
def test_assignment_list(superuser):
    AlertAssignment.objects.create(name="a1", match_type="all")
    request = _request("get", "/assignment/", superuser)
    response = AlertAssignmentModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 1


@pytest.mark.django_db
def test_assignment_update_writes_log(superuser):
    obj = AlertAssignment.objects.create(name="a1", match_type="all")
    data = {
        "name": "a1-updated",
        "match_type": "all",
        "match_rules": [],
        "personnel": [],
        "notify_channels": [],
        "notification_scenario": [],
        "config": {},
        "notification_frequency": {},
    }
    request = _request("put", f"/assignment/{obj.id}/", superuser, data=data)
    response = AlertAssignmentModelViewSet.as_view({"put": "update"})(request, pk=str(obj.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    obj.refresh_from_db()
    assert obj.name == "a1-updated"
    assert OperatorLog.objects.filter(operator_object="告警分派策略-修改").exists()


@pytest.mark.django_db
def test_assignment_destroy_writes_log(superuser):
    obj = AlertAssignment.objects.create(name="a1", match_type="all")
    request = _request("delete", f"/assignment/{obj.id}/", superuser)
    response = AlertAssignmentModelViewSet.as_view({"delete": "destroy"})(request, pk=str(obj.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert not AlertAssignment.objects.filter(id=obj.id).exists()
    assert OperatorLog.objects.filter(operator_object="告警分派策略-删除").exists()


# --------------------------------------------------------------------------
# AlertShield
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_shield_create_writes_log(superuser):
    data = {
        "name": "屏蔽策略1",
        "match_type": "all",
        "match_rules": [],
        "suppression_time": {},
    }
    request = _request("post", "/shield/", superuser, data=data)
    response = AlertShieldModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert AlertShield.objects.filter(name="屏蔽策略1").exists()
    assert OperatorLog.objects.filter(operator_object="告警屏蔽策略-创建").exists()


@pytest.mark.django_db
def test_shield_update_and_destroy(superuser):
    obj = AlertShield.objects.create(name="s1", match_type="all")
    update_data = {"name": "s1-updated", "match_type": "all", "match_rules": [], "suppression_time": {}}
    req_u = _request("put", f"/shield/{obj.id}/", superuser, data=update_data)
    resp_u = AlertShieldModelViewSet.as_view({"put": "update"})(req_u, pk=str(obj.id))
    _render(resp_u)
    assert resp_u.status_code == status.HTTP_200_OK

    req_d = _request("delete", f"/shield/{obj.id}/", superuser)
    resp_d = AlertShieldModelViewSet.as_view({"delete": "destroy"})(req_d, pk=str(obj.id))
    _render(resp_d)
    assert resp_d.status_code == status.HTTP_200_OK
    assert not AlertShield.objects.filter(id=obj.id).exists()
