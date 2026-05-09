from unittest.mock import Mock

import pytest


@pytest.mark.django_db
def test_cloud_region_proxy_address_endpoint_returns_proxy_address(api_client, authenticated_user, mocker):
    mocked_rpc = Mock()
    mocked_rpc.get_cloud_region_proxy_address.return_value = "proxy.example.com"
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=mocked_rpc)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/node_mgmt/cloud_region_proxy_address/",
        data={"cloud_region_id": 42},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["proxy_address"] == "proxy.example.com"
    mocked_rpc.get_cloud_region_proxy_address.assert_called_once_with(42)
