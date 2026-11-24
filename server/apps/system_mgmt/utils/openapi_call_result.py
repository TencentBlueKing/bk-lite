from django.db.models import Q

from apps.core.openapi.envelope import ErrorCode

AUTH_DENIED_ERROR_CODES = frozenset(
    {
        ErrorCode.AUTH_INVALID,
        ErrorCode.PERM_MISSING,
        ErrorCode.SCOPE_DENIED,
        ErrorCode.ROLE_REQUIRED,
        ErrorCode.TEAM_OUT_OF_SCOPE,
    }
)

CALL_RESULT_SUCCESS = "success"
CALL_RESULT_AUTH_PASSED = "auth_passed"
CALL_RESULT_AUTH_DENIED = "auth_denied"
CALL_RESULT_FAILURE = "failure"

API_KIND_INTERNAL = "internal"
API_KIND_EXTERNAL = "external"

CALL_RESULT_EXPORT_LABELS = {
    CALL_RESULT_SUCCESS: "成功",
    CALL_RESULT_AUTH_PASSED: "鉴权通过",
    CALL_RESULT_AUTH_DENIED: "鉴权拒绝",
    CALL_RESULT_FAILURE: "失败",
}


def _error_code_is_empty(error_code) -> bool:
    return error_code is None or str(error_code).strip() == ""


def _http_status_int(http_status):
    try:
        return int(http_status)
    except (TypeError, ValueError):
        return None


def _is_http_2xx(http_status) -> bool:
    status = _http_status_int(http_status)
    return status is not None and 200 <= status < 300


def derive_openapi_call_result(api_kind, http_status, error_code) -> str:
    kind = "" if api_kind is None else str(api_kind).strip()
    if not kind:
        return CALL_RESULT_FAILURE
    if kind == API_KIND_EXTERNAL:
        if _is_http_2xx(http_status) and _error_code_is_empty(error_code):
            return CALL_RESULT_AUTH_PASSED
        if str(error_code or "") in AUTH_DENIED_ERROR_CODES:
            return CALL_RESULT_AUTH_DENIED
        return CALL_RESULT_FAILURE
    if kind == API_KIND_INTERNAL:
        status = _http_status_int(http_status)
        if status is not None and status < 400:
            return CALL_RESULT_SUCCESS
        return CALL_RESULT_FAILURE
    return CALL_RESULT_FAILURE


def _empty_error_code_q() -> Q:
    return Q(error_code="") | Q(error_code__isnull=True)


def _http_2xx_q() -> Q:
    return Q(http_status__gte=200, http_status__lt=300)


def openapi_call_result_outcome_q(outcome: str):
    """SQL filter for the success/failure outcome buckets.

    success: call_result in {success, auth_passed}
    failure: call_result in {auth_denied, failure}
    """
    internal_success = Q(api_kind=API_KIND_INTERNAL, http_status__lt=400)
    auth_passed = Q(api_kind=API_KIND_EXTERNAL) & _http_2xx_q() & _empty_error_code_q()
    success_bucket = internal_success | auth_passed
    if outcome == "success":
        return success_bucket
    if outcome == "failure":
        empty_kind = Q(api_kind="") | Q(api_kind__isnull=True) | ~Q(api_kind__in=[API_KIND_INTERNAL, API_KIND_EXTERNAL])
        internal_failure = Q(api_kind=API_KIND_INTERNAL, http_status__gte=400)
        auth_denied = Q(api_kind=API_KIND_EXTERNAL, error_code__in=AUTH_DENIED_ERROR_CODES)
        external_other_failure = Q(api_kind=API_KIND_EXTERNAL) & ~(auth_passed) & ~Q(error_code__in=AUTH_DENIED_ERROR_CODES)
        return empty_kind | internal_failure | auth_denied | external_other_failure
    return None


def format_openapi_call_result_label(api_kind, http_status, error_code) -> str:
    return CALL_RESULT_EXPORT_LABELS[derive_openapi_call_result(api_kind, http_status, error_code)]
