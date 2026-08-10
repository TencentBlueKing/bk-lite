from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.cmdb.services.k8s_setup import K8sSetupService
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.open_base import OpenAPIViewSet
from apps.core.utils.web_utils import WebUtils


class K8sSetupViewSet(ViewSet):
    """CMDB k8s 引导式接入（内部接口，需要鉴权）"""

    @action(methods=["post"], detail=False, url_path="install_token")
    @HasPermission("auto_collection-Execute")
    def install_token(self, request):
        collector_cluster_id = request.data.get("collector_cluster_id")
        cloud_region_id = request.data.get("cloud_region_id")
        if cloud_region_id in (None, ""):
            raise BaseAppException("cloud_region_id is required")
        data = K8sSetupService.generate_install_token(collector_cluster_id, cloud_region_id)
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="install_command")
    @HasPermission("auto_collection-Execute")
    def install_command(self, request):
        """后端生成安装命令（URL 直连 Django open_api，不走 Next.js 代理）"""
        collector_cluster_id = request.data.get("collector_cluster_id")
        cloud_region_id = request.data.get("cloud_region_id")
        if cloud_region_id in (None, ""):
            raise BaseAppException("cloud_region_id is required")
        data = K8sSetupService.generate_install_command(collector_cluster_id, cloud_region_id)
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="verify")
    @HasPermission("auto_collection-View")
    def verify(self, request):
        collector_cluster_id = request.data.get("collector_cluster_id")
        data = K8sSetupService.verify_collector_reporting(collector_cluster_id)
        return WebUtils.response_success(data)


class K8sSetupOpenViewSet(OpenAPIViewSet):
    """CMDB k8s 接入 open API：根据 token 渲染 YAML（kubectl 直接拉取）"""

    @action(methods=["post"], detail=False, url_path="render")
    def render(self, request):
        token = request.data.get("token")
        if not token:
            raise BaseAppException("Missing required parameter: token")

        data = K8sSetupService.render_yaml_by_token(token)
        response = HttpResponse(data["yaml"], content_type="text/yaml; charset=utf-8")
        response["X-Token-Remaining-Usage"] = str(data.get("remaining_usage", 0))
        return response
