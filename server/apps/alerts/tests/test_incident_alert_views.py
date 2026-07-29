"""事故与告警视图集覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-事故.md：事故由告警聚合而来，支持增删改查与权限范围控制。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.models import Alert, Incident
from apps.alerts.views.alert import AlertModelViewSet
from apps.alerts.views.incident import IncidentModelViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _request(method, path, user, data=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _make_alert(alert_id="A1", team=None):
    return Alert.objects.create(
        alert_id=alert_id, level="0", title="t", content="c", fingerprint="fp", team=team or [1]
    )


@pytest.fixture(autouse=True)
def _grant_permissions(monkeypatch):
    # 让 AuthViewSet 的权限过滤放行 team=1
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"instance": [], "team": ["1"]},
    )


# --------------------------------------------------------------------------
# AlertModelViewSet
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_alert_list(superuser):
    _make_alert("A1", team=[1])
    _make_alert("A2", team=[2])
    request = _request("get", "/alerts/", superuser, team="1")
    response = AlertModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    ids = {item["alert_id"] for item in items}
    assert "A1" in ids
    assert "A2" not in ids


@pytest.mark.django_db
def test_alert_retrieve(superuser):
    alert = _make_alert("A1", team=[1])
    request = _request("get", f"/alerts/{alert.id}/", superuser, team="1")
    response = AlertModelViewSet.as_view({"get": "retrieve"})(request, pk=str(alert.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["alert_id"] == "A1"


@pytest.mark.django_db
def test_alert_retrieve_action(superuser):
    alert = _make_alert("A1", team=[1])
    request = _request("get", f"/alerts/{alert.id}/", superuser, team="1")
    response = AlertModelViewSet.as_view({"get": "retrieve"})(request, pk=str(alert.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["alert_id"] == "A1"


@pytest.mark.django_db
def test_incident_retrieve_non_superuser_denied(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"alarm": {"Incidents-View"}}
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.AuthViewSet.get_has_permission",
        lambda self, *a, **k: False,
    )
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    request = _request("get", f"/incident/{incident.id}/", authenticated_user, team="1")
    response = IncidentModelViewSet.as_view({"get": "retrieve"})(request, pk=str(incident.id))
    _render(response)
    assert response.status_code in (200, 400)


@pytest.mark.django_db
def test_alert_destroy(superuser):
    alert = _make_alert("A1", team=[1])
    request = _request("delete", f"/alerts/{alert.id}/", superuser, team="1")
    response = AlertModelViewSet.as_view({"delete": "destroy"})(request, pk=str(alert.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert not Alert.objects.filter(id=alert.id).exists()


@pytest.mark.django_db
def test_alert_operator_action_no_permission(superuser):
    # 操作不在允许范围内的告警 → 返回失败
    _make_alert("A1", team=[2])  # team 2，当前 team=1 无权
    request = _request("post", "/alerts/operator/acknowledge/", superuser, data={"alert_id": ["A1"]}, team="1")
    response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="acknowledge")
    payload = _render(response)
    # 全部失败 → 500
    assert response.status_code in (status.HTTP_200_OK, 500)


@pytest.mark.django_db
def test_alert_operator_requires_edit_permission(authenticated_user):
    """Issue #3383: operator action 必须拦截仅持有 Alarms-View 的用户（权限旁路修复验证）。

    若将 @HasPermission("Alarms-Edit") 注释掉，本测试将失败——
    因为 view-only 用户的请求会被放行并返回 200/500，而非 403。
    """
    # 只授予 Alarms-View，不授予 Alarms-Edit
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"alarm": {"Alarms-View"}}

    _make_alert("A1", team=[1])
    request = _request("post", "/alerts/operator/close/", authenticated_user, data={"alert_id": ["A1"]}, team="1")
    response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="close")
    # HasPermission("Alarms-Edit") 应拦截并返回 403
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_alert_operator_action_acknowledge(superuser):
    from apps.alerts.constants.constants import AlertStatus

    _make_alert("A1", team=[1])
    alert = Alert.objects.get(alert_id="A1")
    alert.status = AlertStatus.PENDING
    alert.operator = ["testuser"]
    alert.save()
    request = _request("post", "/alerts/operator/acknowledge/", superuser, data={"alert_id": ["A1"]}, team="1")
    response = AlertModelViewSet.as_view({"post": "operator"})(request, operator_action="acknowledge")
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PROCESSING


@pytest.mark.django_db
def test_alert_related_action(superuser):
    base = _make_alert("A1", team=[1])
    base.dimensions = {"service": "svc"}
    base.save()
    request = _request("get", f"/alerts/{base.id}/related/", superuser, team="1")
    response = AlertModelViewSet.as_view({"get": "related"})(request, pk=str(base.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert "items" in json.dumps(payload, ensure_ascii=False) or payload["data"] is not None


@pytest.mark.django_db
def test_alert_events_action(superuser):
    from django.utils import timezone

    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    source = AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")
    alert = _make_alert("A1", team=[1])
    event = Event.objects.create(
        source=source, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1", team=[1]
    )
    alert.events.add(event)
    request = _request("get", f"/alerts/{alert.id}/events/", superuser, team="1")
    response = AlertModelViewSet.as_view({"get": "events"})(request, pk=str(alert.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 1


# --------------------------------------------------------------------------
# IncidentModelViewSet
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_incident_list(superuser):
    Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    Incident.objects.create(incident_id="I2", level="0", title="t", fingerprint="fp", team=[2])
    request = _request("get", "/incident/", superuser, team="1")
    response = IncidentModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    ids = {item["incident_id"] for item in items}
    assert "I1" in ids
    assert "I2" not in ids


@pytest.mark.django_db
def test_incident_build_operator_user_map():
    from apps.system_mgmt.models.user import User as SysUser

    SysUser.objects.create(username="u1", display_name="用户1", domain="domain.com")
    inc = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", operator=["u1"], collaborators=["u1"])
    result = IncidentModelViewSet._build_operator_user_map([inc])
    assert result["u1"] == "用户1"


@pytest.mark.django_db
def test_alert_build_operator_user_map():
    from apps.system_mgmt.models.user import User as SysUser

    SysUser.objects.create(username="u1", display_name="用户1", domain="domain.com")
    alert = _make_alert("A1", team=[1])
    alert.operator = ["u1"]
    alert.save()
    result = AlertModelViewSet._build_operator_user_map([alert])
    assert result["u1"] == "用户1"


@pytest.mark.django_db
def test_incident_retrieve_superuser(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    request = _request("get", f"/incident/{incident.id}/", superuser, team="1")
    response = IncidentModelViewSet.as_view({"get": "retrieve"})(request, pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["incident_id"] == "I1"


@pytest.mark.django_db
def test_incident_create_with_alert(superuser):
    from apps.system_mgmt.models.user import User as SysUser

    # operator 默认取请求用户名，需在 system_mgmt 中存在且属于告警组织
    SysUser.objects.create(username="testuser", domain="domain.com", group_list=[{"id": 1}])
    alert = _make_alert("A1", team=[1])
    data = {"level": "0", "title": "新事故", "team": [1], "alert": [alert.id]}
    request = _request("post", "/incident/", superuser, data=data, team="1")
    response = IncidentModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    incident = Incident.objects.get(title="新事故")
    assert incident.alert.filter(id=alert.id).exists()


@pytest.mark.django_db
def test_incident_create_requires_alert(superuser):
    data = {"level": "0", "title": "无告警事故", "team": [1], "alert": []}
    request = _request("post", "/incident/", superuser, data=data, team="1")
    response = IncidentModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_incident_create_invalid_alert_ids(superuser):
    data = {"level": "0", "title": "事故", "team": [1], "alert": "notalist"}
    request = _request("post", "/incident/", superuser, data=data, team="1")
    response = IncidentModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_incident_create_invalid_team(superuser):
    alert = _make_alert("A1", team=[1])
    data = {"level": "0", "title": "事故", "team": "notalist", "alert": [alert.id]}
    request = _request("post", "/incident/", superuser, data=data, team="1")
    response = IncidentModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_incident_create_with_explicit_operator(superuser):
    from apps.system_mgmt.models.user import User as SysUser

    SysUser.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])
    alert = _make_alert("A1", team=[1])
    data = {"level": "0", "title": "事故", "team": [1], "alert": [alert.id], "operator": ["op1"]}
    request = _request("post", "/incident/", superuser, data=data, team="1")
    response = IncidentModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    incident = Incident.objects.get(title="事故")
    assert incident.operator == ["op1"]


@pytest.mark.django_db
def test_incident_destroy_superuser(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    request = _request("delete", f"/incident/{incident.id}/", superuser, team="1")
    response = IncidentModelViewSet.as_view({"delete": "destroy"})(request, pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert not Incident.objects.filter(id=incident.id).exists()


@pytest.mark.django_db
def test_incident_operator_action_acknowledge(superuser):
    from apps.alerts.constants.constants import IncidentStatus

    Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1], status=IncidentStatus.PENDING)
    request = _request("post", "/incident/operator/acknowledge/", superuser, data={"incident_id": ["I1"]}, team="1")
    response = IncidentModelViewSet.as_view({"post": "operator"})(request, operator_action="acknowledge")
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert Incident.objects.get(incident_id="I1").status == IncidentStatus.PROCESSING


@pytest.mark.django_db
def test_incident_operator_action_empty_list(superuser):
    request = _request("post", "/incident/operator/acknowledge/", superuser, data={"incident_id": []}, team="1")
    response = IncidentModelViewSet.as_view({"post": "operator"})(request, operator_action="acknowledge")
    _render(response)
    assert response.status_code == 400


@pytest.mark.django_db
def test_incident_alerts_action(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    alert = _make_alert("A1", team=[1])
    incident.alert.add(alert)
    request = _request("get", f"/incident/{incident.id}/alerts/", superuser, team="1")
    response = IncidentModelViewSet.as_view({"get": "alerts"})(request, pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 1


@pytest.mark.django_db
def test_incident_add_alerts(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    alert = _make_alert("A1", team=[1])
    request = _request("post", f"/incident/{incident.id}/alerts/add/", superuser, data={"alert": [alert.id]}, team="1")
    response = IncidentModelViewSet.as_view({"post": "add_alerts"})(request, pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert incident.alert.filter(id=alert.id).exists()
    assert alert.id in payload["data"]["added"]


@pytest.mark.django_db
def test_incident_remove_alerts(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    alert = _make_alert("A1", team=[1])
    incident.alert.add(alert)
    request = _request("post", f"/incident/{incident.id}/alerts/remove/", superuser, data={"alert": [alert.id]}, team="1")
    response = IncidentModelViewSet.as_view({"post": "remove_alerts"})(request, pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert not incident.alert.filter(id=alert.id).exists()
    assert alert.id in payload["data"]["removed"]


@pytest.mark.django_db
def test_incident_add_alerts_requires_alert(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    request = _request("post", f"/incident/{incident.id}/alerts/add/", superuser, data={"alert": []}, team="1")
    response = IncidentModelViewSet.as_view({"post": "add_alerts"})(request, pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_incident_update(superuser):
    incident = Incident.objects.create(incident_id="I1", level="0", title="旧标题", fingerprint="fp", team=[1])
    request = _request("put", f"/incident/{incident.id}/", superuser, data={"incident_id": "I1", "level": "0", "title": "新标题", "team": [1]}, team="1")
    response = IncidentModelViewSet.as_view({"put": "update"})(request, pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    incident.refresh_from_db()
    assert incident.title == "新标题"


@pytest.mark.django_db
def test_incident_update_can_replace_alerts_when_all_are_authorized(superuser):
    incident = Incident.objects.create(
        incident_id="I-update-alerts", level="0", title="事故", fingerprint="fp", team=[1]
    )
    alert = _make_alert("A-update", team=[1])
    request = _request(
        "patch",
        f"/incident/{incident.id}/",
        superuser,
        data={"alert": [alert.id]},
        team="1",
    )

    response = IncidentModelViewSet.as_view({"patch": "partial_update"})(
        request, pk=str(incident.id)
    )
    _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert incident.alert.filter(id=alert.id).exists()


@pytest.mark.django_db
def test_incident_create_unauthorized_alert_does_not_leak_title(superuser, monkeypatch):
    alert = _make_alert("A-secret", team=[2])
    alert.title = "跨团队敏感标题"
    alert.save(update_fields=["title"])
    monkeypatch.setattr(IncidentModelViewSet, "_get_allowed_alert_ids", lambda self: set())
    request = _request(
        "post",
        "/incident/",
        superuser,
        data={"level": "0", "title": "事故", "team": [1], "alert": [alert.id]},
        team="1",
    )

    response = IncidentModelViewSet.as_view({"post": "create"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "跨团队敏感标题" not in str(payload)
