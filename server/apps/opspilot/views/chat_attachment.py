"""对话附件上传、状态与下载。登录态与 Api-Authorization 都可调用。"""

from django.http import FileResponse, JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.exempt import api_exempt
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.models import ChatAttachment
from apps.opspilot.services.chat_attachment_service import (
    ChatAttachmentError,
    attachment_content_disposition,
    read_bounded_upload,
    serialize_attachment,
    store_upload,
)
from apps.opspilot.services.skill_channel_chat_service import SkillChannelChatError, authenticate_embedded, saas_external_user_id


def resolve_chat_actor(request) -> tuple[str, str]:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return saas_external_user_id(user), str(get_current_team(request, "0"))
    try:
        user_secret, team_id = authenticate_embedded(request)
    except SkillChannelChatError as exc:
        raise ChatAttachmentError(exc.message, status=exc.status, code="unauthenticated") from exc
    return f"{user_secret.username}@{user_secret.domain}", str(team_id)


def _owned_attachment(request, attachment_id: int) -> ChatAttachment:
    try:
        owner_key, team_id = resolve_chat_actor(request)
    except ChatAttachmentError as exc:
        raise exc
    attachment = ChatAttachment.objects.filter(id=attachment_id, owner_key=owner_key, team_id=team_id).first()
    if attachment is None:
        raise ChatAttachmentError("无权访问该附件", status=403, code="attachment_forbidden")
    if attachment.conversation_id and (attachment.conversation.external_user_id or "") != owner_key:
        raise ChatAttachmentError("无权访问该附件", status=403, code="attachment_forbidden")
    return attachment


def _error_response(exc: ChatAttachmentError):
    return JsonResponse({"result": False, "message": exc.message, "code": exc.code}, status=exc.status)


@api_exempt
def upload_chat_attachment(request):
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "方法不允许"}, status=405)
    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"result": False, "message": "file 必填", "code": "file_required"}, status=400)
    try:
        data = read_bounded_upload(upload, content_length=request.META.get("CONTENT_LENGTH"))
        owner_key, team_id = resolve_chat_actor(request)
        attachment = store_upload(filename=upload.name, data=data, owner_key=owner_key, team_id=team_id)
    except ChatAttachmentError as exc:
        return _error_response(exc)
    except SkillChannelChatError as exc:
        return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
    return JsonResponse({"result": True, "data": serialize_attachment(attachment)})


@api_exempt
def chat_attachment_status(request, attachment_id: int):
    if request.method != "GET":
        return JsonResponse({"result": False, "message": "方法不允许"}, status=405)
    try:
        attachment = _owned_attachment(request, attachment_id)
    except ChatAttachmentError as exc:
        return _error_response(exc)
    payload = serialize_attachment(attachment)
    if attachment.status == ChatAttachment.STATUS_FAILED:
        payload["failure_reason"] = attachment.failure_reason
    return JsonResponse({"result": True, "data": payload})


@api_exempt
def download_chat_attachment(request, attachment_id: int):
    if request.method != "GET":
        return JsonResponse({"result": False, "message": "方法不允许"}, status=405)
    try:
        attachment = _owned_attachment(request, attachment_id)
    except ChatAttachmentError as exc:
        return _error_response(exc)
    if not attachment.file:
        logger.warning(
            "chat_attachment download missing file: attachment_id=%s failed_stage=%s error_type=%s",
            attachment.id,
            "download",
            "MissingFile",
        )
        return JsonResponse({"result": False, "message": "附件文件不存在", "code": "missing_file"}, status=404)
    inline = (attachment.mime_type or "").startswith("image/")
    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=not inline,
        content_type=attachment.mime_type or "application/octet-stream",
    )
    disposition = attachment_content_disposition(attachment.original_name, as_attachment=not inline)
    if disposition:
        response["Content-Disposition"] = disposition
    return response
