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


def _call(request, inst_id="9"):
    view = InstanceViewSet.as_view({"get": "ipam_view"})
    return view(request, inst_id=inst_id)


def test_ipam_view_requires_asset_view_permission():
    user = _user()
    subnet = {
        "_id": 9,
        "model_id": "subnet",
        "organization": [1],
        "subnet_address": "10.0.1.0",
        "subnet_mask": "24",
    }
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_id", return_value=subnet), \
         patch("apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions", return_value={}), \
         patch("apps.cmdb.views.instance.CmdbRulesFormatUtil.has_object_permission", return_value=True), \
         patch("apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]):
        resp = _call(_request(user))

    assert resp.status_code == 403


def test_ipam_view_returns_404_when_subnet_missing():
    user = _user()
    _grant_asset_view(user)

    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_id", return_value=None):
        resp = _call(_request(user), inst_id="404")

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

    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_id", return_value=subnet):
        resp = _call(_request(user))

    assert resp.status_code == 403


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
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_id", return_value=subnet), \
         patch("apps.cmdb.views.instance.CmdbRulesFormatUtil.format_user_groups_permissions", return_value={}), \
         patch("apps.cmdb.views.instance.CmdbRulesFormatUtil.has_object_permission", return_value=True), \
         patch("apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]):
        resp = _call(_request(user))

    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["data"]["capacity"] == 254
