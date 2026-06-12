"""作业管理开放接口（第三方 App 调用）"""

from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from django.utils import timezone
from nanoid import generate
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.logger import job_logger as logger
from apps.job_mgmt.models import DistributionFile
from apps.node_mgmt.utils.s3 import delete_s3_file, upload_file_to_s3

# 文件过期天数：默认值与上下限
DEFAULT_EXPIRE_DAYS = 7
MAX_EXPIRE_DAYS = 365


def _parse_expire_days(raw):
    """
    解析 expire_days 参数。

    Returns:
        tuple: (expire_days, error_message)
        - 合法时返回 (int, None)
        - 非法时返回 (None, error_message)
    """
    if raw is None or raw == "":
        return DEFAULT_EXPIRE_DAYS, None
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None, "expire_days 非法"
    if days < 1 or days > MAX_EXPIRE_DAYS:
        return None, "expire_days 非法"
    return days, None


def _get_user_team_from_request(request):
    """
    获取用户的 team。

    - API Secret 认证 (api_pass=True)：直接使用 group_list[0]（即 UserAPISecret.team）
    - Auth Backend 认证 (api_pass=False)：优先使用 current_team cookie，需要权限校验

    Returns:
        tuple: (team_id, error_message)
        - 成功时返回 (team_id, None)
        - 失败时返回 (None, error_message)
    """
    group_list = getattr(request.user, "group_list", [])

    # 提取 group_ids（兼容 [int] 和 [{"id": int}] 两种格式）
    user_group_ids = []
    for g in group_list:
        if isinstance(g, dict):
            user_group_ids.append(g["id"])
        else:
            user_group_ids.append(g)

    if not user_group_ids:
        return None, "用户未关联团队"

    # API Secret 认证：直接使用 group_list[0]（即 UserAPISecret.team）
    if getattr(request, "api_pass", False):
        return user_group_ids[0], None

    # Auth Backend 认证：优先使用 current_team cookie
    current_team_str = request.COOKIES.get("current_team")
    if current_team_str:
        try:
            current_team = int(current_team_str)
        except (TypeError, ValueError):
            return None, "current_team 参数非法"

        # 校验用户是否有权限访问该 team
        if not getattr(request.user, "is_superuser", False):
            if current_team not in user_group_ids:
                return None, "无权访问该团队数据"

        return current_team, None

    # 没有 current_team，使用 group_list[0]
    return user_group_ids[0], None


class OpenFileUploadView(APIView):
    """
    开放文件上传接口

    使用 UserAPISecret token 鉴权，供第三方 App 上传文件用于后续文件分发。

    鉴权方式：通过 Api-Authorization header 传入 api_secret，
    由全局 APISecretMiddleware 自动完成认证和 request.user 设置。

    请求:
        POST /api/v1/job_mgmt/api/open/upload_file
        Header: Api-Authorization: <api_secret>
        Body: multipart/form-data { file: <binary>, expire_days: <int> }

    参数:
        file: 必填，上传的文件
        expire_days: 可选，过期天数（默认 7，范围 1-365）
            文件在 expire_days 天后由定时任务自动清理；不存在永久保存选项。

    返回:
        {"result": true, "data": {"file_id": 1, "file_key": "job-files/2026/05/06/xxx.rpm"}}
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        # 鉴权由 APISecretMiddleware + AuthMiddleware 在中间件层完成
        # 到达这里时 request.user 已是合法用户

        # 获取用户的 team（用于文件归属）
        # 优先使用 current_team cookie，否则使用 group_list[0]
        user_team, error = _get_user_team_from_request(request)
        if error:
            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 文件校验
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"detail": "未上传文件"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 解析 expire_days 参数（默认 7 天，范围 1-365）
        expire_days, expire_error = _parse_expire_days(request.data.get("expire_days"))
        if expire_error:
            return Response(
                {"detail": expire_error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expire_at = timezone.now() + timedelta(days=expire_days)

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
            expire_at=expire_at,
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
        # 优先使用 current_team cookie，否则使用 group_list[0]
        user_team, error = _get_user_team_from_request(request)
        if error:
            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
