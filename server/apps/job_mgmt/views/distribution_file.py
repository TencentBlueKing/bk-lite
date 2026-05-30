"""分发文件视图"""

from datetime import datetime

from asgiref.sync import async_to_sync
from nanoid import generate
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.user_group import normalize_user_group_ids
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

        # 创建数据库记录
        # 记录文件归属团队，供删除/复用时的越权校验。
        # 优先使用 current_team cookie（用户当前所选团队，需属于该用户），否则回退首个所属组。
        user_group_ids = normalize_user_group_ids(getattr(request.user, "group_list", []) or [])
        team_id = None
        current_team_str = request.COOKIES.get("current_team")
        if current_team_str:
            try:
                current_team = int(current_team_str)
            except (TypeError, ValueError):
                current_team = None
            if current_team is not None and (getattr(request.user, "is_superuser", False) or current_team in user_group_ids):
                team_id = current_team
        if team_id is None and user_group_ids:
            team_id = user_group_ids[0]

        distribution_file = DistributionFile.objects.create(
            original_name=original_name,
            file_key=file_key,
            team=team_id,
        )
        log_operation(request, "create", "job", f"上传分发文件: {distribution_file.original_name}")

        return Response(
            {
                "id": distribution_file.id,
                "name": distribution_file.original_name,
            },
            status=status.HTTP_201_CREATED,
        )
