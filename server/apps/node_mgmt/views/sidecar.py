from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.open_base import OpenAPIViewSet
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.utils.token_auth import token_auth


class SidecarViewSet(ViewSet):
    # @swagger_auto_schema(
    #     operation_id="sidecar_install_steps",
    #     operation_description="获取sidecar的安装步骤",
    #     manual_parameters=[
    #         openapi.Parameter("id", openapi.IN_PATH, description="节点ID", type=openapi.TYPE_INTEGER)
    #     ],
    # )
    # @action(detail=False, methods=["get"], url_path="install_steps/(?P<id>.+?)")
    # def install_steps(self, request, id):
    #     result = Sidecar().get_installation_steps()
    #     return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_id="sidecar_install_guide",
        operation_summary="获取sidecar的安装指南",
        manual_parameters=[
            openapi.Parameter("ip", openapi.IN_QUERY, description="节点ip", type=openapi.TYPE_STRING, required=True),
            openapi.Parameter("operating_system", openapi.IN_QUERY, description="操作系统", type=openapi.TYPE_STRING,
                              required=True, enum=["linux", "windows"]),
            openapi.Parameter("group", openapi.IN_QUERY, description="组织", type=openapi.TYPE_STRING, required=True),
        ],
        tags=['Sidecar']
    )
    @action(detail=False, methods=["get"], url_path="install_guide")
    def sidecar_install_guide(self, request):
        ip = request.query_params.get('ip')
        operating_system = request.query_params.get('operating_system')
        group = request.query_params.get('group')
        if operating_system.lower() not in ['windows', 'linux']:
            return WebUtils.response_error(error_message="operating_system参数错误, 只能为windows或linux")
        guide = Sidecar.get_sidecar_install_guide(ip, operating_system, group)
        return WebUtils.response_success(guide)


class OpenSidecarViewSet(OpenAPIViewSet):
    # @swagger_auto_schema(
    #     operation_id="download_sidecar_file",
    #     operation_description="获取sidecar的安装包文件",
    #     manual_parameters=[
    #         openapi.Parameter("file_name", openapi.IN_PATH, description="sidecar文件名称", type=openapi.TYPE_STRING)
    #     ],
    # )
    # @action(detail=False, methods=["get"], url_path="download_file/(?P<file_name>.+?)")
    # def download_sidecar_file(self, request, file_name):
    #     # 获取文件目录
    #     local_path = settings.CURRENT_FILE_PATH.rstrip("/") + "/sidecar/installation_package/"
    #     return download_local_file(local_path, file_name)

    @swagger_auto_schema(
        operation_id="sidecar_server_info",
        operation_description="获取服务器信息",
    )
    @action(detail=False, methods=["get"], url_path="node")
    @token_auth
    def server_info(self, request):
        return Sidecar.get_version()

    @swagger_auto_schema(
        operation_id="sidecar_collectors",
        operation_description="获取采集器列表",
    )
    @action(detail=False, methods=["get"], url_path="node/sidecar/collectors")
    @token_auth
    def collectors(self, request):
        return Sidecar.get_collectors(request)

    @swagger_auto_schema(
        operation_id="sidecar_node_configuration",
        operation_description="获取节点配置",
        manual_parameters=[
            openapi.Parameter("node_id", openapi.IN_PATH, description="节点ID", type=openapi.TYPE_STRING),
            openapi.Parameter("configuration_id", openapi.IN_PATH, description="配置ID", type=openapi.TYPE_STRING),
        ],
    )
    @action(detail=False, methods=["get"],
            url_path="node/sidecar/configurations/render/(?P<node_id>.+?)/(?P<configuration_id>.+?)")
    @token_auth
    def configuration(self, request, node_id, configuration_id):
        return Sidecar.get_node_config(request, node_id, configuration_id)

    @swagger_auto_schema(
        operation_id="sidecar_update_client",
        operation_description="更新sidecar客户端",
        manual_parameters=[
            openapi.Parameter("node_id", openapi.IN_PATH, description="节点ID", type=openapi.TYPE_STRING)
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "node_name": openapi.Schema(type=openapi.TYPE_STRING, description="节点名称"),
                "node_details": openapi.Schema(type=openapi.TYPE_OBJECT, description="节点详情"),
            },
        ),
    )
    @action(detail=False, methods=["PUT"], url_path="node/sidecars/(?P<node_id>.+?)")
    @token_auth
    def update_sidecar_client(self, request, node_id):
        return Sidecar.update_node_client(request, node_id)
