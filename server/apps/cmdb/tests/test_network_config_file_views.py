from rest_framework.test import APIRequestFactory

from apps.cmdb.views.collect import CollectModelViewSet


def test_network_config_file_supported_brands_returns_options():
    request = APIRequestFactory().get("/cmdb/api/collect/network_config_file_supported_brands/")
    view = CollectModelViewSet.as_view({"get": "network_config_file_supported_brands"})

    response = view(request)

    assert response.status_code == 200
    assert {"label": "Cisco", "device_type": "cisco_ios"} in response.data["items"]
