"""Playbook视图"""

import io
import zipfile

from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.job_mgmt.filters.playbook import PlaybookFilter
from apps.job_mgmt.models import Playbook
from apps.job_mgmt.serializers.playbook import (
    PlaybookBatchDeleteSerializer,
    PlaybookCreateSerializer,
    PlaybookDetailSerializer,
    PlaybookListSerializer,
    PlaybookUpdateSerializer,
    PlaybookUpgradeSerializer,
)


class PlaybookViewSet(AuthViewSet):
    """Playbook视图集"""

    queryset = Playbook.objects.all()
    serializer_class = PlaybookDetailSerializer
    filterset_class = PlaybookFilter
    search_fields = ["name", "version"]
    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    def get_serializer_class(self):
        if self.action == "list":
            return PlaybookListSerializer
        elif self.action == "retrieve":
            return PlaybookDetailSerializer
        elif self.action == "create":
            return PlaybookCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return PlaybookUpdateSerializer
        elif self.action == "upgrade":
            return PlaybookUpgradeSerializer
        elif self.action == "batch_delete":
            return PlaybookBatchDeleteSerializer
        return PlaybookDetailSerializer

    @HasPermission("playbook_library-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("playbook_library-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("playbook_library-Add")
    def create(self, request, *args, **kwargs):
        """
        创建 Playbook（文件上传）

        上传 ZIP 文件，后端自动提取文件名作为 Playbook 名称。

        请求体 (multipart/form-data):
        {
            "file": <ZIP 文件>,  // 必填，支持 .zip, .tar.gz, .tgz
            "version": "v1.0.0",  // 可选，默认 v1.0.0
            "team": [1, 2]  // 可选，团队 ID 列表
        }

        返回:
        {
            "id": 1,
            "name": "my-playbook",  // 从文件名自动提取
            "version": "v1.0.0",
            "file_name": "my-playbook.zip",
            "file_key": "playbooks/2026/03/05/my-playbook.zip",
            "bucket_name": "job-mgmt-private",
            "file_size": 12345,
            "team": [1, 2],
            "created_by": "admin",
            "created_at": "2026-03-05T12:00:00Z",
            "updated_by": "admin",
            "updated_at": "2026-03-05T12:00:00Z"
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        # 返回完整的对象信息
        response_serializer = PlaybookDetailSerializer(instance, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    @HasPermission("playbook_library-Delete")
    def batch_delete(self, request):
        """批量删除Playbook"""
        serializer = PlaybookBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        # 只删除当前用户有权限的Playbook
        queryset = self.filter_queryset(self.get_queryset())
        playbooks = queryset.filter(id__in=ids)

        # 先批量删除 MinIO 文件
        for playbook in playbooks:
            if playbook.file:
                playbook.file.delete(save=False)

        # 再批量删除数据库记录
        deleted_count, _ = playbooks.delete()

        return Response({"deleted_count": deleted_count}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    @HasPermission("playbook_library-Edit")
    def upgrade(self, request, pk=None):
        """
        更新 Playbook 版本

        上传新的 ZIP 文件，可选填写新版本号。
        不填写版本号则自动在当前版本上 +0.0.1。

        请求体 (multipart/form-data):
        {
            "file": <ZIP 文件>,  // 必填
            "version": "v1.1.0"  // 可选，不填则自动 +0.0.1
        }
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.update(instance, serializer.validated_data)

        response_serializer = PlaybookDetailSerializer(instance, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    @HasPermission("playbook_library-View")
    def download(self, request, pk=None):
        """
        下载 Playbook 文件

        返回 Playbook 压缩包文件流
        """
        instance = self.get_object()

        if not instance.file:
            return Response({"detail": "文件不存在"}, status=status.HTTP_404_NOT_FOUND)

        file_handle = instance.file.open("rb")
        response = FileResponse(file_handle, as_attachment=True, filename=instance.file_name)
        return response

    @action(detail=False, methods=["get"])
    @HasPermission("playbook_library-View")
    def download_template(self, request):
        """下载 Playbook 模板压缩包。"""
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(
                "playbook-template/playbook.yml",
                "---\n- name: Example Playbook\n  hosts: all\n  gather_facts: false\n\n  roles:\n    - example\n",
            )
            zip_file.writestr(
                "playbook-template/README.md",
                "# Playbook 模板示例\n\n"
                "这是一个可直接运行的 Playbook 模板。\n\n"
                "## 目录说明\n\n"
                "- `playbook.yml`：Playbook 入口文件（`hosts: all`，由系统自动注入目标主机）\n"
                "- `README.md`：Playbook 说明文档\n"
                "- `roles/example/tasks/main.yml`：任务示例\n"
                "- `roles/example/vars/main.yml`：变量示例\n\n"
                "## 执行说明\n\n"
                "上传后在「快速执行」中选择目标主机即可运行，系统会自动生成 inventory。\n\n"
                "## 自定义建议\n\n"
                "1. 按业务需要修改 `roles/example/tasks/main.yml`\n"
                "2. 在 `vars/main.yml` 中补充变量\n"
                "3. 如果需要多角色，可以在 `roles/` 下继续增加目录\n",
            )
            zip_file.writestr(
                "playbook-template/roles/example/tasks/main.yml",
                '---\n- name: Print hello message\n  debug:\n    msg: "{{ message }}"\n',
            )
            zip_file.writestr(
                "playbook-template/roles/example/vars/main.yml",
                '---\nmessage: "Hello from playbook template"\n',
            )
            zip_file.writestr("playbook-template/roles/example/templates/.gitkeep", "")

        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename="playbook-template.zip", content_type="application/zip")
