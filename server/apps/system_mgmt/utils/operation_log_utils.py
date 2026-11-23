"""
操作日志工具函数
"""
from ipware import get_client_ip

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models.app import App
from apps.system_mgmt.models.operation_log import OperationLog

OPERATION_LOG_WRITE_FAILED = "event=operation_log_write_failed failed_stage=persist error_type=%s"
SENSITIVE_VALUE_PLACEHOLDER = "已修改"
_SENSITIVE_KEY_MARKERS = ("password", "token", "secret", "otp", "access_key", "private_key")
_RECORDED_OUTCOMES = frozenset(
    {
        OperationLog.OUTCOME_SUCCESS,
        OperationLog.OUTCOME_FAILURE,
        OperationLog.OUTCOME_ACCEPTED,
    }
)


def _key_is_sensitive(key):
    lowered = str(key).lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def sanitize_operation_detail(value):
    """递归脱敏 detail。字段名不区分大小写，命中敏感片段时值改为「已修改」。"""
    if isinstance(value, dict):
        redacted = {}
        for key, child in value.items():
            if _key_is_sensitive(key):
                redacted[key] = SENSITIVE_VALUE_PLACEHOLDER
            else:
                redacted[key] = sanitize_operation_detail(child)
        return redacted
    if isinstance(value, list):
        return [sanitize_operation_detail(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_operation_detail(item) for item in value]
    return value


def normalize_outcome(outcome):
    if outcome in _RECORDED_OUTCOMES:
        return outcome
    return OperationLog.OUTCOME_UNRECORDED


def normalize_failure_reason(outcome, failure_reason):
    if outcome != OperationLog.OUTCOME_FAILURE:
        return ""
    return failure_reason or ""


def app_display_name_map(names=None):
    queryset = App.objects.all()
    if names is not None:
        queryset = queryset.filter(name__in=set(names))
    return dict(queryset.values_list("name", "display_name"))


def resolve_app_display_name(app, mapping=None):
    if mapping is None:
        mapping = app_display_name_map([app] if app else [])
    return mapping.get(app) or app or ""


def persist_operation_log(
    *,
    username,
    source_ip,
    app,
    action_type,
    summary="",
    domain="domain.com",
    target_type="",
    target_id="",
    target_name="",
    detail=None,
    outcome="",
    failure_reason="",
    idempotency_key=None,
):
    recorded_outcome = normalize_outcome(outcome)
    fields = {
        "username": username,
        "source_ip": source_ip,
        "app": app,
        "action_type": action_type,
        "summary": summary,
        "domain": domain,
        "target_type": target_type or "",
        "target_id": str(target_id or ""),
        "target_name": target_name or "",
        "detail": sanitize_operation_detail(detail or {}),
        "outcome": recorded_outcome,
        "failure_reason": normalize_failure_reason(recorded_outcome, failure_reason),
    }
    if idempotency_key is not None:
        fields["idempotency_key"] = idempotency_key
    return OperationLog.objects.create(**fields)


def log_operation(
    request,
    action_type,
    app,
    summary,
    *,
    target_type="",
    target_id="",
    target_name="",
    detail=None,
    outcome="",
    failure_reason="",
):
    """
    记录操作日志。新参数均可选；未传 outcome 时存空字符串，表示未记录。
    写入失败只记错误，不影响主业务。
    """
    try:
        client_ip, _ = get_client_ip(request)
        return persist_operation_log(
            username=request.user.username,
            source_ip=client_ip or "0.0.0.0",
            app=app,
            action_type=action_type,
            summary=summary,
            domain=getattr(request.user, "domain", "domain.com"),
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            detail=detail,
            outcome=outcome,
            failure_reason=failure_reason,
        )
    except Exception as exc:
        logger.error(OPERATION_LOG_WRITE_FAILED, type(exc).__name__, exc_info=True)
        return None
