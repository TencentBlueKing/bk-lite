# -- coding: utf-8 --
"""IP 视图手工登记接口权限。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet

pytestmark = pytest.mark.unit

SUBNET = {
    "_id": 9,
    "inst_uuid": "subnet-uuid",
    "model_id": "subnet",
    "organization": [1],
    "subnet_address": "10.11.27.0",
    "subnet_mask": "24",
}
EXISTING_IP = {
    "_id": 88,
    "inst_uuid": "ip-uuid",
    "model_id": "ip",
    "ip_addr": "10.11.27.87",
    "organization": [1],
    "ip_allocated_status": ["allocated"],
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


def _request(user, data):
    request = APIRequestFactory().post(
        "/api/v1/cmdb/api/instance/ipam_ip/",
        data=data,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _call(request):
    return InstanceViewSet.as_view({"post": "ipam_ip"})(request)


def _grant_subnet_view():
    return patch.object(InstanceViewSet, "require_instance_permission", return_value=None)


def test_ipam_ip_requires_write_permission():
    user = _user(["asset_info-View"])
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.27.10",
                    "ip_allocated_status": "allocated",
                },
            )
        )
    assert resp.status_code == 403


def test_ipam_ip_create_requires_add():
    user = _user(["asset_info-Edit"])
    with _grant_subnet_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]
    ):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.27.10",
                    "ip_allocated_status": "allocated",
                    "description": "web",
                },
            )
        )
    assert resp.status_code == 403


def test_ipam_ip_create_with_add(monkeypatch):
    user = _user(["asset_info-Add"])
    created = {"_id": 3, "inst_uuid": "new-ip", "ip_addr": "10.11.27.10", "model_id": "ip"}

    def fake_execute(**kwargs):
        assert kwargs["action"] == "create"
        assert kwargs["operator"] == "bob"
        assert kwargs["ip_addr"] == "10.11.27.10"
        assert kwargs["description"] == "web"
        return {"action": "create", "ip": created}

    monkeypatch.setattr("apps.cmdb.services.ipam_edit.execute_manual_ip_action", fake_execute)
    with _grant_subnet_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]
    ), patch.object(InstanceViewSet, "_get_allowed_org_ids", return_value=[1]):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.27.10",
                    "ip_allocated_status": "allocated",
                    "description": "web",
                },
            )
        )
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["data"]["action"] == "create"
    assert "inst_uuid" in body["data"]["ip"]
    assert "_id" not in body["data"]["ip"]


def test_ipam_ip_update_requires_edit_and_operate():
    user = _user(["asset_info-Add"])
    with _grant_subnet_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[EXISTING_IP]
    ):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.27.87",
                    "ip_allocated_status": "reserved",
                    "description": "vip",
                },
            )
        )
    assert resp.status_code == 403


def test_ipam_ip_update_denied_without_instance_operate(monkeypatch):
    user = _user(["asset_info-Edit"])
    from rest_framework import status as http_status

    from apps.core.utils.web_utils import WebUtils

    denied = WebUtils.response_error("抱歉！您没有此实例的权限", status_code=http_status.HTTP_403_FORBIDDEN)

    def fake_require(self, request, instance, operator="View"):
        if instance.get("model_id") == "ip":
            return denied
        return None

    monkeypatch.setattr(InstanceViewSet, "require_instance_permission", fake_require)
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[EXISTING_IP]
    ):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.27.87",
                    "ip_allocated_status": "reserved",
                },
            )
        )
    assert resp.status_code == 403


def test_ipam_ip_delete_requires_delete_permission():
    user = _user(["asset_info-Edit"])
    with _grant_subnet_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[EXISTING_IP]
    ):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.27.87",
                    "ip_allocated_status": "available",
                },
            )
        )
    assert resp.status_code == 403


def test_ipam_ip_rejects_address_outside_subnet():
    user = _user(["asset_info-Add"])
    with _grant_subnet_view(), patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=SUBNET):
        resp = _call(
            _request(
                user,
                {
                    "subnet_inst_uuid": "subnet-uuid",
                    "ip_addr": "10.11.28.1",
                    "ip_allocated_status": "allocated",
                },
            )
        )
    assert resp.status_code == 400
