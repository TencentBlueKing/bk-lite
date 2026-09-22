import inspect
import json
import logging
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.serializers.scene_widget_serializers import Room3DLayoutRequestSerializer, Room3DRoomsRequestSerializer
from apps.operation_analysis.services.room3d import Room3DError, Room3DService
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

ROOM_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOM_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SECRET_SENTINEL = "super-secret-nats-payload"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _post_request(user, path, data=None):
    request = APIRequestFactory().post(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _service_request():
    return SimpleNamespace(
        user=SimpleNamespace(
            username="testuser",
            domain="domain.com",
            locale="zh-CN",
            timezone="Asia/Shanghai",
            permission={},
            group_tree=[],
            is_superuser=False,
        ),
        COOKIES={"current_team": "1", "include_children": "0"},
    )


class _FakeCMDB:
    def __init__(self, rooms=None, layout=None, rooms_result=None, layout_result=None, error=None):
        self.rooms = rooms if rooms is not None else [{"inst_uuid": ROOM_A, "inst_name": "机房 A"}]
        self.layout = layout if layout is not None else {"room": {"id": ROOM_A, "name": "机房 A"}, "racks": []}
        self.rooms_result = rooms_result
        self.layout_result = layout_result
        self.error = error
        self.room_calls = []
        self.layout_calls = []

    def get_room_list(self, **kwargs):
        self.room_calls.append(kwargs)
        if self.error == "rooms":
            raise RuntimeError("nats unavailable")
        if self.rooms_result is not None:
            return self.rooms_result
        return {"items": self.rooms}

    def get_room3d_layout(self, **kwargs):
        self.layout_calls.append(kwargs)
        if self.error == "layout":
            raise RuntimeError("nats unavailable")
        if self.layout_result is not None:
            return self.layout_result
        return {"result": True, "data": self.layout, "message": ""}


def _install(monkeypatch, cmdb):
    monkeypatch.setattr("apps.operation_analysis.services.room3d.CMDB", lambda: cmdb)


def test_rooms_serializer_rejects_unknown_fields():
    serializer = Room3DRoomsRequestSerializer(data={"server_room_id": ROOM_A})
    assert not serializer.is_valid()
    assert Room3DRoomsRequestSerializer(data={}).is_valid()


def test_layout_serializer_requires_uuid():
    serializer = Room3DLayoutRequestSerializer(data={"server_room_id": ROOM_A})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"server_room_id": ROOM_A}
    invalid = Room3DLayoutRequestSerializer(data={})
    assert not invalid.is_valid()


def test_service_does_not_import_cmdb_instance_manage():
    source = inspect.getsource(Room3DService)
    assert "InstanceManage" not in source


def test_list_rooms_maps_visible_cmdb_rooms(monkeypatch):
    cmdb = _FakeCMDB(
        rooms=[
            {"inst_uuid": ROOM_A, "inst_name": "机房 A", "token": SECRET_SENTINEL},
            {"inst_uuid": "", "inst_name": "匿名"},
            {"inst_uuid": ROOM_B, "inst_name": "机房 B"},
        ]
    )
    _install(monkeypatch, cmdb)

    result = Room3DService.list_rooms(request=_service_request())

    assert result == {
        "items": [
            {"id": ROOM_A, "name": "机房 A"},
            {"id": ROOM_B, "name": "机房 B"},
        ]
    }
    assert cmdb.room_calls[0]["user_info"]["user"] == "testuser"


def test_layout_returns_nats_payload(monkeypatch):
    layout = {"room": {"id": ROOM_A, "name": "机房 A"}, "racks": [{"rack_id": "r1"}]}
    cmdb = _FakeCMDB(layout=layout)
    _install(monkeypatch, cmdb)

    result = Room3DService.layout(request=_service_request(), server_room_id=ROOM_A)

    assert result == layout
    assert cmdb.layout_calls[0]["server_room_id"] == ROOM_A


def test_layout_maps_permission_denied(monkeypatch):
    cmdb = _FakeCMDB(layout_result={"result": False, "data": {}, "message": "无权限查看当前机房", "code": 403})
    _install(monkeypatch, cmdb)

    with pytest.raises(Room3DError) as exc_info:
        Room3DService.layout(request=_service_request(), server_room_id=ROOM_A)

    assert exc_info.value.code == "permission_denied"


def test_layout_source_failure_logs_once_without_payload(monkeypatch, caplog):
    cmdb = _FakeCMDB(error="layout")
    _install(monkeypatch, cmdb)

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(Room3DError) as exc_info:
            Room3DService.layout(request=_service_request(), server_room_id=ROOM_A)

    assert exc_info.value.code == "source_failure"
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=room3d_source_failed failed_stage=%s error_type=%s server_room_id=%s"
    assert record.args == ("layout", "RuntimeError", ROOM_A)
    rendered = record.getMessage()
    assert "layout" in rendered
    assert "RuntimeError" in rendered
    assert ROOM_A in rendered
    assert SECRET_SENTINEL not in rendered
    assert record.exc_info is not None


def test_rooms_nats_false_result_logs_once_without_payload(monkeypatch, caplog):
    cmdb = _FakeCMDB(rooms_result={"result": False, "data": {"token": SECRET_SENTINEL}, "message": "nats down"})
    _install(monkeypatch, cmdb)

    with caplog.at_level(logging.ERROR, logger="operation_analysis"):
        with pytest.raises(Room3DError) as exc_info:
            Room3DService.list_rooms(request=_service_request())

    assert exc_info.value.code == "source_failure"
    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.msg == "event=room3d_source_failed failed_stage=%s error_type=%s server_room_id=%s"
    assert record.args == ("rooms", "NatsResultFalse", "-")
    rendered = record.getMessage()
    assert "rooms" in rendered
    assert "NatsResultFalse" in rendered
    assert SECRET_SENTINEL not in rendered
    assert SECRET_SENTINEL not in caplog.text
    assert record.exc_info is None


def _user():
    return SimpleNamespace(
        is_authenticated=True,
        is_superuser=True,
        username="testuser",
        domain="domain.com",
        locale="zh-CN",
        timezone="Asia/Shanghai",
        permission={},
        group_tree=[],
    )


def test_rooms_view_returns_items(monkeypatch):
    cmdb = _FakeCMDB(rooms=[{"inst_uuid": ROOM_A, "inst_name": "机房 A"}])
    _install(monkeypatch, cmdb)
    request = _post_request(_user(), "/operation_analysis/api/scene_widgets/room3d/rooms/", {})
    response = SceneWidgetViewSet.as_view({"post": "room3d_rooms"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == {"items": [{"id": ROOM_A, "name": "机房 A"}]}


def test_layout_view_returns_payload(monkeypatch):
    layout = {"room": {"id": ROOM_A, "name": "机房 A"}, "racks": []}
    cmdb = _FakeCMDB(layout=layout)
    _install(monkeypatch, cmdb)
    request = _post_request(
        _user(),
        "/operation_analysis/api/scene_widgets/room3d/layout/",
        {"server_room_id": ROOM_A},
    )
    response = SceneWidgetViewSet.as_view({"post": "room3d_layout"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == layout


def test_layout_view_rejects_invalid_body():
    request = _post_request(_user(), "/operation_analysis/api/scene_widgets/room3d/layout/", {})
    response = SceneWidgetViewSet.as_view({"post": "room3d_layout"})(request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
