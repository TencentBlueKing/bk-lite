import json
from unittest.mock import Mock

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.views.node import NodeViewSet


def _post_proxy_address(user, cloud_region_id=42):
    request = APIRequestFactory().post(
        "/api/v1/log/node_mgmt/cloud_region_proxy_address/",
        data={"cloud_region_id": cloud_region_id},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    view = NodeViewSet.as_view({"post": "get_cloud_region_proxy_address"})
    return view(request)


def _response_data(response):
    return json.loads(response.content)["data"]


@pytest.mark.django_db
def test_cloud_region_proxy_address_endpoint_returns_proxy_address(authenticated_user, mocker):
    mocked_rpc = Mock()
    mocked_rpc.get_cloud_region_proxy_address.return_value = "proxy.example.com"
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=mocked_rpc)

    response = _post_proxy_address(authenticated_user)

    assert response.status_code == 200
    assert _response_data(response)["proxy_address"] == "proxy.example.com"
    # 非超管用户会带上其组织 id 列表作为第二个参数
    mocked_rpc.get_cloud_region_proxy_address.assert_called_once()
    call_args = mocked_rpc.get_cloud_region_proxy_address.call_args.args
    assert call_args[0] == 42
    assert isinstance(call_args[1], list)


@pytest.mark.django_db
def test_cloud_region_proxy_address_endpoint_falls_back_to_node_server_url(authenticated_user, mocker):
    mocked_rpc = Mock()
    mocked_rpc.get_cloud_region_proxy_address.return_value = ""
    mocked_rpc.node_list.return_value = {"nodes": [{"id": "node-1"}]}
    mocked_rpc.get_cloud_region_envconfig.return_value = {
        "NODE_SERVER_URL": "https://logs.example.com:8011/api/v1",
    }
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=mocked_rpc)

    response = _post_proxy_address(authenticated_user)

    assert response.status_code == 200
    assert _response_data(response)["proxy_address"] == "logs.example.com"
