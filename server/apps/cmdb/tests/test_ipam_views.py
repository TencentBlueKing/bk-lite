# -- coding: utf-8 --
"""IP 视图数据接口。规格 §7.2。"""
import json
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.django_db


def test_ipam_view_action(api_client):
    subnet = {"_id": 9, "model_id": "subnet", "subnet_address": "10.0.1.0", "subnet_mask": "24"}
    with patch("apps.cmdb.views.instance.InstanceManage.query_entity_by_id", return_value=subnet), \
         patch("apps.cmdb.services.ipam_view._query_subnet_ips", return_value=[]):
        resp = api_client.get("/api/v1/cmdb/api/instance/ipam_view/9/")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert body["data"]["capacity"] == 254
