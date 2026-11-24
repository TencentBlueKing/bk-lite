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
    if ticket and ("field" in payload or "task_id" in payload):
        from apps.itsm.services.form.validator import FormValidator
        from apps.itsm.services.ticket.service import _find_node, _normalize_perm, workflow_schema
        from apps.itsm.views.tickets import editable_task

        task = editable_task(request, ticket, payload.get("task_id"))
        permissions = _find_node(ticket.workflow_version.design, node_id=task.node_id).get("field_perm")
        validator = FormValidator(workflow_schema(ticket.workflow_version), _normalize_perm(permissions))
        key = payload.get("field")
        if not any(field.key == key and field.type == "attachment" and mode not in {"hidden", "readonly"} for field, mode in validator._fields()):
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
