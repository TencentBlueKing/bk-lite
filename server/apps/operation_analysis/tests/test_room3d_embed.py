import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.services.room3d_embed import Room3DEmbedError, Room3DEmbedService
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

ROOM_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SECRET_SENTINEL = "super-secret-nats-payload"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _post_request(user, data):
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/room3d/",
        data=data,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def test_room3d_embed_queries_single_room_by_inst_uuid(monkeypatch, authenticated_user):
    captured = {}

    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            captured["server_room_id"] = server_room_id
            captured["user_info"] = user_info
            return {
                "result": True,
                "data": {
                    "room": {"id": server_room_id, "name": "机房A"},
                    "racks": [{"id": "rack-1"}],
                },
                "message": "",
            }

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)

    request = _post_request(authenticated_user, {"inst_uuid": ROOM_UUID})
    response = SceneWidgetViewSet.as_view({"post": "room3d"})(request)
    payload = _render(response)

    assert response.status_code == 200
    assert payload["result"] is True
    assert captured["server_room_id"] == ROOM_UUID
    assert captured["user_info"]["user"] == authenticated_user.username
    assert captured["user_info"]["team"] == 1
    assert payload["data"]["room"]["id"] == ROOM_UUID
    assert payload["data"]["racks"] == [{"id": "rack-1"}]
    assert SECRET_SENTINEL not in json.dumps(payload)


def test_room3d_embed_maps_not_found(monkeypatch, authenticated_user):
    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            return {"result": False, "data": {}, "message": "机房实例不存在", "code": 404}

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)
    request = _post_request(authenticated_user, {"inst_uuid": ROOM_UUID})
    response = SceneWidgetViewSet.as_view({"post": "room3d"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert payload["result"] is False
    assert payload["code"] == "40400"


def test_room3d_embed_maps_permission_denied(monkeypatch, authenticated_user):
    captured = {}

    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            captured["server_room_id"] = server_room_id
            captured["user_info"] = user_info
            return {"result": False, "data": {}, "message": "无权限查看该机房", "code": 403}

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)
    request = _post_request(authenticated_user, {"inst_uuid": ROOM_UUID})
    response = SceneWidgetViewSet.as_view({"post": "room3d"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False
    assert payload["code"] == "40300"
    assert "无权限" in payload["message"]
    assert captured["server_room_id"] == ROOM_UUID
    assert captured["user_info"]["user"] == authenticated_user.username
    assert captured["user_info"]["domain"] == authenticated_user.domain
    assert captured["user_info"]["team"] == 1


def test_room3d_embed_does_not_query_full_wall(monkeypatch):
    captured = {}

    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            captured["server_room_id"] = server_room_id
            return {"result": True, "data": {"room": {"id": server_room_id}, "racks": []}, "message": ""}

        def list_application_systems(self, **kwargs):
            raise AssertionError("room3D embed must not load application walls")

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)
    request = SimpleNamespace(
        user=SimpleNamespace(username="tester", domain="domain.com"),
        COOKIES={"current_team": "1", "include_children": "0"},
    )
    Room3DEmbedService.build(request, ROOM_UUID)
    assert captured["server_room_id"] == ROOM_UUID


def test_room3d_embed_source_failure_is_logged_once(monkeypatch, caplog):
    original_error = RuntimeError("nats down")

    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            raise original_error

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)
    request = SimpleNamespace(
        user=SimpleNamespace(username="tester", domain="domain.com"),
        COOKIES={"current_team": "1", "include_children": "0"},
    )
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(Room3DEmbedError) as exc:
            Room3DEmbedService.build(request, ROOM_UUID)
    assert exc.value.code == "source_failure"
    records = [
        record
        for record in caplog.records
        if record.name == "operation_analysis" and record.msg == "event=room3d_embed_source_failed failed_stage=%s error_type=%s inst_uuid=%s"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.args == ("layout", "RuntimeError", ROOM_UUID)
    assert record.exc_info is not None
    assert record.exc_info[2] is original_error.__traceback__
    formatted = logging.Formatter().format(record)
    assert "nats down" not in formatted
    assert "nats down" not in record.getMessage()
    assert original_error.args == ("nats down",)
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in caplog.text


def test_room3d_embed_false_nats_result_is_logged_without_payload(monkeypatch, caplog):
    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            return {
                "result": False,
                "data": {"body": SECRET_SENTINEL},
                "message": SECRET_SENTINEL,
            }

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)
    request = SimpleNamespace(
        user=SimpleNamespace(username="tester", domain="domain.com"),
        COOKIES={"current_team": "1", "include_children": "0"},
    )
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(Room3DEmbedError) as exc:
            Room3DEmbedService.build(request, ROOM_UUID)
    assert exc.value.code == "source_failure"
    records = [
        record
        for record in caplog.records
        if record.name == "operation_analysis" and record.msg == "event=room3d_embed_source_failed failed_stage=%s error_type=%s inst_uuid=%s"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.args == ("layout", "NatsResultFalse", ROOM_UUID)
    assert record.exc_info is None
    formatted = logging.Formatter().format(record)
    assert SECRET_SENTINEL not in formatted
    assert SECRET_SENTINEL not in record.getMessage()
    assert SECRET_SENTINEL not in caplog.text


def test_room3d_embed_mapped_nats_error_does_not_log_source_failure(monkeypatch, caplog):
    class FakeCMDB:
        def get_room3d_layout(self, server_room_id=None, user_info=None):
            return {"result": False, "data": {}, "message": "机房实例不存在", "code": 404}

    monkeypatch.setattr("apps.operation_analysis.services.room3d_embed.CMDB", FakeCMDB)
    request = SimpleNamespace(
        user=SimpleNamespace(username="tester", domain="domain.com"),
        COOKIES={"current_team": "1", "include_children": "0"},
    )
    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(Room3DEmbedError) as exc:
            Room3DEmbedService.build(request, ROOM_UUID)
    assert exc.value.code == "not_found"
    assert not [
        record
        for record in caplog.records
        if record.name == "operation_analysis" and record.msg == "event=room3d_embed_source_failed failed_stage=%s error_type=%s inst_uuid=%s"
    ]
