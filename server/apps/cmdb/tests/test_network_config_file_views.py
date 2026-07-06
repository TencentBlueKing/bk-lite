from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from apps.cmdb.views.collect import CollectModelViewSet


def test_network_config_file_supported_brands_returns_options():
    request = APIRequestFactory().get("/cmdb/api/collect/network_config_file_supported_brands/")
    request.user = SimpleNamespace(is_superuser=True, is_active=True)  # 超级用户绕过权限检查
    view = CollectModelViewSet.as_view({"get": "network_config_file_supported_brands"})

    response = view(request)

    assert response.status_code == 200
    assert {"label": "Cisco", "device_type": "cisco_ios"} in response.data["items"]


# ---------------------------------------------------------------------------
# P1-2.4 — network_config_file_supported_brands 必须显式权限校验
# ---------------------------------------------------------------------------

class TestNetworkConfigFileSupportedBrandsPermission:
    """P1-2.4: 原 action 缺 @HasPermission 装饰,任何已登录用户都能拿到品牌白名单。
    AGENTS.md / backend-coding-guide §1 要求「每个 view/action 显式权限校验」,
    即便返回静态白名单也要走标准流程,避免后续被复用为敏感数据出口。"""

    @pytest.fixture
    def non_superuser_request(self):
        request = APIRequestFactory().get("/cmdb/api/collect/network_config_file_supported_brands/")
        request.user = SimpleNamespace(
            is_superuser=False,
            is_active=True,
            permission={},
        )
        return request

    def test_no_permission_returns_403(self, non_superuser_request):
        view = CollectModelViewSet.as_view({"get": "network_config_file_supported_brands"})

        response = view(non_superuser_request)

        assert response.status_code == 403, "无 View 权限的用户必须被 403 拒掉,不能拿到品牌白名单"

    def test_with_view_permission_returns_200(self):
        """持有 auto_collection-View 权限的用户应能正常拿到列表。"""
        request = APIRequestFactory().get("/cmdb/api/collect/network_config_file_supported_brands/")
        request.user = SimpleNamespace(
            is_superuser=False,
            is_active=True,
            permission={"cmdb": {"auto_collection-View"}},
        )

        view = CollectModelViewSet.as_view({"get": "network_config_file_supported_brands"})
        response = view(request)

        assert response.status_code == 200
        assert isinstance(response.data["items"], list)
