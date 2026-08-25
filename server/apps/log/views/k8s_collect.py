from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.log.services.k8s_collect import K8sLogCollectService
from apps.log.views.collect_config import CollectInstanceViewSet
from apps.rpc.node_mgmt import NodeMgmt


class K8sCollectViewSet(viewsets.ViewSet):
    @staticmethod
    def _normalize_organizations(organizations):
        if not isinstance(organizations, list):
            return None

        normalized = []
        for organization in organizations:
            if isinstance(organization, bool) or not isinstance(organization, (int, str)):
                return None
            try:
                normalized.append(int(organization))
            except ValueError:
                return None
        return normalized

    @action(methods=["get"], detail=False, url_path="cloud_region_list")
    def cloud_region_list(self, request):
        data = NodeMgmt().cloud_region_list()
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="create_instance")
    def create_instance(self, request):
        organizations = request.data.get("organizations", [])
        if not organizations:
            return WebUtils.response_error("organizations is required")

        organizations = self._normalize_organizations(organizations)
        if organizations is None:
            return WebUtils.response_error(error_message="organizations must contain only integer values")

        error_response = CollectInstanceViewSet()._authorize_target_organizations(
            request,
            organizations,
            request.data.get("collect_type_id"),
        )
        if error_response:
            return error_response
        data = K8sLogCollectService.create_k8s_collect_instance({**request.data, "organizations": organizations})
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="generate_install_command")
    def generate_install_command(self, request):
        instances, error_response = CollectInstanceViewSet()._authorize_instances(request, [request.data.get("instance_id")])
        if error_response:
            return error_response
        command = K8sLogCollectService.generate_install_command(
            instances[0].id,
            request.data.get("cloud_region_id"),
            request.data.get("image_registry_prefix"),
        )
        return WebUtils.response_success(command)

    @action(methods=["get", "post"], detail=False, url_path="collect_setting")
    def collect_setting(self, request):
        if request.method == "GET":
            instance_id = request.query_params.get("instance_id")
            instances, error_response = CollectInstanceViewSet()._authorize_instances(
                request,
                [instance_id],
                required_permission="View",
            )
            if error_response:
                return error_response
            data = K8sLogCollectService.get_setting(instances[0].id)
            return WebUtils.response_success(data)

        instance_id = request.data.get("instance_id")
        cloud_region_id = request.data.get("cloud_region_id")
        if not cloud_region_id:
            return WebUtils.response_error("cloud_region_id is required")
        instances, error_response = CollectInstanceViewSet()._authorize_instances(request, [instance_id])
        if error_response:
            return error_response
        setting = K8sLogCollectService.save_setting(instances[0].id, request.data)
        command = K8sLogCollectService.generate_install_command(
            instances[0].id,
            cloud_region_id,
            request.data.get("image_registry_prefix"),
        )
        return WebUtils.response_success({**setting, "command": command})

    @action(methods=["post"], detail=False, url_path="check_collect_status")
    def check_collect_status(self, request):
        instances, error_response = CollectInstanceViewSet()._authorize_instances(
            request,
            [request.data.get("instance_id")],
            required_permission="View",
        )
        if error_response:
            return error_response
        success = K8sLogCollectService.check_collect_status(instances[0].id)
        return WebUtils.response_success({"success": success})
