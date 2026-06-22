"""分发文件视图"""

from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from django.utils import timezone
from nanoid import generate
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.models import DistributionFile
from apps.job_mgmt.serializers.distribution_file import DistributionFileSerializer, DistributionFileUploadSerializer
from apps.node_mgmt.utils.s3 import upload_file_to_s3
from apps.system_mgmt.utils.operation_log_utils import log_operation


class DistributionFileViewSet(AuthViewSet):
    """分发文件视图集"""

    queryset = DistributionFile.objects.all()
    serializer_class = DistributionFileSerializer
    permission_key = "job"
    http_method_names = ["post"]

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser])
    @HasPermission("file_dist-Add")
    def upload(self, request):
        """
        上传分发文件

        使用 multipart/form-data 上传文件，存储到 JetStream Object Store。
        文件名会进行混淆处理，保证唯一性。

        请求体 (multipart/form-data):
        {
            "file": <文件>
        }

        返回:
        {
            "id": 1,
            "name": "原始文件名.txt"
        }
        """
        # BL-NEW-002：上传文件必须带团队归属，否则文件分发时无法做团队隔离。
        # 校验并取得当前用户有权访问的 current_team，作为文件归属团队。
        current_team = self._validate_current_team_permission(request)

        serializer = DistributionFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["file"]
        original_name = file.name

        # 生成混淆文件名：使用 nanoid 保证唯一性，保留扩展名
        ext = ""
        if "." in original_name:
            ext = "." + original_name.rsplit(".", 1)[-1]
        unique_id = generate(size=21)
        now = datetime.now()
        file_key = f"job-files/{now.year}/{now.month:02d}/{now.day:02d}/{unique_id}{ext}"

        # 上传到 JetStream Object Store
        async_to_sync(upload_file_to_s3)(file, file_key)

        # 创建数据库记录（带团队归属）。expire_at 必填（模型无默认），
        # 与开放上传接口一致默认 7 天后过期，由定时任务清理。
        distribution_file = DistributionFile.objects.create(
            original_name=original_name,
            file_key=file_key,
            expire_at=timezone.now() + timedelta(days=7),
            team=current_team,
        )
        log_operation(request, "create", "job", f"上传分发文件: {distribution_file.original_name}")

        return Response(
            {
                "id": distribution_file.id,
                "name": distribution_file.original_name,
            },
            status=status.HTTP_201_CREATED,
        )
