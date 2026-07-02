"""apps/log/views/node.py get_nodes 端点测试。

NodeMgmt RPC 为外部边界（mock），断言入参契约与响应透传。
"""
from unittest.mock import Mock

import pytest


@pytest.mark.django_db
def test_get_nodes_passes_filters_and_permission_data(api_client, authenticated_user, mocker):
    mocked_rpc = Mock()
    mocked_rpc.node_list.return_value = {"count": 1, "nodes": [{"id": "n1", "name": "node-1"}]}
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=mocked_rpc)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/node_mgmt/nodes/",
        data={
            "cloud_region_id": 5,
            "name": "node",
            "ip": "10.0.0.1",
            "os": "linux",
            "page": 2,
            "page_size": 20,
            "is_active": True,
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["count"] == 1

    mocked_rpc.node_list.assert_called_once()
    payload = mocked_rpc.node_list.call_args.args[0]
    assert payload["cloud_region_id"] == 5
    assert payload["name"] == "node"
    assert payload["ip"] == "10.0.0.1"
    assert payload["page"] == 2
    assert payload["page_size"] == 20
    # 权限数据携带用户身份
    assert payload["permission_data"]["username"] == authenticated_user.username
    assert "organization_ids" in payload


@pytest.mark.django_db
def test_get_nodes_defaults_cloud_region_and_paging(api_client, authenticated_user, mocker):
    mocked_rpc = Mock()
    mocked_rpc.node_list.return_value = {"count": 0, "nodes": []}
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=mocked_rpc)

    api_client.cookies["current_team"] = "1"
    response = api_client.post("/api/v1/log/node_mgmt/nodes/", data={}, format="json")

    assert response.status_code == 200
    payload = mocked_rpc.node_list.call_args.args[0]
    assert payload["cloud_region_id"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 10
