"""作业管理开放接口（第三方 App 调用）"""

from datetime import datetime

from asgiref.sync import async_to_sync
from nanoid import generate
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.logger import job_logger as logger
from apps.job_mgmt.models import DistributionFile
from apps.node_mgmt.utils.s3 import delete_s3_file, upload_file_to_s3


class OpenFileUploadView(APIView):
    """
    开放文件上传接口

    使用 UserAPISecret token 鉴权，供第三方 App 上传文件用于后续文件分发。

    鉴权方式：通过 Api-Authorization header 传入 api_secret，
    由全局 APISecretMiddleware 自动完成认证和 request.user 设置。

    请求:
        POST /api/v1/job_mgmt/api/open/upload_file
        Header: Api-Authorization: <api_secret>
        Body: multipart/form-data { file: <binary>, permanent: <bool> }

    参数:
        file: 必填，上传的文件
        permanent: 可选，是否永久保存（默认 false）
            - true: 文件永久保存，不会被定时清理
            - false: 文件在 7 天后自动清理

    返回:
        {"result": true, "data": {"file_id": 1, "file_key": "job-files/2026/05/06/xxx.rpm"}}
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        # 鉴权由 APISecretMiddleware + AuthMiddleware 在中间件层完成
        # 到达这里时 request.user 已是合法用户

        # 获取用户的 team（用于文件归属）
        user_team = None
        if hasattr(request.user, "group_list") and request.user.group_list:
            user_team = request.user.group_list[0]
        if user_team is None:
            return Response(
                {"detail": "用户未关联团队"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 文件校验
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"detail": "未上传文件"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 解析 permanent 参数（仅对外 API 支持）
        permanent_str = request.data.get("permanent", "false")
        is_permanent = str(permanent_str).lower() in ("true", "1", "yes")

        original_name = file.name

        # 生成混淆文件名
        ext = ""
        if "." in original_name:
            ext = "." + original_name.rsplit(".", 1)[-1]
        unique_id = generate(size=21)
        now = datetime.now()
        file_key = f"job-files/{now.year}/{now.month:02d}/{now.day:02d}/{unique_id}{ext}"

        # 上传到 JetStream Object Store
        try:
            async_to_sync(upload_file_to_s3)(file, file_key)
        except Exception as e:
            logger.error(f"[open_upload_file] 文件上传失败: {e}")
            return Response(
                {"detail": "文件上传失败"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 创建数据库记录
        distribution_file = DistributionFile.objects.create(
            original_name=original_name,
            file_key=file_key,
            is_permanent=is_permanent,
            team=user_team,
        )

        return Response(
            {"file_id": distribution_file.id, "file_key": distribution_file.file_key},
            status=status.HTTP_201_CREATED,
        )


class OpenFileDeleteView(APIView):
    """
    开放文件删除接口

    根据 file_key 删除对象存储中的文件及数据库记录。

    鉴权方式：通过 Api-Authorization header 传入 api_secret，
    由全局 APISecretMiddleware 自动完成认证。

    请求:
        DELETE /api/v1/job_mgmt/api/open/delete_file
        Header: Api-Authorization: <api_secret>
        Body: {"files": [{"file_id": 1, "file_key": "job-files/..."}]}

    返回:
        {"result": true, "data": {"deleted": 1}}
    """

    def delete(self, request):
        files = request.data.get("files", [])
        if not files:
            return Response(
                {"detail": "files 不能为空"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 获取当前用户的 team（用于权限校验）
        user_team = None
        if hasattr(request.user, "group_list") and request.user.group_list:
            user_team = request.user.group_list[0]

        # 校验格式并匹配删除
        deleted_count = 0
        no_permission = []  # 无权限的文件
        not_found = []  # 不存在的文件
        for item in files:
            file_id = item.get("file_id")
            file_key = item.get("file_key")
            if not file_id or not file_key:
                continue

            # 先查询文件是否存在
            try:
                df = DistributionFile.objects.get(id=file_id, file_key=file_key)
            except DistributionFile.DoesNotExist:
                not_found.append({"file_id": file_id, "file_key": file_key})
                continue

            # 校验 team 权限
            if df.team != user_team:
                no_permission.append({"file_id": file_id, "file_key": file_key})
                continue

            # 删除对象存储文件
            try:
                async_to_sync(delete_s3_file)(df.file_key)
            except Exception as e:
                logger.warning(f"[open_delete_file] 删除对象存储文件失败: {df.file_key}, error={e}")

            df.delete()
            deleted_count += 1

        result = {"deleted": deleted_count}
        if no_permission:
            result["no_permission"] = no_permission
        if not_found:
            result["not_found"] = not_found

        return Response(
            result,
            status=status.HTTP_200_OK,
        )
