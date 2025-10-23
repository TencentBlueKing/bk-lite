from rest_framework.decorators import action

from apps.core.utils.open_base import OpenAPIViewSet
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.utils.token_auth import check_token_auth


class OpenSidecarViewSet(OpenAPIViewSet):
    @action(detail=False, methods=["get"], url_path="node")
    def server_info(self, request):
        node_id = request.query_params.get("node_id")
        check_token_auth(node_id, request)
        return Sidecar.get_version(request)

    @action(detail=False, methods=["get"], url_path="node/sidecar/collectors")
    def collectors(self, request):
        node_id = request.query_params.get("node_id")
        check_token_auth(node_id, request)
        return Sidecar.get_collectors(request)

    @action(detail=False, methods=["get"],
            url_path="node/sidecar/configurations/render/(?P<node_id>.+?)/(?P<configuration_id>.+?)")
    def configuration(self, request, node_id, configuration_id):
        check_token_auth(node_id, request)
        return Sidecar.get_node_config(request, node_id, configuration_id)

    @action(detail=False, methods=["get"],
            url_path="node/sidecar/env_config/(?P<node_id>.+?)/(?P<configuration_id>.+?)")
    def configuration_env(self, request, node_id, configuration_id):
        check_token_auth(node_id, request)
        return Sidecar.get_node_config_env(request, node_id, configuration_id)

    @action(detail=False, methods=["PUT"], url_path="node/sidecars/(?P<node_id>.+?)")
    def update_sidecar_client(self, request, node_id):
        check_token_auth(node_id, request)
        return Sidecar.update_node_client(request, node_id)
