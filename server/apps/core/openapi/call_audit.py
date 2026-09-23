"""网关调用日志落库：与 INFO openapi_access 并存，失败不影响网关响应。"""

import json
import re

from ipware import get_client_ip

from apps.core.logger import openapi_logger as logger, safe_exception_info, safe_log_value
from apps.core.openapi.envelope import ErrorCode

ENTRY_INVOKE = "invoke"
ENTRY_FORWARD_AUTH = "forward_auth"

PATH_RE = re.compile(
    r"^/openapi/(?P<version>[a-z0-9]+)/(?P<service>[a-z][a-z0-9-]*)(?:/(?P<sub_path>.*?))?/?$"
)


def persist_call_log(request, identity, response, *, entry):
    try:
        _create_call_log(request, identity, response, entry=entry)
    except Exception as exc:
        token_id = getattr(identity, "token_id", None)
        logger.error(
            "event=openapi_call_log_persist_failed failed_stage=persist error_type=%s token_id=%s path=%s",
            type(exc).__name__,
            token_id if token_id is not None else "-",
            safe_log_value(getattr(request, "path", ""), max_length=128),
            exc_info=safe_exception_info(exc),
        )


def _create_call_log(request, identity, response, *, entry):
    from apps.system_mgmt.models import OpenAPICallLog

    method, path, service, sub_path = _request_target(request, entry=entry)
    http_status, error_code = _gateway_outcome(response)
    source_ip, _routable = get_client_ip(request)
    username, credential_type, token_id, token_name, system_id, team_id = _audit_identity(identity)
    OpenAPICallLog.objects.create(
        source_ip=source_ip or "0.0.0.0",
        username=username,
        credential_type=credential_type,
        token_id=token_id,
        token_name=token_name,
        system_id=system_id,
        team_id=team_id,
        api_kind=classify_api_kind(service, sub_path, method),
        method=method,
        path=path,
        http_status=http_status,
        error_code=error_code,
    )


def classify_api_kind(service, sub_path, method):
    """目录命中才填写接口类型：内部端点优先，否则外部服务，都对不上则为空。"""
    from apps.core.openapi.registry import default_registry
    from apps.core.openapi.renderer import get_external_entry
    from apps.system_mgmt.models import OpenAPICallLog

    if service and default_registry.find(service, sub_path, method):
        return OpenAPICallLog.API_KIND_INTERNAL
    if service and get_external_entry(service):
        return OpenAPICallLog.API_KIND_EXTERNAL
    return ""


def _identity_text(identity, attr):
    if identity is None:
        return ""
    value = getattr(identity, attr, None)
    return "" if value is None else str(value)


def _team_id(identity):
    if identity is None or not getattr(identity, "user", None):
        return None
    team_ids = [tid for tid in (getattr(identity, "team_ids", None) or []) if tid is not None]
    if len(team_ids) != 1:
        return None
    return int(team_ids[0])


def _audit_identity(identity):
    """只留下个人密钥和系统密钥。JWT 及其他未识别凭据整行身份留空。"""
    from apps.system_mgmt.models import OpenAPICallLog

    empty = ("", "", None, "", "", None)
    if identity is None:
        return empty
    credential_type = _identity_text(identity, "credential_type")
    if credential_type not in (
        OpenAPICallLog.CREDENTIAL_API_TOKEN,
        OpenAPICallLog.CREDENTIAL_SYSTEM_TOKEN,
    ):
        return empty
    token_id = getattr(identity, "token_id", None)
    system_id = ""
    if credential_type == OpenAPICallLog.CREDENTIAL_SYSTEM_TOKEN:
        system_id = _identity_text(identity, "caller_system")
    return (
        _identity_text(identity, "user"),
        credential_type,
        token_id,
        _identity_text(identity, "token_name"),
        system_id,
        _team_id(identity),
    )


def _request_target(request, *, entry):
    if entry == ENTRY_FORWARD_AUTH:
        raw_uri = request.META.get("HTTP_X_FORWARDED_URI") or ""
        path = raw_uri.split("?", 1)[0][:512]
        method = request.META.get("HTTP_X_FORWARDED_METHOD") or ""
    else:
        method = request.method or ""
        path = (request.path or "")[:512]
    service, sub_path = _split_openapi_path(path)
    return method, path, service, sub_path


def _split_openapi_path(path):
    matched = PATH_RE.match(path or "")
    if not matched:
        return "", ""
    sub_path = (matched.group("sub_path") or "").strip("/")
    return matched.group("service"), sub_path


def _gateway_outcome(response):
    if response is None:
        return 500, ErrorCode.INTERNAL_ERROR
    status = int(getattr(response, "status_code", 500) or 500)
    error_code = ""
    try:
        payload = json.loads(getattr(response, "content", b"") or b"")
    except (ValueError, TypeError, UnicodeDecodeError):
        payload = None
    if isinstance(payload, dict) and payload.get("result") is False:
        error_code = payload.get("code") or ""
    return status, error_code
