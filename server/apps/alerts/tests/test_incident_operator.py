"""Incident 社区版状态机覆盖测试。"""

import pytest

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models.models import Incident
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.service.incident_operator import IncidentOperator


def _make_incident(incident_id="I1", status=IncidentStatus.PENDING):
    return Incident.objects.create(
        incident_id=incident_id,
        level="0",
        title="事故",
        fingerprint="fp",
        status=status,
    )


@pytest.mark.django_db
def test_acknowledge_pending_to_processing():
    _make_incident(status=IncidentStatus.PENDING)
    result = IncidentOperator(user="u1").operate("acknowledge", "I1", {})
    assert result["result"] is True
    incident = Incident.objects.get(incident_id="I1")
    assert incident.status == IncidentStatus.PROCESSING
    assert OperatorLog.objects.filter(operator_object="事故处理-确认").exists()


@pytest.mark.django_db
def test_acknowledge_wrong_status_fails():
    _make_incident(status=IncidentStatus.CLOSED)
    assert (
        IncidentOperator(user="u1").operate("acknowledge", "I1", {})["result"]
        is False
    )


@pytest.mark.django_db
def test_close_processing_to_closed():
    _make_incident(status=IncidentStatus.PROCESSING)
    result = IncidentOperator(user="u1").operate("close", "I1", {})
    assert result["result"] is True
    assert Incident.objects.get(incident_id="I1").status == IncidentStatus.CLOSED


@pytest.mark.django_db
def test_close_wrong_status_fails():
    _make_incident(status=IncidentStatus.PENDING)
    assert IncidentOperator(user="u1").operate("close", "I1", {})["result"] is False


@pytest.mark.django_db
def test_reopen_closed_to_processing():
    _make_incident(status=IncidentStatus.CLOSED)
    result = IncidentOperator(user="u1").operate("reopen", "I1", {})
    assert result["result"] is True
    assert (
        Incident.objects.get(incident_id="I1").status
        == IncidentStatus.PROCESSING
    )


@pytest.mark.django_db
def test_operate_unknown_action():
    _make_incident()
    result = IncidentOperator(user="u1").operate("teleport", "I1", {})
    assert result["result"] is False
    assert "不支持" in result["message"]


@pytest.mark.django_db
def test_operate_not_allowed_incident():
    _make_incident()
    result = IncidentOperator(
        user="u1",
        allowed_incident_ids=["I999"],
    ).operate("acknowledge", "I1", {})
    assert result["result"] is False
    assert "权限" in result["message"]


@pytest.mark.django_db
def test_operate_nonexistent_incident():
    result = IncidentOperator(user="u1").operate("acknowledge", "missing", {})
    assert result["result"] is False
    assert "不存在" in result["message"]


def test_is_incident_allowed_none_allows_all():
    assert IncidentOperator(
        user="u1",
        allowed_incident_ids=None,
    )._is_incident_allowed("anything")
