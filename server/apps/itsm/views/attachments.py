import json

from django.views.decorators.csrf import csrf_exempt

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.services.attachment import AttachmentError, presign_upload


@csrf_exempt
@HasPermission("ticket-Add")
def presign_attachment(request):
    payload = json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
    try:
        signed = presign_upload(str(payload.get("filename") or "file"))
    except AttachmentError as exc:
        return WebUtils.response_error(str(exc))
    return WebUtils.response_success(signed)
