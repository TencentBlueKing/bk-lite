from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services.infra import InfraService


class InfraViewSet(ViewSet):
    """基础设施配置视图 - 代理外部 infra render API"""

    @action(methods=['post'], detail=False, url_path='render')
    def render(self, request):
        """
        渲染基础设施配置 YAML（使用限时令牌）

        请求参数:
        - token: 限时令牌（5分钟有效，最多使用5次）

        返回:
        - 纯 YAML 文本，可直接用于 kubectl apply -f -
        """
        token = request.data.get("token")

        if not token:
            raise BaseAppException("Missing required parameter: token")

        # 调用 InfraService 验证令牌并获取参数（带次数限制）
        token_data = InfraService.validate_and_get_token_data(token)

        cluster_name = token_data.get("cluster_name")
        cloud_region_id = token_data.get("cloud_region_id")
        remaining_usage = token_data.get("remaining_usage", 0)

        # 调用 InfraService 渲染配置
        yaml_content = InfraService.render_config_from_cloud_region(
            cluster_name=cluster_name,
            cloud_region_id=cloud_region_id,
            config_type="metric",
        )

        # 在响应头中添加剩余使用次数信息
        response = HttpResponse(yaml_content, content_type='text/yaml; charset=utf-8')
        response['X-Token-Remaining-Usage'] = str(remaining_usage)

        return response
