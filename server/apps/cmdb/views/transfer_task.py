import uuid
from pathlib import PurePath
from tempfile import TemporaryFile

from django.core.handlers.asgi import ASGIRequest
from django.db import transaction
from django.http import FileResponse, JsonResponse
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ViewSet

from apps.cmdb.services.transfer_authorization import TransferAuthorization
from apps.cmdb.services.transfer_execution import TransferExecution
from apps.cmdb.services.transfer_files import TransferFiles
from apps.cmdb.services.transfer_service import TransferError, TransferService
from apps.cmdb.services.transfer_validation import ExportRequest, inspect_workbook
from apps.cmdb.views.instance import _iter_export_file
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.team_utils import get_current_team
from apps.system_mgmt.models.user import User


def task_data(task):
    actions = []
    if task.status == "queued":
        actions.append("cancel")
    if task.status in TransferService.TERMINAL and not task.holds_slot:
        actions.append("delete")
    if task.kind == "export" and task.status == "failed":
        actions.append("retry")
    for name in ("result", "errors"):
        if name in task.artifacts and (task.status in ("succeeded", "partial_success") or (name == "errors" and task.status == "failed")):
            actions.append("download" if name == "result" else "download_errors")
    return dict(
        task_id=str(task.pk),
        type=task.kind,
        model_id=task.model_id,
        model_name=task.model_name,
        team_id=task.team_id,
        scope=task.params.get("scope"),
        filename=task.filename,
        status=task.status,
        phase=task.phase,
        processed_rows=task.processed_rows,
        total_rows=task.total_rows,
        summary=task.summary,
        message=task.message,
        error_code=task.error_code,
        available_actions=actions,
        created_at=task.created_at,
        finished_at=task.finished_at,
        expires_at=task.expires_at,
    )


def response(data=None, status=200):
    return JsonResponse({"result": True, "data": data, "message": ""}, status=status)


class TransferTaskViewSet(ViewSet):
    lookup_value_regex = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

    def handle_exception(self, exc):
        if isinstance(exc, TransferError):
            return JsonResponse({"result": False, "data": {}, "code": exc.code, "message": str(exc)}, status=exc.status_code)
        if isinstance(exc, ValidationError):
            return JsonResponse({"result": False, "data": {}, "code": "invalid_request", "message": "请求参数不合法"}, status=400)
        return super().handle_exception(exc)

    @staticmethod
    def owner(request):
        user = User.objects.filter(username=request.user.username, domain=request.user.domain, disabled=False).first()
        if not user:
            raise TransferError("owner_disabled", "用户不存在或已停用", 403)
        return user

    def list(self, request):
        owner = self.owner(request)
        return response(
            {
                "items": [task_data(task) for task in TransferService.list(owner)[:5]],
                "can_submit": not owner.cmdbtransfertask_set.filter(status__in=TransferService.ACTIVE).exists(),
                "limits": {"history": 5, "retention_days": 7, "import_bytes": 20 * 1024 * 1024, "import_rows": 10000, "export_rows": 100000},
            }
        )

    def retrieve(self, request, pk=None):
        return response(task_data(TransferService.get(self.owner(request), pk)))

    def destroy(self, request, pk=None):
        TransferService.request_delete(self.owner(request), pk)
        return response()

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        TransferService.cancel(self.owner(request), pk)
        return response()

    def submit(self, request, *, kind, params, source=None, original_scope=None, retry_of=None):
        owner = self.owner(request)
        model_id = params["model_id"]
        try:
            team = int(get_current_team(request))
        except (TypeError, ValueError):
            raise TransferError("invalid_team", "请先选择有效组织") from None
        children = request.COOKIES.get("include_children") == "1"
        if original_scope is not None:
            team, children = original_scope
        context = TransferAuthorization.resolve(owner, team, children, model_id, kind)
        attrs = {item["attr_id"] for item in context.attrs if not item.get("is_display_field") and item.get("attr_type") not in ("file", "image")}
        associations = {item["model_asst_id"] for item in context.associations}
        key, digest, filename = "", "", ""
        if source is not None:
            if not source.name.lower().endswith(".xlsx"):
                raise TransferError("invalid_workbook", "仅支持 .xlsx 文件")
            inspected = inspect_workbook(source, model_id, allowed_fields=attrs | associations)
            digest = inspected["sha256"]
            key = f"transfer/tmp/{uuid.uuid4().hex}/source.xlsx"
            try:
                TransferFiles().put(key, source)
            except TransferError:
                raise
            except Exception as exc:
                logger.warning(
                    "event=cmdb_transfer_upload_deferred owner_id=%s failed_stage=upload_source error_type=%s", owner.pk, type(exc).__name__
                )
                raise TransferError("storage_unavailable", "源文件存储失败，任务未创建，请稍后重试", 503) from None
            filename = PurePath(source.name).name[:255]
        elif not set(params["attr_list"]).issubset(attrs) or not set(params["association_list"]).issubset(associations):
            raise TransferError("invalid_fields", "导出字段或关联已变化，请刷新后重试")
        params = {name: value for name, value in params.items() if name != "model_id"}
        task = TransferService.submit(
            owner=owner,
            kind=kind,
            model_id=model_id,
            team_id=team,
            include_children=children,
            params=params,
            authorization=context.snapshot,
            schema_hash=context.schema_hash,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            source_key=key,
            source_hash=digest,
            filename=filename,
            model_name=context.model.get("model_name", model_id),
            retry_of=retry_of,
        )
        from apps.cmdb.tasks.transfer import dispatch_transfer

        transaction.on_commit(lambda: dispatch_transfer(str(task.pk)))
        return response(task_data(task), 202)

    @action(detail=False, methods=["post"], url_path="export")
    def export_file(self, request):
        serializer = ExportRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = dict(serializer.validated_data)
        params["inst_uuids"] = [str(value) for value in params["inst_uuids"]]
        return self.submit(request, kind="export", params=params)

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request):
        model_id = request.data.get("model_id")
        source = request.FILES.get("file")
        if not isinstance(model_id, str) or not model_id or len(model_id) > 128 or source is None:
            raise TransferError("invalid_request", "请选择模型并上传 Excel 文件")
        return self.submit(request, kind="import", params={"model_id": model_id}, source=source)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        owner = self.owner(request)
        replay = TransferService.replayed_retry(owner, pk, request.headers.get("Idempotency-Key", ""))
        if replay is not None:
            return response(task_data(replay), 202)
        task = TransferService.get(owner, pk)
        if task.kind != "export" or task.status != "failed":
            raise TransferError("state_conflict", "仅已失败的导出任务允许重新提交", 409)
        return self.submit(
            request,
            kind="export",
            params=dict(task.params, model_id=task.model_id),
            original_scope=(task.team_id, task.include_children),
            retry_of=task.pk,
        )

    @action(detail=True, methods=["post"])
    def download(self, request, pk=None):
        task = TransferService.get(self.owner(request), pk)
        artifact = request.data.get("artifact", "result")
        if artifact not in ("result", "errors") or artifact not in task.artifacts or task.status not in ("succeeded", "partial_success", "failed"):
            raise TransferError("artifact_not_found", "文件不存在或任务尚未完成", 404)
        files = TransferFiles()
        TransferExecution.validate_download(task, files)
        stream = TemporaryFile(mode="w+b")
        try:
            with files.read(task.artifacts[artifact]["key"]) as remote:
                while chunk := remote.read(64 * 1024):
                    stream.write(chunk)
                    if stream.tell() > files.MAX_BYTES:
                        raise TransferError("file_too_large", "结果文件超过大小限制", 413)
            stream.seek(0)
            # 下载授权后传输期间仍执行保留窗口检查。
            TransferService.get(self.owner(request), pk)
            result = FileResponse(stream, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            result["Content-Disposition"] = f'attachment; filename="cmdb-{task.pk}-{artifact}.xlsx"'
            result["Cache-Control"] = "private, no-store"
            if isinstance(getattr(request, "_request", request), ASGIRequest):
                result.streaming_content = _iter_export_file(stream)
            return result
        except BaseException:
            stream.close()
            raise
