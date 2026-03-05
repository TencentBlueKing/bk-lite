"""目标管理视图"""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.logger import logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.target import TargetFilter
from apps.job_mgmt.models import Target
from apps.job_mgmt.serializers.target import (
    TargetBatchDeleteSerializer,
    TargetCreateSerializer,
    TargetSerializer,
    TargetTestConnectionSerializer,
    TargetUpdateSerializer,
)
from apps.job_mgmt.services.target_sync import TargetSyncService


class TargetViewSet(AuthViewSet):
    """目标管理视图集"""

    queryset = Target.objects.all()
    serializer_class = TargetSerializer
    filterset_class = TargetFilter
    search_fields = ["name", "ip"]
    ORGANIZATION_FIELD = "team"

    def get_serializer_class(self):
        if self.action == "create":
            return TargetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return TargetUpdateSerializer
        elif self.action == "batch_delete":
            return TargetBatchDeleteSerializer
        elif self.action == "test_connection":
            return TargetTestConnectionSerializer
        return TargetSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # 返回完整的对象信息
        instance = Target.objects.get(pk=serializer.instance.pk)
        response_serializer = TargetSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
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
    def sync_from_nodes(self, request):
        """
        从 Node 同步目标

        请求体:
        {
            "node_ids": ["node-1", "node-2"],  // 可选，不传则同步全部
            "team": [1, 2]  // 必填，目标归属团队
        }
        """
        node_ids = request.data.get("node_ids", [])
        team = request.data.get("team", [])

        if not team:
            return Response(
                {"error": "team 字段必填"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = TargetSyncService()
        result = service.sync_nodes(node_ids=node_ids, team=team)

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def test_connection(self, request):
        """
        测试 SSH 连接

        请求体:
        {
            "ip": "192.168.1.100",
            "cloud_region_id": "region-1",
            "driver": "ansible",
            "credential_source": "manual",
            "credential_id": "",  // 凭据管理时必填
            "ssh_port": 22,
            "ssh_user": "root",
            "ssh_credential_type": "password",
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

        # TODO: 实际连接测试逻辑
        # 当前返回模拟结果，后续对接执行器 (rpc/executor.py)
        # 需要根据 driver 类型和凭据信息执行 SSH 连接测试

        ip = validated_data.get("ip")
        ssh_user = validated_data.get("ssh_user", "")
        ssh_port = validated_data.get("ssh_port", 22)

        logger.info(f"Test connection request: {ssh_user}@{ip}:{ssh_port}")

        # 模拟连接测试结果
        return Response(
            {
                "success": True,
                "message": f"连接测试功能待实现（{ssh_user}@{ip}:{ssh_port}）",
            },
            status=status.HTTP_200_OK,
        )
