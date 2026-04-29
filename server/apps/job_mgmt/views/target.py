"""目标管理视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import job_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.constants import OSType, SSHCredentialType
from apps.job_mgmt.filters.target import TargetFilter
from apps.job_mgmt.models import Target
from apps.job_mgmt.serializers.target import TargetBatchDeleteSerializer, TargetSerializer, TargetTestConnectionSerializer
from apps.node_mgmt.models import CloudRegion
from apps.rpc.executor import Executor
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.system_mgmt import SystemMgmt


def _get_executor_node(cloud_region_id: int) -> str:
    """
    根据云区域ID获取执行节点

    Args:
        cloud_region_id: 云区域ID

    Returns:
        节点ID

    Raises:
        ValueError: 未找到可用的执行节点
    """
    node_mgmt = NodeMgmt()
    result = node_mgmt.node_list(
        {
            "cloud_region_id": cloud_region_id,
            "is_container": True,
            "page": 1,
            "page_size": 1,
        }
    )
    if not isinstance(result, dict):
        raise ValueError(f"云区域 {cloud_region_id} 下未找到可用的执行节点")
    nodes = result.get("nodes", [])
    if not nodes:
        raise ValueError(f"云区域 {cloud_region_id} 下未找到可用的执行节点")
    return nodes[0]["id"]


def _parse_ssh_test_result(result) -> tuple[bool, str, str]:
    """解析 SSH 测试连接返回结果，兼容字符串与字典两种格式"""
    if isinstance(result, str):
        return ("success" in result, result, "")

    if isinstance(result, dict):
        success = result.get("success", False)
        stdout = result.get("result", "")
        error = result.get("error", "")
        return success, str(stdout), str(error)

    return False, str(result), f"未知返回类型: {type(result).__name__}"


def _build_actor_context(request):
    current_team = request.COOKIES.get("current_team")
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")

    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
    }


class TargetViewSet(AuthViewSet):
    """目标管理视图集"""

    queryset = Target.objects.all()
    serializer_class = TargetSerializer
    filterset_class = TargetFilter
    search_fields = ["name", "ip"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    def get_serializer_class(self):
        if self.action == "batch_delete":
            return TargetBatchDeleteSerializer
        elif self.action == "test_connection":
            return TargetTestConnectionSerializer
        return TargetSerializer

    @HasPermission("target-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("target-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("target-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    @HasPermission("target-View")
    def query_nodes(self, request):
        """
        从节点管理查询节点列表

        直接查询 node_mgmt 的节点数据，不做同步存储，支持筛选和分页。
        返回格式与手动添加目标保持一致，方便前端统一处理。

        查询参数:
            cloud_region_id: 云区域ID (可选)
            name: 节点名称，模糊匹配 (可选)
            ip: IP地址，模糊匹配 (可选)
            os: 操作系统 linux/windows (可选)
            page: 页码，默认1
            page_size: 每页数量，默认20

        返回:
        {
            "result": true,
            "data": {
                "count": 100,
                "items": [
                    {
                        "id": "node-1",
                        "name": "节点1",
                        "ip": "192.168.1.100",
                        "os_type": "linux",
                        "cloud_region_id": 1,
                        "cloud_region_name": "默认区域",
                        "source": "node_mgmt"
                    }
                ]
            }
        }
        """
        # 构建查询参数
        query_data = {
            "page": int(request.query_params.get("page", 1)),
            "page_size": int(request.query_params.get("page_size", 20)),
        }

        # 可选筛选条件
        cloud_region_id = request.query_params.get("cloud_region_id")
        if cloud_region_id:
            query_data["cloud_region_id"] = int(cloud_region_id)

        name = request.query_params.get("name")
        if name:
            query_data["name"] = name

        ip = request.query_params.get("ip")
        if ip:
            query_data["ip"] = ip

        os_type = request.query_params.get("os")
        if os_type:
            query_data["os"] = os_type

        try:
            actor_context = _build_actor_context(request)
            include_children = actor_context["include_children"]
            scope_result = SystemMgmt().get_authorized_groups_scoped(actor_context, include_children=include_children)
            query_data["organization_ids"] = scope_result.get("data", [])

            if not request.user.is_superuser:
                query_data["permission_data"] = {
                    "username": request.user.username,
                    "domain": request.user.domain,
                    "current_team": actor_context["current_team"],
                    "include_children": include_children,
                }

            node_mgmt = NodeMgmt()
            result = node_mgmt.node_list(query_data)

            # 获取云区域名称映射

            cloud_regions = CloudRegion.objects.all().values("id", "name")
            cloud_region_map = {cr["id"]: cr["name"] for cr in cloud_regions}

            # 转换字段名，统一格式
            unified_items = []
            for node in result.get("nodes", []):
                cloud_region_id = node.get("cloud_region")
                unified_items.append(
                    {
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "ip": node.get("ip"),
                        "os_type": node.get("operating_system", "linux"),
                        "cloud_region_id": cloud_region_id,
                        "cloud_region_name": cloud_region_map.get(cloud_region_id, ""),
                        "source": "node_mgmt",
                    }
                )

            return Response(
                {
                    "result": True,
                    "data": {
                        "count": result.get("count", 0),
                        "items": unified_items,
                    },
                }
            )
        except BaseAppException as e:
            return Response(
                {"result": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception(f"[query_nodes] 查询节点失败: {e}")
            return Response(
                {"result": False, "message": f"查询节点失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"])
    @HasPermission("target-View")
    def cloud_regions(self, request):
        """
        获取云区域列表

        返回:
        {
            "result": true,
            "data": [
                {"id": 1, "name": "默认区域"},
                ...
            ]
        }
        """
        try:
            node_mgmt = NodeMgmt()
            result = node_mgmt.cloud_region_list()
            return Response({"result": True, "data": result})
        except Exception as e:
            logger.exception(f"[cloud_regions] 查询云区域失败: {e}")
            return Response(
                {"result": False, "message": f"查询云区域失败: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"])
    @HasPermission("target-Delete")
    def batch_delete(self, request):
        """批量删除目标"""
        serializer = TargetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        # 只删除当前用户有权限的目标
        queryset = self.filter_queryset(self.get_queryset())
        deleted_count, _ = queryset.filter(id__in=ids).delete()

        return Response({"deleted_count": deleted_count}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    @HasPermission("target-View")
    def test_connection(self, request):
        """
        测试连接（仅支持 Linux SSH）

        通过 nats-executor 执行 echo success 命令测试 SSH 连接。

        请求体:
        {
            "ip": "192.168.1.100",
            "os_type": "linux",  // 目前仅支持 linux
            "cloud_region_id": 1,
            "ssh_port": 22,
            "ssh_user": "root",
            "ssh_credential_type": "password",  // password 或 key
            "ssh_password": "xxx",  // 密码方式必填
            "ssh_key_file": <file>  // 密钥方式必填
        }

        返回:
        {
            "success": true,
            "message": "连接成功"
        }
        """
        serializer = TargetTestConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        ip = validated_data.get("ip")
        os_type = validated_data.get("os_type", OSType.LINUX)
        cloud_region_id = validated_data.get("cloud_region_id")

        # Windows 暂不支持
        if os_type == OSType.WINDOWS:
            return Response({"success": False, "message": "Windows 测试连接暂不支持"})

        # 获取执行节点
        try:
            node_id = _get_executor_node(cloud_region_id)
        except ValueError as e:
            logger.warning(f"[test_connection] 获取执行节点失败: {e}")
            return Response({"success": False, "message": str(e)})

        # 构建 SSH 凭据
        ssh_user = validated_data.get("ssh_user", "")
        ssh_port = validated_data.get("ssh_port", 22)
        ssh_credential_type = validated_data.get("ssh_credential_type", SSHCredentialType.PASSWORD)

        password = None
        private_key = None

        if ssh_credential_type == SSHCredentialType.PASSWORD:
            password = validated_data.get("ssh_password", "")
        else:
            # 密钥方式：读取上传的文件内容
            ssh_key_file = validated_data.get("ssh_key_file")
            if ssh_key_file:
                private_key = ssh_key_file.read().decode("utf-8")

        # 执行测试命令
        try:
            logger.info(f"[test_connection] Testing SSH: {ssh_user}@{ip}:{ssh_port} via node {node_id}")
            executor = Executor(node_id)
            result = executor.execute_ssh(
                command="echo success", host=str(ip), username=ssh_user, password=password, private_key=private_key, timeout=30, port=ssh_port
            )
            # 解析结果（兼容字符串与字典）
            success, stdout, error = _parse_ssh_test_result(result)

            if success and "success" in stdout:
                logger.info(f"[test_connection] SSH connection test passed: {ssh_user}@{ip}:{ssh_port}")
                return Response({"success": True, "message": "连接测试成功"})
            else:
                error_msg = error if error else f"输出异常: {stdout}"
                logger.warning(f"[test_connection] SSH connection test failed: {ssh_user}@{ip}:{ssh_port}, error: {error_msg}")
                return Response({"success": False, "message": f"连接测试失败: {error_msg}"})

        except Exception as e:
            logger.exception(f"[test_connection] SSH connection test error: {ssh_user}@{ip}:{ssh_port}, error: {e}")
            return Response({"success": False, "message": f"连接测试异常: {str(e)}"})
