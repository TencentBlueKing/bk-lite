from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.weopsx_cloud_catalog import fetch_weopsx_cloud_catalog


class WeopsxCloudCatalogViewSet(viewsets.ViewSet):
    """只读代理 WeOpsX GET /api/v1/cmp/cloud-nav/catalog。bk-lite 侧栏不接入此目录挂叶。"""

    @action(methods=["get"], detail=False, url_path="cloud-catalog")
    @HasPermission("view_list-View")
    def cloud_catalog(self, request):
        locale = request.query_params.get("locale") or getattr(request.user, "locale", None)
        payload = fetch_weopsx_cloud_catalog(
            locale=locale,
            authorization=request.headers.get("Authorization"),
        )
        return WebUtils.response_success(payload)
