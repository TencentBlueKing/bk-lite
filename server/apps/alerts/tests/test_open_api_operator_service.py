from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.models import Alert
from apps.alerts.open_api.auth import AlertsOpenAPIContext
from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.open_api.services import AlertsOpenAPIService


def _context(*, team_id=1, username="api-user", is_superuser=True, permissions=None):
    alarm_perms = {"Alarms-View", "Alarms-Edit"} if permissions is None else permissions
    user = SimpleNamespace(
        username=username,
        group_list=[{"id": team_id}],
        permission={"alarm": set(alarm_perms)},
        is_superuser=is_superuser,
        locale="zh-CN",
        domain="default",
    )
    return AlertsOpenAPIContext(user=user, team_id=team_id)


def _service(*, team_id=1, username="api-user", is_superuser=True, permissions=None):
    return AlertsOpenAPIService(_context(team_id=team_id, username=username, is_superuser=is_superuser, permissions=permissions))


def _create_alert(*, alert_id, team=None, status=AlertStatus.UNASSIGNED, operator=None, session_status=""):
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title=f"title-{alert_id}",
        content="content",
        fingerprint=f"fp-{alert_id}",
        team=team if team is not None else [1],
        status=status,
        operator=operator if operator is not None else [],
        session_status=session_status,
    )


@pytest.mark.django_db
@patch("apps.alerts.action.engine.ActionEngine.dispatch_async")
@patch("apps.alerts.common.notify.dispatcher.enqueue_notifications")
@patch("apps.alerts.service.alter_operator.validate_alert_assignees")
def test_operate_alert_assign_success(mock_validate, _mock_notify, _mock_dispatch):
    mock_validate.return_value = (["api-user"], None)
    alert = _create_alert(alert_id="A-assign", status=AlertStatus.UNASSIGNED)

    result = _service().operate_alert("A-assign", "assign", {"assignee": ["api-user"]})

    assert result["alert_id"] == "A-assign"
    assert result["status"] == AlertStatus.PENDING
    assert result["operator"] == ["api-user"]
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING
    assert alert.operator == ["api-user"]


@pytest.mark.django_db
def test_operate_alert_acknowledge_wrong_state():
    _create_alert(alert_id="A-wrong-state", status=AlertStatus.PROCESSING, operator=["api-user"])

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service().operate_alert("A-wrong-state", "acknowledge", {})

    assert exc.value.code == "alerts.operator.invalid_state"
    assert exc.value.status_code == 409
    assert "无法进行" in exc.value.message


@pytest.mark.django_db
def test_operate_alert_acknowledge_not_assignee():
    _create_alert(alert_id="A-not-assignee", status=AlertStatus.PENDING, operator=["other-user"])

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service().operate_alert("A-not-assignee", "acknowledge", {})

    assert exc.value.code == "alerts.operator.not_assignee"
    assert exc.value.status_code == 403
    assert "没有权限认领" in exc.value.message


@pytest.mark.django_db
def test_operate_alert_other_team_not_found():
    _create_alert(alert_id="A-other-team", team=[2], status=AlertStatus.PENDING, operator=["api-user"])

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service(team_id=1).operate_alert("A-other-team", "acknowledge", {})

    assert exc.value.code == "alerts.alert.not_found"
    assert exc.value.status_code == 404


@pytest.mark.django_db
@patch("apps.alerts.action.engine.ActionEngine.dispatch_async")
def test_operate_alert_api_close_pending_without_assignee(_mock_dispatch):
    _create_alert(alert_id="A-api-close-pending", status=AlertStatus.PENDING, operator=["other-user"])

    result = _service().operate_alert("A-api-close-pending", "close", {"reason": "自动化关闭"})

    assert result["alert_id"] == "A-api-close-pending"
    assert result["status"] == AlertStatus.CLOSED
    assert Alert.objects.get(alert_id="A-api-close-pending").status == AlertStatus.CLOSED


@pytest.mark.django_db
@patch("apps.alerts.action.engine.ActionEngine.dispatch_async")
def test_operate_alert_api_close_processing_without_assignee(_mock_dispatch):
    _create_alert(alert_id="A-api-close-processing", status=AlertStatus.PROCESSING, operator=["other-user"])

    result = _service().operate_alert("A-api-close-processing", "close", {})

    assert result["status"] == AlertStatus.CLOSED


@pytest.mark.django_db
def test_operate_alert_api_close_rejects_unassigned():
    _create_alert(alert_id="A-api-close-unassigned", status=AlertStatus.UNASSIGNED, operator=["other-user"])

    with pytest.raises(AlertsOpenAPIError) as exc:
        _service().operate_alert("A-api-close-unassigned", "close", {})

    assert exc.value.code == "alerts.operator.invalid_state"
    assert exc.value.status_code == 409
