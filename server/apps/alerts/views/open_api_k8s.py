from django.http import HttpResponse
from rest_framework.decorators import action

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.service.k8s_install import K8sInstallService
from apps.alerts.views.alert_source import K8S_SOURCE_ID, AlertSourceModelViewSet
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.open_base import OpenAPIViewSet


class K8sOpenAPIViewSet(OpenAPIViewSet):
    @action(methods=["post"], detail=False, url_path="render")
    def render(self, request):
        token = request.data.get("token")
        if not token:
            raise BaseAppException("Missing required parameter: token")

        token_data = K8sInstallService.validate_and_get_token_data(token)
        source = AlertSource.objects.filter(source_id=K8S_SOURCE_ID).first()
        if not source:
            raise BaseAppException("K8s alert source not found")

        yaml_content = AlertSourceModelViewSet._build_k8s_deploy_yaml(
            receiver_url=token_data["receiver_url"],
            secret=token_data["secret"],
            cluster_name=token_data["cluster_name"],
            push_source_id=token_data["push_source_id"],
        )
        response = HttpResponse(yaml_content, content_type="text/yaml; charset=utf-8")
        response["X-Token-Remaining-Usage"] = str(token_data.get("remaining_usage", 0))
        return response
