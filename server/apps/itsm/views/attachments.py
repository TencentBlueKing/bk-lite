import json

from django.views.decorators.csrf import csrf_exempt

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.services.attachment import AttachmentError, presign_upload, upload_receipt
from apps.itsm.services.basic_settings import attachment_type_allowed
from apps.itsm.views.access import api_errors, domain_of, get_ticket, has_permission


@csrf_exempt
@api_errors
@HasPermission("ticket-View")
def presign_attachment(request):
    payload = json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
    ticket = get_ticket(request, payload["ticket_id"]) if payload.get("ticket_id") else None
    if ticket is None and not has_permission(request, "ticket-Add"):
        raise PermissionError()
    name = str(payload.get("filename") or "file")[:255]
    if not attachment_type_allowed(domain_of(request), name):
        return WebUtils.response_error("文件扩展名不在允许的附件类型中")
    try:
        signed = presign_upload(name)
    except AttachmentError as exc:
        return WebUtils.response_error(str(exc))
    if ticket:
        signed["receipt"] = upload_receipt(signed, ticket, request.user.username, name)
    return WebUtils.response_success(signed)
