# -- coding: utf-8 --
"""IP 视图数据接口。规格 §7.2。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet

pytestmark = pytest.mark.unit


def _grant_asset_view(user):
    user.permission = {"cmdb": {"asset_info-View"}}


def _user():
    return SimpleNamespace(
        username="bob",
        is_superuser=False,
        is_authenticated=True,
        is_active=True,
        permission={},
        group_list=[{"id": 1, "name": "Default Team"}],
        group_tree=[],
        roles=[],
        locale="en",
    )


def _request(user):
    request = APIRequestFactory().get("/api/v1/cmdb/api/instance/ipam_view/9/")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _call(request, inst_uuid="subnet-uuid"):
    view = InstanceViewSet.as_view({"get": "ipam_view"})
    return view(request, inst_uuid=inst_uuid)


def _reconcile_request(user):
    request = APIRequestFactory().post(
        "/api/v1/cmdb/api/instance/ipam_reconcile/",
        data={},
        format="json",
    )
    force_authenticate(request, user=user)
    return request


def _call_reconcile(request):
    return InstanceViewSet.as_view({"post": "ipam_reconcile"})(request)


def test_ipam_view_requires_asset_view_permission():
    user = _user()
    subnet = {
        "_id": 9,
        "model_id": "subnet",
        "organization": [1],
        "subnet_address": "10.0.1.0",
        "subnet_mask": "24",
    }
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_id", return_value=subnet), patch(
        "apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions", return_value={}
    ), patch("apps.cmdb.views.instance.CmdbRulesFormatUtil.has_object_permission", return_value=True), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]
    ):
        resp = _call(_request(user))

    assert resp.status_code == 403


def test_ipam_view_returns_404_when_subnet_missing():
    user = _user()
    _grant_asset_view(user)

    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=None):
        resp = _call(_request(user), inst_uuid="404")

    assert resp.status_code == 404


def test_ipam_view_returns_403_without_subnet_view_permission():
    user = _user()
    _grant_asset_view(user)
    subnet = {
        "_id": 9,
        "model_id": "subnet",
        "organization": [2],
        "subnet_address": "10.0.1.0",
        "subnet_mask": "24",
    }

    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=subnet):
        resp = _call(_request(user))

    assert resp.status_code == 403
    assert json.loads(resp.content)["message"] == "抱歉！您没有此实例的权限"


def test_ipam_view_action_returns_capacity_with_view_permission():
    user = _user()
    _grant_asset_view(user)
    subnet = {
        "_id": 9,
        "model_id": "subnet",
        "organization": [1],
        "subnet_address": "10.0.1.0",
        "subnet_mask": "24",
    }
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=subnet), patch(
        "apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions", return_value={}
    ), patch("apps.cmdb.views.instance.CmdbRulesFormatUtil.has_object_permission", return_value=True), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]
    ), patch.object(
        InstanceViewSet, "require_instance_permission", return_value=None
    ):
        resp = _call(_request(user))

    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["data"]["capacity"] == 254


_IPAM_DETAIL_FIELDS = ("inst_uuid", "_id", "inst_name", "description", "mac", "ip_user", "_creator")


def _allocated_ip(**overrides):
    row = {
        "_id": 101,
        "inst_uuid": "ip-hidden",
        "inst_name": "hidden-assoc",
        "model_id": "ip",
        "organization": [1],
        "subnet_id": "9",
        "ip_addr": "10.0.1.10",
        "ip_allocated_status": ["allocated"],
        "ip_status": ["online"],
        "description": "hidden description",
        "mac": "aa:bb:cc:dd:ee:10",
        "ip_user": [7],
        "_creator": "alice",
    }
    row.update(overrides)
    return row


def _assert_ip_details_hidden(ip):
    for field in _IPAM_DETAIL_FIELDS:
        assert field not in ip
    assert ip["permission"] == []
    assert ip["ip_allocated_status"] == ["allocated"]
    assert ip["ip_status"] == ["online"]


def test_ipam_view_hides_attributes_without_instance_view():
    user = _user()
    _grant_asset_view(user)
    subnet = {
        "_id": 9,
        "inst_uuid": "subnet-uuid",
        "model_id": "subnet",
        "organization": [1],
        "subnet_address": "10.0.1.0",
        "subnet_mask": "24",
    }
    hidden_by_association = _allocated_ip()
    visible = _allocated_ip(
        _id=102,
        inst_uuid="ip-visible",
        inst_name="visible-ip",
        ip_addr="10.0.1.11",
        description="visible description",
        mac="aa:bb:cc:dd:ee:11",
        ip_user=[8],
    )
    hidden_by_field = _allocated_ip(
        _id=103,
        inst_uuid="ip-other-org",
        inst_name="other-org-ip",
        organization=[2],
        ip_addr="10.0.1.12",
        description="other org description",
        mac="aa:bb:cc:dd:ee:12",
        ip_user=[9],
        _creator="carol",
    )
    created_by_caller = _allocated_ip(
        _id=104,
        inst_uuid="ip-creator",
        inst_name="creator-ip",
        ip_addr="10.0.1.13",
        description="creator description",
        mac="aa:bb:cc:dd:ee:13",
        ip_user=[10],
        _creator="bob",
    )
    permissions = {1: {"permission_instances_map": {"visible-ip": ["View"]}, "inst_names": ["visible-ip"]}}

    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_uuid", return_value=subnet), patch(
        "apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions", return_value=permissions
    ), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips_by_association",
        return_value=[hidden_by_association, visible],
    ), patch(
        "apps.cmdb.services.ipam_view._query_subnet_ips_by_field",
        return_value=[hidden_by_field, created_by_caller],
    ), patch.object(InstanceViewSet, "require_instance_permission", return_value=None):
        resp = _call(_request(user))

    assert resp.status_code == 200
    data = json.loads(resp.content)["data"]
    by_addr = {ip["ip_addr"]: ip for ip in data["ips"]}
    assert set(by_addr) == {"10.0.1.10", "10.0.1.11", "10.0.1.12", "10.0.1.13"}

    _assert_ip_details_hidden(by_addr["10.0.1.10"])
    _assert_ip_details_hidden(by_addr["10.0.1.12"])

    assert by_addr["10.0.1.11"]["description"] == "visible description"
    assert by_addr["10.0.1.11"]["inst_uuid"] == "ip-visible"
    assert "View" in by_addr["10.0.1.11"]["permission"]

    creator = by_addr["10.0.1.13"]
    assert creator["inst_uuid"] == "ip-creator"
    assert creator["_id"] == 104
    assert creator["inst_name"] == "creator-ip"
    assert creator["description"] == "creator description"
    assert creator["mac"] == "aa:bb:cc:dd:ee:13"
    assert creator["ip_user"] == [10]
    assert creator["_creator"] == "bob"
    assert creator["permission"] == ["View", "Operate"]

    assert data["capacity"] == 254
    assert data["used"] == 4
    assert data["available"] == 250
    assert data["status_counts"]["online"] == 4


def test_ipam_reconcile_requires_asset_edit_permission():
    user = _user()

    with patch(
        "apps.cmdb.services.ipam_reconcile.run_reconciliation",
        return_value={"created": 1},
    ) as reconcile:
        response = _call_reconcile(_reconcile_request(user))

    assert response.status_code == 403
    reconcile.assert_not_called()


def test_ipam_reconcile_enqueues_with_asset_edit_permission():
    user = _user()
    user.permission = {"cmdb": {"asset_info-Edit"}}

    with patch(
        "apps.cmdb.services.ipam_reconcile_job.IPAMReconcileJob.enqueue",
    ) as enqueue:
        enqueue.return_value.run.run_id = "run-1"
        enqueue.return_value.run.status = "pending"
        enqueue.return_value.reused = False
        response = _call_reconcile(_reconcile_request(user))

    assert response.status_code == 200
    enqueue.assert_called_once_with(trigger="manual")
    body = json.loads(response.content)["data"]
    assert body == {"run_id": "run-1", "status": "pending", "reused": False}
