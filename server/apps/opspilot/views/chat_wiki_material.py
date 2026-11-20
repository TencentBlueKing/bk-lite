"""对话里查看和确认一次知识库写入的结果。会话用户调用，不走对外网关。"""

from django.http import JsonResponse

from apps.opspilot.models import Material
from apps.opspilot.services.wiki.chat_material_service import REPLY_KB_DENIED, decide_chat_wiki_write, read_chat_wiki_outcome
from apps.opspilot.views.chat_flow import parse_json_body


def _user_can_operate_knowledge_base(user, knowledge_base) -> bool:
    # viewsets 包的初始化会在 views 包尚未加载完时回到这里，顶层导入形成环。
    from apps.opspilot.viewsets.wiki_team_scope import user_can_operate_knowledge_base

    return user_can_operate_knowledge_base(user, knowledge_base)


def _source_ip(request) -> str:
    raw = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or ""
    ip = str(raw).split(",")[0].strip()
    if ip.count(".") == 3 or ":" in ip:
        return ip
    return "0.0.0.0"


def _load_chat_material(request, material_id):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None, JsonResponse({"result": False, "message": "未登录"}, status=401)
    material = Material.objects.select_related("knowledge_base").filter(pk=material_id, chat_sourced=True).first()
    if material is None:
        return None, JsonResponse({"result": False, "message": "没有这条写入结果"}, status=404)
    if not _user_can_operate_knowledge_base(user, material.knowledge_base):
        return None, JsonResponse({"result": False, "message": REPLY_KB_DENIED}, status=403)
    return material, None


def chat_wiki_material_outcome(request, material_id):
    if request.method != "GET":
        return JsonResponse({"result": False, "message": "method not allowed"}, status=405)
    material, error = _load_chat_material(request, material_id)
    if error:
        return error
    return JsonResponse({"result": True, "data": read_chat_wiki_outcome(material)})


def chat_wiki_material_decide(request, material_id):
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "method not allowed"}, status=405)
    material, error = _load_chat_material(request, material_id)
    if error:
        return error
    payload, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)
    try:
        check_id = int(payload.get("check_id"))
    except (TypeError, ValueError):
        return JsonResponse({"result": False, "message": "无法确认这条知识"}, status=400)
    action = payload.get("action")
    if not isinstance(action, str) or not action.strip():
        return JsonResponse({"result": False, "message": "无法确认这条知识"}, status=400)
    body = payload.get("body", "")
    if body is None:
        body = ""
    if not isinstance(body, str):
        return JsonResponse({"result": False, "message": "无法确认这条知识"}, status=400)
    user = request.user
    try:
        updated = decide_chat_wiki_write(
            material_id=material.pk,
            check_id=check_id,
            action=action,
            body=body,
            operator=getattr(user, "username", "") or "",
            domain=getattr(user, "domain", "") or "domain.com",
            source_ip=_source_ip(request),
        )
    except ValueError:
        return JsonResponse({"result": False, "message": "无法确认这条知识"}, status=400)
    return JsonResponse({"result": True, "data": updated})
