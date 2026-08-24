# -- coding: utf-8 --
"""机房机柜布局变更接口权限。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet

pytestmark = pytest.mark.unit

ROOM = {
    "_id": 7,
    "inst_uuid": "room-uuid",
    "model_id": "server_room",
    "organization": [1],
    "inst_name": "R1",
}
RACK = {
    "_id": 8,
    "inst_uuid": "rack-uuid",
    "model_id": "rack",
    "organization": [1],
    "inst_name": "A01",
    "location": "",
}


def _user(perms=None):
    return SimpleNamespace(
        username="bob",
        is_superuser=False,
        is_authenticated=True,
        is_active=True,
        permission={"cmdb": set(perms or [])},
        group_list=[{"id": 1, "name": "Default Team"}],
        group_tree=[],
        roles=[],
        locale="en",
    )


def _post(user, data):
    request = APIRequestFactory().post(
        "/api/v1/cmdb/api/instance/rack_room_layout/",
        data=data,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _get(user, query):
    request = APIRequestFactory().get(
        "/api/v1/cmdb/api/instance/rack_room_layout_candidates/",
        data=query,
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _call_post(request):
    return InstanceViewSet.as_view({"post": "rack_room_layout"})(request)


def _call_get(request):
    return InstanceViewSet.as_view({"get": "rack_room_layout_candidates"})(request)


def _grant_view():
    return patch.object(InstanceViewSet, "require_instance_permission", return_value=None)


def test_layout_place_create_requires_add():
    user = _user(["asset_info-Edit"])
    with _grant_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=ROOM):
        resp = _call_post(
            _post(
                user,
                {
                    "action": "place_create",
                    "scope": "room",
                    "container_inst_uuid": "room-uuid",
                    "row": 1,
                    "col": 1,
                    "instance_info": {"inst_name": "R1"},
                },
            )
        )
    assert resp.status_code == 403


def test_layout_place_existing_requires_edit():
    user = _user(["asset_info-Add"])
    with _grant_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", side_effect=[ROOM, RACK]):
        resp = _call_post(
            _post(
                user,
                {
                    "action": "place_existing",
                    "scope": "room",
                    "container_inst_uuid": "room-uuid",
                    "inst_uuid": "rack-uuid",
                    "row": 1,
                    "col": 1,
                },
            )
        )
    assert resp.status_code == 403


def test_layout_unplace_denied_without_instance_operate(monkeypatch):
    user = _user(["asset_info-Edit"])
    from rest_framework import status as http_status

    from apps.core.utils.web_utils import WebUtils

    denied = WebUtils.response_error("抱歉！您没有此实例的权限", status_code=http_status.HTTP_403_FORBIDDEN)

    def fake_require(self, request, instance, operator="View"):
        if instance.get("model_id") == "rack":
            return denied
        return None

    monkeypatch.setattr(InstanceViewSet, "require_instance_permission", fake_require)
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", side_effect=[ROOM, RACK]):
        resp = _call_post(
            _post(
                user,
                {
                    "action": "unplace",
                    "scope": "room",
                    "container_inst_uuid": "room-uuid",
                    "inst_uuid": "rack-uuid",
                },
            )
        )
    assert resp.status_code == 403


def test_layout_place_create_with_add(monkeypatch):
    user = _user(["asset_info-Add"])
    created = {"_id": 4, "inst_uuid": "rack-new", "model_id": "rack", "inst_name": "R1"}

    def fake_execute(**kwargs):
        assert kwargs["action"] == "place_create"
        assert kwargs["operator"] == "bob"
        assert kwargs["row"] == 2
        assert kwargs["col"] == 1
        assert kwargs["instance_info"]["inst_name"] == "R1"
        return {"action": "place_create", "instance": created}

    monkeypatch.setattr("apps.cmdb.services.rack_room_edit.execute_layout_action", fake_execute)
    with _grant_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=ROOM), patch.object(
        InstanceViewSet, "_get_allowed_org_ids", return_value=[1]
    ):
        resp = _call_post(
            _post(
                user,
                {
                    "action": "place_create",
                    "scope": "room",
                    "container_inst_uuid": "room-uuid",
                    "row": 2,
                    "col": 1,
                    "instance_info": {"inst_name": "R1", "u_count": 42},
                },
            )
        )
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["data"]["action"] == "place_create"
    assert body["data"]["instance"]["inst_uuid"] == "rack-new"
    assert "_id" not in body["data"]["instance"]


def test_layout_candidates_require_write_menu():
    user = _user(["asset_info-View"])
    with _grant_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=ROOM):
        resp = _call_get(
            _get(
                user,
                {
                    "scope": "room",
                    "container_inst_uuid": "room-uuid",
                    "model_id": "rack",
                },
            )
        )
    assert resp.status_code == 403


def test_layout_candidates_ok(monkeypatch):
    user = _user(["asset_info-Edit"])

    def fake_list(**kwargs):
        assert kwargs["scope"] == "room"
        assert kwargs["model_id"] == "rack"
        return {
            "count": 1,
            "items": [
                {
                    "inst_uuid": "rack-8",
                    "inst_name": "A01",
                    "model_id": "rack",
                    "organization": [1],
                    "status": "selectable",
                    "_id": 8,
                }
            ],
        }

    monkeypatch.setattr("apps.cmdb.services.rack_room_edit.list_layout_candidates", fake_list)
    monkeypatch.setattr(
        "apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *a, **k: {},
    )
    with _grant_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=ROOM), patch.object(
        InstanceViewSet, "_attach_layout_item_permissions", lambda *a, **k: None
    ):
        resp = _call_get(
            _get(
                user,
                {
                    "scope": "room",
                    "container_inst_uuid": "room-uuid",
                    "model_id": "rack",
                },
            )
        )
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["data"]["items"][0]["inst_uuid"] == "rack-8"
    assert "_id" not in body["data"]["items"][0]
