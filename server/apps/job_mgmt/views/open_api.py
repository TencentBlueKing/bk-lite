"""作业管理开放接口（第三方 App 调用）"""

import os
from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from django.utils import timezone
from nanoid import generate
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.logger import job_logger as logger
from apps.job_mgmt.models import DistributionFile, JobExecution
from apps.job_mgmt.nats_api import job_detail_query, job_list, job_script_execute, job_status_batch_query
from apps.job_mgmt.utils.team_authz import is_team_authorized
from apps.job_mgmt.views.mixins import TeamResolveMixin
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


def _int_env(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# 单文件大小上界（env 可配、保守默认；负责人可按部署调整，无需改码）。
# TTL 只兜住保存时长，不兜单次上传体量——防止持有 UserAPISecret 的调用方
# 用超大文件在过期前打满对象存储（issue #3154 的"大小"维度）。
MAX_UPLOAD_FILE_SIZE_MB = _int_env("JOB_MAX_UPLOAD_FILE_SIZE_MB", 1024)


class OpenFileUploadView(TeamResolveMixin, APIView):
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
        file: 必填，上传的文件（单文件大小上限默认 1024MB，
            可由环境变量 JOB_MAX_UPLOAD_FILE_SIZE_MB 调整）
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
        user_team, error = self.resolve_user_team(request)
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

        # 单文件大小上界（防超大单文件在过期前占满存储）
        if getattr(file, "size", 0) and file.size > MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024:
            return Response(
                {"detail": f"文件大小超过上限（{MAX_UPLOAD_FILE_SIZE_MB}MB）"},
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


class OpenFileDeleteView(TeamResolveMixin, APIView):
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
        {"result": true, "data": {"deleted": 1, "failed": [{"file_id": 2, "file_key": "...", "reason": "..."}]}}
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
        user_team, error = self.resolve_user_team(request)
        if error:
            return Response(
                {"detail": error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 校验格式并匹配删除
        deleted_count = 0
        not_found = []  # 不存在的文件
        failed = []  # S3 删除失败的文件
        for item in files:
            file_id = item.get("file_id")
            file_key = item.get("file_key")
            if not file_id or not file_key:
                continue

            # 将团队归属纳入查询条件，跨团队文件与不存在文件使用同一响应，
            # 避免调用方利用差异化结果枚举其他团队的文件。
            try:
                df = DistributionFile.objects.get(id=file_id, file_key=file_key, team=user_team)
            except DistributionFile.DoesNotExist:
                not_found.append({"file_id": file_id, "file_key": file_key})
                continue

            # 删除对象存储文件；若失败则跳过 DB 删除，避免产生孤儿 S3 对象
            try:
                async_to_sync(delete_s3_file)(df.file_key)
            except Exception as e:
                logger.warning(f"[open_delete_file] 删除对象存储文件失败: {df.file_key}, error={e}")
                failed.append({"file_id": df.id, "file_key": df.file_key, "reason": str(e)})
                continue  # S3 删除失败时不删除 DB 记录，防止产生孤儿文件

            df.delete()
            deleted_count += 1

        result = {"deleted": deleted_count}
        if not_found:
            result["not_found"] = not_found
        if failed:
            result["failed"] = failed

        return Response(
            result,
            status=status.HTTP_200_OK,
        )


def _resolve_open_team(view, request):
    user_team, error = view.resolve_user_team(request)
    if error:
        return None, Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
    return user_team, None


class OpenJobListView(TeamResolveMixin, APIView):
    """
    开放作业列表查询

    返回当前团队脚本库与 Playbook 的作业信息及参数定义，供执行前获取背景信息。
    不含脚本内容 / Playbook 文件。

    GET /api/v1/job_mgmt/api/open/job_list
    Header: Api-Authorization: <api_secret>
    Query: name, page, page_size（默认 20，最大 100）
    """

    def get(self, request):
        user_team, error_response = _resolve_open_team(self, request)
        if error_response:
            return error_response

        result = job_list(
            {
                "team": [user_team],
                "name": request.query_params.get("name") or "",
                "page": request.query_params.get("page") or 1,
                "page_size": request.query_params.get("page_size") or 20,
            }
        )
        if not result.get("result"):
            return Response({"detail": result.get("message") or "查询失败"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.get("data") or {}, status=status.HTTP_200_OK)


class OpenScriptExecuteView(TeamResolveMixin, APIView):
    """
    开放脚本执行接口

    请求体与 NATS ``job_script_execute`` 相同；团队取 API Secret 绑定值，忽略请求体 team。

    POST /api/v1/job_mgmt/api/open/script_execute
    Header: Api-Authorization: <api_secret>
    """

    def post(self, request):
        user_team, error_response = _resolve_open_team(self, request)
        if error_response:
            return error_response

        payload = dict(request.data)
        payload["team"] = [user_team]
        result = job_script_execute(payload)
        if not result.get("result"):
            message = result.get("message") or "脚本执行失败"
            http_status = (
                status.HTTP_503_SERVICE_UNAVAILABLE
                if "调度服务" in message
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"detail": message}, status=http_status)
        return Response(result.get("data") or {}, status=status.HTTP_201_CREATED)


class OpenJobStatusView(TeamResolveMixin, APIView):
    """
    开放作业状态批量查询

    请求体与 NATS ``job_status_batch_query`` 相同。跨团队任务按 not_found 返回。

    POST /api/v1/job_mgmt/api/open/job_status
    Header: Api-Authorization: <api_secret>
    Body: {"task_ids": [123, 456]}
    """

    def post(self, request):
        user_team, error_response = _resolve_open_team(self, request)
        if error_response:
            return error_response

        task_ids = request.data.get("task_ids") or []
        if not isinstance(task_ids, list) or not task_ids:
            return Response({"detail": "task_ids 不能为空"}, status=status.HTTP_400_BAD_REQUEST)
        if len(task_ids) > 100:
            return Response({"detail": "task_ids 最多 100 个"}, status=status.HTTP_400_BAD_REQUEST)

        result = job_status_batch_query({"task_ids": task_ids})
        if not result.get("result"):
            return Response({"detail": result.get("message") or "查询失败"}, status=status.HTTP_400_BAD_REQUEST)

        owned_ids = {
            execution.id
            for execution in JobExecution.objects.filter(id__in=task_ids)
            if is_team_authorized(execution.team, {user_team})
        }
        items = []
        for item in result.get("data") or []:
            task_id = item.get("task_id")
            if task_id not in owned_ids:
                items.append({"task_id": task_id, "status": "not_found"})
            else:
                items.append(item)
        return Response(items, status=status.HTTP_200_OK)


class OpenJobDetailView(TeamResolveMixin, APIView):
    """
    开放作业详情查询

    查询当前团队的执行任务详情。跨团队与不存在统一返回 404。

    GET /api/v1/job_mgmt/api/open/job_detail/<task_id>
    Header: Api-Authorization: <api_secret>
    """

    def get(self, request, task_id):
        user_team, error_response = _resolve_open_team(self, request)
        if error_response:
            return error_response

        result = job_detail_query({"task_id": task_id, "team": [user_team]})
        if not result.get("result"):
            return Response({"detail": "任务不存在"}, status=status.HTTP_404_NOT_FOUND)
        return Response(result.get("data") or {}, status=status.HTTP_200_OK)
