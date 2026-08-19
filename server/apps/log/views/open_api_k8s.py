from django.http import HttpResponse
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.open_base import OpenAPIViewSet
from apps.log.services.k8s_collect import K8sLogCollectService


class K8sOpenAPIViewSet(OpenAPIViewSet):
    @action(methods=["post"], detail=False, url_path="render")
    def render(self, request):
        token = request.data.get("token")
        if not token:
            raise BaseAppException("Missing required parameter: token")

        token_data = K8sLogCollectService.validate_and_get_token_data(token)
        yaml_content = K8sLogCollectService.render_config_from_cloud_region(
            token_data.get("cluster_name"),
            token_data.get("cloud_region_id"),
        )
        response = HttpResponse(yaml_content, content_type="text/yaml; charset=utf-8")
        response["X-Token-Remaining-Usage"] = str(token_data.get("remaining_usage", 0))
        return response
