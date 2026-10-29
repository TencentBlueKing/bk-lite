import logging
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from apps.operation_analysis.services.dashboard_scene_permission import (
    batch_check_dashboard_scene_permissions,
    check_application_topology_permission,
    check_related_topology_permission,
)

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

pytestmark = pytest.mark.unit


def _request_user():
    return SimpleNamespace(
        username="scene-perm-user",
        domain="domain.com",
        locale="en",
        timezone="Asia/Shanghai",
        permission={},
        group_tree=[],
        is_superuser=False,
        is_authenticated=True,
    )


def test_batch_check_skips_unbound_instances():
    request = APIRequestFactory().post("/")
    request.user = _request_user()
    results = batch_check_dashboard_scene_permissions(
        request,
        [
            {"widget_id": "w1", "scene_type": "relatedTopology", "inst_uuid": ""},
        ],
    )
    assert results == [{"widget_id": "w1", "code": "visible"}]


def test_batch_check_marks_permission_denied(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_scene_permission.check_related_topology_permission",
        lambda request, inst_uuid: "permission_denied",
    )
    request = APIRequestFactory().post("/")
    request.user = _request_user()
    results = batch_check_dashboard_scene_permissions(
        request,
        [
            {
                "widget_id": "w1",
                "scene_type": "relatedTopology",
                "inst_uuid": CENTER_UUID,
            }
        ],
    )
    assert results == [{"widget_id": "w1", "code": "permission_denied"}]


def test_query_failure_stays_visible_and_logs_once_without_payload(monkeypatch, caplog):
    request = APIRequestFactory().post("/")
    request.user = _request_user()
    request.COOKIES["current_team"] = "1"
    sentinel = "scene-permission-secret-sentinel"

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_scene_permission.normalize_inst_uuid",
        lambda raw: raw,
    )

    def boom(inst_uuid):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_scene_permission.InstanceManage.query_entity_by_uuid",
        boom,
    )

    with caplog.at_level(logging.WARNING, logger="operation_analysis"):
        assert check_related_topology_permission(request, CENTER_UUID) == "visible"

    records = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=dashboard_scene_permission_degraded failed_stage=%s error_type=%s inst_uuid=%s"
    assert record.args == ("query_entity", "RuntimeError", CENTER_UUID)
    rendered = record.getMessage()
    assert "query_entity" in rendered
    assert CENTER_UUID in rendered
    assert sentinel not in rendered
    assert sentinel not in caplog.text
    assert record.exc_info is not None
    assert record.exc_info[2] is not None
    formatted = logging.Formatter().format(record)
    assert sentinel not in formatted


def test_check_related_topology_permission_visible_when_unbound():
    request = APIRequestFactory().post("/")
    request.user = _request_user()
    assert check_related_topology_permission(request, "") == "visible"


def test_check_application_topology_permission_denied_matches_topology_gate(monkeypatch):
    request = APIRequestFactory().post("/")
    request.user = _request_user()

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_scene_permission._topology_permission_code",
        lambda request, inst_uuid, require_application_system=False: "permission_denied",
    )

    assert check_application_topology_permission(request, CENTER_UUID) == "permission_denied"


def test_check_related_topology_permission_denied_matches_topology_gate(monkeypatch):
    request = APIRequestFactory().post("/")
    request.user = _request_user()

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_scene_permission._topology_permission_code",
        lambda request, inst_uuid, require_application_system=False: "permission_denied",
    )

    assert check_related_topology_permission(request, CENTER_UUID) == "permission_denied"
