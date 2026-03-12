"""目标管理视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import job_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.target import TargetFilter
from apps.job_mgmt.models import Target
from apps.job_mgmt.serializers.target import TargetBatchDeleteSerializer, TargetSerializer, TargetTestConnectionSerializer
from apps.node_mgmt.models import CloudRegion
from apps.rpc.executor import Executor
from apps.rpc.node_mgmt import NodeMgmt


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

        # 组织权限过滤
        current_team = request.COOKIES.get("current_team")
        if current_team:
            query_data["organization_ids"] = [current_team]

        try:
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
        测试连接

        根据 os_type 决定使用 SSH (Linux) 或 WinRM (Windows) 连接。

        请求体:
        {
            "ip": "192.168.1.100",
            "os_type": "linux",  // linux 或 windows，默认 linux
            "cloud_region_id": "region-1",
            "driver": "ansible",
            "credential_source": "manual",
            "credential_id": "",  // 凭据管理时必填
            // Linux SSH 字段
            "ssh_port": 22,
            "ssh_user": "root",
            "ssh_credential_type": "password",
            "ssh_password": "xxx",  // 密码方式必填
            "ssh_key_file": <file>,  // 密钥方式必填
            // Windows WinRM 字段
            "winrm_port": 5986,
            "winrm_scheme": "https",  // http 或 https
            "winrm_user": "Administrator",
            "winrm_password": "xxx",
            "winrm_cert_validation": true  // 是否验证证书
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

        # TODO: 实际连接测试逻辑
        # 当前返回模拟结果，后续对接执行器 (rpc/executor.py)
        # 需要根据 os_type 和凭据信息执行 SSH 或 WinRM 连接测试

        ip = validated_data.get("ip")
        os_type = validated_data.get("os_type", "linux")

        if os_type == "linux":
            user = validated_data.get("ssh_user", "")
            port = validated_data.get("ssh_port", 22)
            logger.info(f"Test SSH connection: {user}@{ip}:{port}")
            message = f"连接测试功能待实现（SSH {user}@{ip}:{port}）"
        else:
            user = validated_data.get("winrm_user", "")
            port = validated_data.get("winrm_port", 5986)
            scheme = validated_data.get("winrm_scheme", "https")
            logger.info(f"Test WinRM connection: {user}@{ip}:{port} ({scheme})")
            message = f"连接测试功能待实现（WinRM {user}@{ip}:{port} {scheme}）"

        return Response({"success": True, "message": message}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    @HasPermission("target-View")
    def test_target_connection(self, request, pk=None):
        """
        测试已有目标的连接

        通过 node 执行简单脚本测试连接（需要 node_id）
        """
        target = self.get_object()

        if not target.node_id:
            return Response(
                {"success": False, "message": "目标缺少 node_id，无法测试连接"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            executor = Executor(target.node_id)
            # 根据操作系统选择测试命令
            if target.os_type == "windows":
                test_command = "echo yes"
                shell = "cmd"
            else:
                test_command = "echo yes"
                shell = "sh"

            result = executor.execute_local(test_command, timeout=30, shell=shell)

            exit_code = result.get("exit_code", result.get("code", -1))
            stdout = result.get("stdout", "").strip()

            if exit_code == 0 and "yes" in stdout:
                logger.info(f"Target {target.name}({target.ip}) connection test passed")
                return Response(
                    {"success": True, "message": "连接测试成功"},
                    status=status.HTTP_200_OK,
                )
            else:
                logger.warning(f"Target {target.name}({target.ip}) connection test failed: exit_code={exit_code}, stdout={stdout}")
                return Response(
                    {"success": False, "message": f"连接测试失败: exit_code={exit_code}"},
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            logger.exception(f"Target {target.name}({target.ip}) connection test error: {e}")
            return Response(
                {"success": False, "message": f"连接测试异常: {str(e)}"},
                status=status.HTTP_200_OK,
            )
