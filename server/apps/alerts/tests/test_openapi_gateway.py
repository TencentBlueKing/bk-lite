"""统一 OpenAPI 网关：告警中心双租户契约。"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.models.operator_log import OperatorLog
from apps.base.models import User, UserAPISecret
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

LIST_URL = "/openapi/v1/alerts/list"
DETAIL_URL = "/openapi/v1/alerts/detail"
EVENTS_URL = "/openapi/v1/alerts/events"
ASSIGN_URL = "/openapi/v1/alerts/assign"
ACK_URL = "/openapi/v1/alerts/acknowledge"
REASSIGN_URL = "/openapi/v1/alerts/reassign"
CLOSE_URL = "/openapi/v1/alerts/close"
BATCH_URL = "/openapi/v1/alerts/batch-action"
SHIELD_CREATE_URL = "/openapi/v1/alerts/shield-create"
SHIELD_OPERATE_URL = "/openapi/v1/alerts/shield-operate"
SHIELD_URL = "/openapi/v1/alerts/shield"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant_alarm_perms(system_user):
    menu_specs = [
        ("Alarms-View", "Alarms View"),
        ("Alarms-Edit", "Alarms Edit"),
        ("shield_strategy-Add", "Shield Strategy Add"),
        ("shield_strategy-Edit", "Shield Strategy Edit"),
        ("shield_strategy-Delete", "Shield Strategy Delete"),
    ]
    menu_ids = []
    for name, display_name in menu_specs:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="alarm",
            defaults={"display_name": display_name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(
        name="openapi-alarm-operator",
        app="alarm",
        defaults={"menu_list": menu_ids},
    )
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])
    return role


def _make_tenant(*, team_name, username, domain):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(
        username=user.username,
        domain=user.domain,
        group_list=[team.id],
    )
    _grant_alarm_perms(system_user)
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
        a=_make_tenant(team_name="alerts-openapi-a", username="alerts-openapi-a", domain="a.test.com"),
        b=_make_tenant(team_name="alerts-openapi-b", username="alerts-openapi-b", domain="b.test.com"),
    )


def _create_alert(*, tenant, suffix, status=AlertStatus.PENDING, operator=None, resource_type="host", resource_id="host-1"):
    alert_id = f"ALERT-GW-{suffix}-{uuid.uuid4().hex[:8]}"
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title=f"title-{suffix}",
        content="content",
        fingerprint=uuid.uuid4().hex[:32],
        team=[tenant.team.id],
        status=status,
        operator=operator if operator is not None else [tenant.user.username],
        resource_type=resource_type,
        resource_id=resource_id,
    )


@pytest.fixture(autouse=True)
def _permission_rules_own_team():
    def _rules(user, current_team, app_name="alerts", permission_key="alert", include_children=False):
        del user, app_name, permission_key, include_children
        return {"team": [int(current_team)], "instance": []}

    def _validate(alert, usernames):
        del alert
        return list(usernames), None

    with (
        patch("apps.alerts.open_api.services.get_permission_rules", side_effect=_rules),
        patch("apps.alerts.service.alter_operator.validate_alert_assignees", side_effect=_validate),
        patch("apps.alerts.action.engine.ActionEngine.dispatch_async"),
        patch("apps.alerts.common.notify.dispatcher.enqueue_notifications"),
    ):
        yield


def test_api_tenant_can_list_own_org_alerts(tenants):
    own = _create_alert(tenant=tenants.a, suffix="own")
    _create_alert(tenant=tenants.b, suffix="other")

    response = APIClient().get(LIST_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    items = response.json()["data"]["items"]
    ids = {item["alert_id"] for item in items}
    assert own.alert_id in ids
    assert all("id" not in item for item in items)


def test_api_tenant_cannot_list_other_org_alerts(tenants):
    other = _create_alert(tenant=tenants.a, suffix="hidden")

    response = APIClient().get(LIST_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["alert_id"] for item in response.json()["data"]["items"]}
    assert other.alert_id not in ids


def test_list_forged_team_is_rejected(tenants):
    response = APIClient().get(
        LIST_URL,
        {"team": str(tenants.b.team.id)},
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_list_filters_resource_type_and_id(tenants):
    host = _create_alert(tenant=tenants.a, suffix="host", resource_type="host", resource_id="host-9")
    _create_alert(tenant=tenants.a, suffix="pod", resource_type="pod", resource_id="pod-9")

    response = APIClient().get(
        LIST_URL,
        {"resource_type": "host", "resource_id": "host-9"},
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    ids = {item["alert_id"] for item in response.json()["data"]["items"]}
    assert ids == {host.alert_id}


def test_list_clamps_page_size_to_gateway_limit(tenants):
    _create_alert(tenant=tenants.a, suffix="page")
    response = APIClient().get(LIST_URL, {"page_size": "999"}, **_auth(tenants.a.token))
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["page_size"] == 500


def test_api_tenant_can_read_own_alert(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="detail")
    response = APIClient().get(DETAIL_URL, {"alert_id": alert.alert_id}, **_auth(tenants.a.token))
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["alert_id"] == alert.alert_id
    assert "id" not in data
    assert "labels" in data


def test_api_tenant_cannot_read_other_org_alert(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="secret")
    response = APIClient().get(DETAIL_URL, {"alert_id": alert.alert_id}, **_auth(tenants.b.token))
    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"


def test_detail_forged_team_is_rejected(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="forged-detail")
    response = APIClient().get(
        DETAIL_URL,
        {"alert_id": alert.alert_id, "team": str(tenants.b.team.id)},
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_alert_events(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="events")
    source = AlertSource.objects.create(
        name=f"src-{uuid.uuid4().hex[:8]}",
        source_id=f"src-{uuid.uuid4().hex[:8]}",
        source_type="restful",
        secret="x",
    )
    event = Event.objects.create(
        source=source,
        raw_data={},
        title="event-1",
        level="0",
        event_id=f"E-{uuid.uuid4().hex[:8]}",
        start_time=timezone.now(),
    )
    alert.events.add(event)

    response = APIClient().get(EVENTS_URL, {"alert_id": alert.alert_id}, **_auth(tenants.a.token))
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["count"] == 1
    assert response.json()["data"]["items"][0]["event_id"] == event.event_id


def test_api_tenant_cannot_list_other_org_alert_events(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="events-hidden")
    response = APIClient().get(EVENTS_URL, {"alert_id": alert.alert_id}, **_auth(tenants.b.token))
    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"


def test_events_forged_team_is_rejected(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="events-forged")
    response = APIClient().get(
        EVENTS_URL,
        {"alert_id": alert.alert_id, "team": str(tenants.b.team.id)},
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_assign_own_alert(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="assign", status=AlertStatus.UNASSIGNED, operator=[])
    response = APIClient().post(
        ASSIGN_URL,
        {"alert_id": alert.alert_id, "assignee": [tenants.a.user.username]},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING
    assert tenants.a.user.username in alert.operator


def test_api_tenant_cannot_assign_other_org_alert(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="assign-other", status=AlertStatus.UNASSIGNED, operator=[])
    response = APIClient().post(
        ASSIGN_URL,
        {"alert_id": alert.alert_id, "assignee": [tenants.b.user.username]},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    alert.refresh_from_db()
    assert alert.status == AlertStatus.UNASSIGNED


def test_assign_forged_team_is_rejected(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="assign-forged", status=AlertStatus.UNASSIGNED, operator=[])
    response = APIClient().post(
        ASSIGN_URL,
        {"alert_id": alert.alert_id, "assignee": [tenants.a.user.username], "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_acknowledge_own_alert(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="ack",
        status=AlertStatus.PENDING,
        operator=[tenants.a.user.username],
    )
    response = APIClient().post(
        ACK_URL,
        {"alert_id": alert.alert_id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PROCESSING


def test_api_tenant_cannot_acknowledge_other_org_alert(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="ack-other",
        status=AlertStatus.PENDING,
        operator=[tenants.a.user.username],
    )
    response = APIClient().post(
        ACK_URL,
        {"alert_id": alert.alert_id},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING


def test_acknowledge_forged_team_is_rejected(tenants):
    response = APIClient().post(
        ACK_URL,
        {"alert_id": "ALERT-x", "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_reassign_own_alert(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="reassign",
        status=AlertStatus.PROCESSING,
        operator=[tenants.a.user.username],
    )
    response = APIClient().post(
        REASSIGN_URL,
        {"alert_id": alert.alert_id, "assignee": [tenants.a.user.username]},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()


def test_api_tenant_cannot_reassign_other_org_alert(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="reassign-other",
        status=AlertStatus.PROCESSING,
        operator=[tenants.a.user.username],
    )
    response = APIClient().post(
        REASSIGN_URL,
        {"alert_id": alert.alert_id, "assignee": [tenants.b.user.username]},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    alert.refresh_from_db()
    assert alert.operator == [tenants.a.user.username]


def test_reassign_forged_team_is_rejected(tenants):
    response = APIClient().post(
        REASSIGN_URL,
        {"alert_id": "ALERT-x", "assignee": ["u"], "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_close_own_pending_alert_without_assignee(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="close",
        status=AlertStatus.PENDING,
        operator=["someone-else"],
    )
    response = APIClient().post(
        CLOSE_URL,
        {"alert_id": alert.alert_id, "reason": "自动化关闭"},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    alert.refresh_from_db()
    assert alert.status == AlertStatus.CLOSED


def test_api_tenant_cannot_close_other_org_alert(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="close-other",
        status=AlertStatus.PENDING,
        operator=["someone-else"],
    )
    response = APIClient().post(
        CLOSE_URL,
        {"alert_id": alert.alert_id},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING


def test_close_forged_team_is_rejected(tenants):
    response = APIClient().post(
        CLOSE_URL,
        {"alert_id": "ALERT-x", "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_close_rejects_database_primary_key_anchor(tenants):
    alert = _create_alert(tenant=tenants.a, suffix="pk", status=AlertStatus.PENDING, operator=["x"])
    response = APIClient().post(
        CLOSE_URL,
        {"id": alert.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING


def test_api_tenant_can_batch_close_own_alerts(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="batch",
        status=AlertStatus.PROCESSING,
        operator=["someone-else"],
    )
    response = APIClient().post(
        BATCH_URL,
        {"action": "close", "alert_ids": [alert.alert_id]},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    assert alert.alert_id in response.json()["data"]["succeeded"]
    alert.refresh_from_db()
    assert alert.status == AlertStatus.CLOSED


def test_api_tenant_cannot_batch_close_other_org_alerts(tenants):
    alert = _create_alert(
        tenant=tenants.a,
        suffix="batch-other",
        status=AlertStatus.PROCESSING,
        operator=["someone-else"],
    )
    response = APIClient().post(
        BATCH_URL,
        {"action": "close", "alert_ids": [alert.alert_id]},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 200, response.json()
    assert alert.alert_id in [item["alert_id"] for item in response.json()["data"]["failed"]]
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PROCESSING


def test_batch_action_forged_team_is_rejected(tenants):
    response = APIClient().post(
        BATCH_URL,
        {"action": "close", "alert_ids": ["ALERT-x"], "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_system_token_all_scope_still_requires_alarms_view():
    from apps.core.openapi.tests.test_system_token_auth import _acting, _create_acting_user, _create_system_token

    user = _create_acting_user(210)
    token = _create_system_token(scope={"mode": "all"})
    response = APIClient().get(LIST_URL, **_acting(token, user, 210))
    assert response.status_code == 403, response.json()
    assert response.json()["code"] == "PERM_MISSING"
    assert response.json()["message"] == "permission denied"


def test_system_token_all_scope_admin_bypasses_alarms_menu():
    from apps.core.openapi.tests.test_system_token_auth import _acting, _create_acting_user, _create_system_token
    from apps.core.openapi.tests.test_system_token_permission import _grant_admin_role

    user = _create_acting_user(211)
    _grant_admin_role(user)
    token = _create_system_token(scope={"mode": "all"})
    response = APIClient().get(LIST_URL, **_acting(token, user, 211))
    assert response.status_code == 200, response.json()
    assert response.json()["result"] is True
    assert response.json()["data"]["count"] == 0


def test_system_token_alarm_admin_bypasses_empty_alarms_menu():
    from apps.core.openapi.tests.test_system_token_auth import _acting, _create_acting_user, _create_system_token

    user = _create_acting_user(212)
    role, _ = Role.objects.get_or_create(name="admin", app="alarm", defaults={"menu_list": []})
    if role.menu_list:
        role.menu_list = []
        role.save(update_fields=["menu_list"])
    SystemUser.objects.filter(username=user.username, domain=user.domain).update(role_list=[role.id])
    token = _create_system_token(scope={"mode": "all"})
    response = APIClient().get(LIST_URL, **_acting(token, user, 212))
    assert response.status_code == 200, response.json()
    assert response.json()["result"] is True
    assert response.json()["data"]["count"] == 0


def _shield_payload(name, **overrides):
    payload = {
        "name": name,
        "match_type": "all",
        "match_rules": [],
        "suppression_time": {"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _create_shield(*, tenant, name, is_active=True):
    return AlertShield.objects.create(
        name=name,
        match_type="all",
        match_rules=[],
        suppression_time={},
        is_active=is_active,
        created_by=tenant.user.username,
        domain=tenant.user.domain,
    )


def test_api_tenant_can_create_shield(tenants):
    name = f"shield-own-{uuid.uuid4().hex[:8]}"
    response = APIClient().post(
        SHIELD_CREATE_URL,
        _shield_payload(name),
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["name"] == name
    assert data["is_active"] is True
    assert "id" not in data
    shield = AlertShield.objects.get(name=name)
    assert shield.created_by == tenants.a.user.username
    assert OperatorLog.objects.filter(operator_object="告警屏蔽策略-创建", target_id=str(shield.id)).exists()


def test_api_tenant_create_shield_does_not_belong_to_other_org(tenants):
    name = f"shield-b-{uuid.uuid4().hex[:8]}"
    response = APIClient().post(
        SHIELD_CREATE_URL,
        _shield_payload(name),
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 200, response.json()
    shield = AlertShield.objects.get(name=name)
    assert shield.created_by == tenants.b.user.username
    assert shield.created_by != tenants.a.user.username


def test_shield_create_forged_team_is_rejected(tenants):
    name = f"shield-forged-{uuid.uuid4().hex[:8]}"
    payload = _shield_payload(name)
    payload["team"] = tenants.b.team.id
    response = APIClient().post(
        SHIELD_CREATE_URL,
        payload,
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert not AlertShield.objects.filter(name=name).exists()


def test_api_tenant_can_operate_own_shield(tenants):
    name = f"shield-op-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name, is_active=True)
    response = APIClient().post(
        SHIELD_OPERATE_URL,
        {"name": name, "is_active": False},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["is_active"] is False
    assert AlertShield.objects.get(name=name).is_active is False
    assert OperatorLog.objects.filter(operator_object="告警屏蔽策略-修改", overview=f"停用告警屏蔽策略[{name}]").exists()

    enable = APIClient().post(
        SHIELD_OPERATE_URL,
        {"name": name, "is_active": True},
        format="json",
        **_auth(tenants.a.token),
    )
    assert enable.status_code == 200, enable.json()
    assert enable.json()["data"]["is_active"] is True
    assert AlertShield.objects.get(name=name).is_active is True


def test_api_tenant_cannot_operate_other_org_shield(tenants):
    name = f"shield-op-hidden-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name, is_active=True)
    response = APIClient().post(
        SHIELD_OPERATE_URL,
        {"name": name, "is_active": False},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert AlertShield.objects.get(name=name).is_active is True


def test_shield_operate_forged_team_is_rejected(tenants):
    name = f"shield-op-forged-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().post(
        SHIELD_OPERATE_URL,
        {"name": name, "is_active": False, "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert AlertShield.objects.get(name=name).is_active is True


def test_api_tenant_can_update_own_shield(tenants):
    name = f"shield-upd-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().put(
        SHIELD_URL,
        {
            "name": name,
            "match_type": "filter",
            "match_rules": [[{"key": "title", "operator": "eq", "value": "cpu"}]],
            "suppression_time": {"type": "day", "start_time": "01:00:00", "end_time": "02:00:00"},
        },
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["match_type"] == "filter"
    assert data["match_rules"] == [[{"key": "title", "operator": "eq", "value": "cpu"}]]
    shield = AlertShield.objects.get(name=name)
    assert shield.match_type == "filter"
    assert OperatorLog.objects.filter(operator_object="告警屏蔽策略-修改", overview=f"修改告警屏蔽策略[{name}]").exists()


def test_api_tenant_cannot_update_other_org_shield(tenants):
    name = f"shield-upd-hidden-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().put(
        SHIELD_URL,
        {"name": name, "match_type": "all", "match_rules": [], "suppression_time": {}},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert AlertShield.objects.get(name=name).match_type == "all"


def test_shield_update_forged_team_is_rejected(tenants):
    name = f"shield-upd-forged-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().put(
        SHIELD_URL,
        {"name": name, "match_type": "all", "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_delete_own_shield(tenants):
    name = f"shield-own-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().delete(
        SHIELD_URL,
        {"name": name},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 200, response.json()
    assert response.json()["data"]["name"] == name
    assert "id" not in response.json()["data"]
    assert not AlertShield.objects.filter(name=name).exists()
    assert OperatorLog.objects.filter(operator_object="告警屏蔽策略-删除", overview=f"删除告警屏蔽策略[{name}]").exists()


def test_api_tenant_cannot_delete_other_org_shield(tenants):
    name = f"shield-hidden-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().delete(
        SHIELD_URL,
        {"name": name},
        format="json",
        **_auth(tenants.b.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert AlertShield.objects.filter(name=name).exists()


def test_shield_delete_forged_team_is_rejected(tenants):
    name = f"shield-forged-{uuid.uuid4().hex[:8]}"
    _create_shield(tenant=tenants.a, name=name)
    response = APIClient().delete(
        SHIELD_URL,
        {"name": name, "team": tenants.b.team.id},
        format="json",
        **_auth(tenants.a.token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
    assert AlertShield.objects.filter(name=name).exists()
