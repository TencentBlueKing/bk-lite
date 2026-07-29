"""事故操作状态机覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-事故.md：未分派→待响应→处理中→已关闭→重新打开到处理中。
"""

import uuid

import pytest

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup
from apps.alerts.models.models import Incident
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.service.incident_operator import IncidentOperator


def _make_incident(incident_id="I1", status=IncidentStatus.PENDING):
    return Incident.objects.create(incident_id=incident_id, level="0", title="事故", fingerprint="fp", status=status)


@pytest.mark.django_db
def test_acknowledge_pending_to_processing():
    _make_incident(status=IncidentStatus.PENDING)
    op = IncidentOperator(user="u1")
    result = op.operate("acknowledge", "I1", {})
    assert result["result"] is True
    incident = Incident.objects.get(incident_id="I1")
    assert incident.status == IncidentStatus.PROCESSING
    assert OperatorLog.objects.filter(operator_object="事故处理-确认").exists()


@pytest.mark.django_db
def test_acknowledge_wrong_status_fails():
    _make_incident(status=IncidentStatus.CLOSED)
    op = IncidentOperator(user="u1")
    result = op.operate("acknowledge", "I1", {})
    assert result["result"] is False


@pytest.mark.django_db
def test_close_processing_to_closed():
    _make_incident(status=IncidentStatus.PROCESSING)
    op = IncidentOperator(user="u1")
    result = op.operate("close", "I1", {})
    assert result["result"] is True
    assert Incident.objects.get(incident_id="I1").status == IncidentStatus.CLOSED


@pytest.mark.django_db
def test_close_wrong_status_fails():
    _make_incident(status=IncidentStatus.PENDING)
    op = IncidentOperator(user="u1")
    result = op.operate("close", "I1", {})
    assert result["result"] is False


@pytest.mark.django_db
def test_reopen_closed_to_processing():
    _make_incident(status=IncidentStatus.CLOSED)
    op = IncidentOperator(user="u1")
    result = op.operate("reopen", "I1", {})
    assert result["result"] is True
    assert Incident.objects.get(incident_id="I1").status == IncidentStatus.PROCESSING


@pytest.mark.django_db
def test_operate_unknown_action():
    _make_incident()
    op = IncidentOperator(user="u1")
    result = op.operate("teleport", "I1", {})
    assert result["result"] is False
    assert "不支持" in result["message"]


@pytest.mark.django_db
def test_operate_not_allowed_incident():
    _make_incident()
    op = IncidentOperator(user="u1", allowed_incident_ids=["I999"])
    result = op.operate("acknowledge", "I1", {})
    assert result["result"] is False
    assert "权限" in result["message"]


@pytest.mark.django_db
def test_operate_nonexistent_incident():
    op = IncidentOperator(user="u1")
    result = op.operate("acknowledge", "missing", {})
    assert result["result"] is False
    assert "不存在" in result["message"]


@pytest.mark.django_db
def test_is_incident_allowed_none_allows_all():
    op = IncidentOperator(user="u1", allowed_incident_ids=None)
    assert op._is_incident_allowed("anything") is True


def _make_im_group(incident, **overrides):
    values = {
        "incident": incident,
        "provider_key": "feishu",
        "channel_name_snapshot": "测试飞书",
        "member_id_type": "open_id",
        "group_name": "事故群",
        "external_chat_id": "oc_test",
        "status": IncidentIMGroup.Status.ACTIVE,
        "current_stage": IncidentIMGroup.Stage.COMPLETED,
        "continuous_sync_enabled": True,
        "idempotency_key": f"bklite-{uuid.uuid4().hex}",
    }
    values.update(overrides)
    return IncidentIMGroup.objects.create(**values)


@pytest.mark.django_db
def test_close_pauses_im_group_and_reopen_restores_and_enqueues():
    incident = _make_incident(status=IncidentStatus.PROCESSING)
    group = _make_im_group(incident)
    op = IncidentOperator(user="u1")

    assert op.operate("close", "I1", {})["result"] is True
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.resume_after_reopen is True

    assert op.operate("reopen", "I1", {})["result"] is True
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE
    assert group.pause_reason == ""
    assert group.resume_after_reopen is False
    assert AlertOutbox.objects.filter(kind="incident_im_group.reconcile").exists()


@pytest.mark.django_db
def test_reopen_preserves_manual_pause_and_does_not_enqueue():
    incident = _make_incident(status=IncidentStatus.CLOSED)
    group = _make_im_group(
        incident,
        status=IncidentIMGroup.Status.PAUSED,
        pause_reason=IncidentIMGroup.PauseReason.MANUAL,
    )

    assert IncidentOperator(user="u1").operate("reopen", "I1", {})["result"] is True

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.MANUAL
    assert not AlertOutbox.objects.filter(kind="incident_im_group.reconcile").exists()


@pytest.mark.django_db
def test_reopen_clears_closed_pause_without_enqueue_when_continuous_sync_was_off():
    incident = _make_incident(status=IncidentStatus.CLOSED)
    group = _make_im_group(
        incident,
        status=IncidentIMGroup.Status.PAUSED,
        pause_reason=IncidentIMGroup.PauseReason.INCIDENT_CLOSED,
        continuous_sync_enabled=False,
        resume_after_reopen=False,
    )

    assert IncidentOperator(user="u1").operate("reopen", "I1", {})["result"] is True

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE
    assert group.pause_reason == ""
    assert not AlertOutbox.objects.filter(kind="incident_im_group.reconcile").exists()


@pytest.mark.django_db
def test_close_group_hook_rolls_back_with_incident_when_later_operation_fails(monkeypatch):
    incident = _make_incident(status=IncidentStatus.PROCESSING)
    group = _make_im_group(incident)
    op = IncidentOperator(user="u1")
    monkeypatch.setattr(op, "operator_log", lambda _data: (_ for _ in ()).throw(RuntimeError("log failed")))

    result = op.operate("close", "I1", {})

    assert result["result"] is False
    incident.refresh_from_db()
    group.refresh_from_db()
    assert incident.status == IncidentStatus.PROCESSING
    assert group.status == IncidentIMGroup.Status.ACTIVE


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("group_status", "external_chat_id"),
    [
        (IncidentIMGroup.Status.CREATE_FAILED, ""),
        (IncidentIMGroup.Status.DEGRADED, "oc_degraded"),
    ],
)
def test_close_reopen_preserves_non_resumable_group_authoritative_state(group_status, external_chat_id):
    incident = _make_incident(status=IncidentStatus.PROCESSING)
    group = _make_im_group(
        incident,
        status=group_status,
        external_chat_id=external_chat_id,
    )
    op = IncidentOperator(user="u1")

    assert op.operate("close", "I1", {})["result"] is True
    group.refresh_from_db()
    assert group.status == group_status
    assert group.pause_reason == ""

    assert op.operate("reopen", "I1", {})["result"] is True
    group.refresh_from_db()
    assert group.status == group_status
    assert group.pause_reason == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    "group_status",
    [
        IncidentIMGroup.Status.PENDING_CREATE,
        IncidentIMGroup.Status.CREATING,
        IncidentIMGroup.Status.ACTIVE,
        IncidentIMGroup.Status.ACTIVE_PARTIAL,
    ],
)
def test_close_reopen_pre_chat_group_is_idempotently_requeued_for_create(group_status):
    from apps.alerts.service.incident_im.reconcile import (
        pause_group_for_closed_incident,
        resume_group_for_reopened_incident,
    )

    incident = _make_incident(status=IncidentStatus.PROCESSING)
    group = _make_im_group(incident, status=group_status, external_chat_id="")
    op = IncidentOperator(user="u1")

    assert op.operate("close", "I1", {})["result"] is True
    pause_group_for_closed_incident(incident.id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.resume_after_reopen is True
    pause_group_for_closed_incident(incident.id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.resume_after_reopen is True

    assert op.operate("reopen", "I1", {})["result"] is True
    resume_group_for_reopened_incident(incident.id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PENDING_CREATE
    assert group.current_stage == IncidentIMGroup.Stage.QUEUED
    assert group.pause_reason == ""
    assert AlertOutbox.objects.filter(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}
    ).count() == 1
    resume_group_for_reopened_incident(incident.id)
    assert AlertOutbox.objects.filter(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}
    ).count() == 1
