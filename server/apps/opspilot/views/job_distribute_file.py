"""分发文件暂存。确认分发前不写入作业平台。"""

from django.http import JsonResponse

from apps.core.utils.exempt import api_exempt
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.services.chat_attachment_service import ChatAttachmentError
from apps.opspilot.services.job_tool_service import (
    JobToolError,
    _max_upload_bytes,
    distribute_owner_key,
    list_staged_distribute_files,
    stage_distribute_file,
)
from apps.opspilot.services.skill_channel_chat_service import SkillChannelChatError
from apps.opspilot.views.chat_attachment import resolve_chat_actor


def _read_upload(upload) -> bytes:
    limit = _max_upload_bytes()
    declared = getattr(upload, "size", None)
    try:
        declared = int(declared) if declared is not None else None
    except (TypeError, ValueError):
        declared = None
    if declared is not None and declared > limit:
        raise JobToolError("文件超过作业平台上传上限")
    parts = []
    total = 0
    chunks = getattr(upload, "chunks", None)
    stream = chunks() if callable(chunks) else iter([upload.read(limit + 1)])
    for chunk in stream:
        if not chunk:
            continue
        if len(chunk) > limit or total > limit - len(chunk):
            raise JobToolError("文件超过作业平台上传上限")
        parts.append(chunk)
        total += len(chunk)
    if not parts:
        raise JobToolError("文件内容为空")
    return b"".join(parts)


def _distribute_actor(request):
    owner_key, team_id = resolve_chat_actor(request)
    if team_id in ("", "0", None):
        team_id = str(get_current_team(request, "0"))
    user = getattr(request, "user", None)
    username = getattr(user, "username", "") if user is not None else ""
    domain = getattr(user, "domain", "") if user is not None else ""
    if isinstance(username, str) and username.strip() and isinstance(domain, str) and domain.strip():
        owner_key = distribute_owner_key(username.strip(), domain.strip())
    return owner_key, str(team_id)


@api_exempt
def list_job_distribute_files(request):
    if request.method != "GET":
        return JsonResponse({"result": False, "message": "方法不允许"}, status=405)
    session_key = str(request.GET.get("session_id") or "").strip()
    if not session_key:
        return JsonResponse({"result": False, "message": "当前会话缺失，不能查看暂存文件"}, status=400)
    try:
        owner_key, team_id = _distribute_actor(request)
    except ChatAttachmentError as exc:
        return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
    except SkillChannelChatError as exc:
        return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
    files = list_staged_distribute_files(owner_key=owner_key, team_id=team_id, session_key=session_key)
    return JsonResponse({"result": True, "data": files})


@api_exempt
def upload_job_distribute_file(request):
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "方法不允许"}, status=405)
    upload = request.FILES.get("file")
    session_key = str(request.POST.get("session_id") or "").strip()
    if upload is None:
        return JsonResponse({"result": False, "message": "file 必填"}, status=400)
    try:
        owner_key, team_id = _distribute_actor(request)
        data = _read_upload(upload)
        staged = stage_distribute_file(
            owner_key=owner_key,
            team_id=team_id,
            session_key=session_key,
            filename=upload.name,
            data=data,
        )
    except JobToolError as exc:
        return JsonResponse({"result": False, "message": exc.message}, status=400)
    except ChatAttachmentError as exc:
        return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
    except SkillChannelChatError as exc:
        return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
    return JsonResponse(
        {
            "result": True,
            "data": {"id": staged.id, "name": staged.original_name, "size": staged.size},
        }
    )
