"""OpenAPI 统一网关响应契约：envelope 与机器可读错误码。

契约来源：specs/changes/openapi-unified-gateway/design.md 3.8 与第 8 章冻结清单。
错误码为对外冻结契约：只允许新增（additive），不得改名、复用或删除。
TIMEOUT 与 BUSINESS_REJECTED 为实现期增补项，见同目录实现备忘。
"""

from django.http import JsonResponse


class ErrorCode:
    AUTH_INVALID = "AUTH_INVALID"
    PERM_MISSING = "PERM_MISSING"
    ROLE_REQUIRED = "ROLE_REQUIRED"
    TEAM_OUT_OF_SCOPE = "TEAM_OUT_OF_SCOPE"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_UNREACHABLE = "UPSTREAM_UNREACHABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT = "TIMEOUT"
    BUSINESS_REJECTED = "BUSINESS_REJECTED"


ERROR_HTTP_STATUS = {
    ErrorCode.AUTH_INVALID: 401,
    ErrorCode.PERM_MISSING: 403,
    ErrorCode.ROLE_REQUIRED: 403,
    ErrorCode.TEAM_OUT_OF_SCOPE: 403,
    ErrorCode.SCHEMA_INVALID: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.UPSTREAM_UNREACHABLE: 502,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.TIMEOUT: 504,
    ErrorCode.BUSINESS_REJECTED: 400,
}


def ok(data) -> JsonResponse:
    return JsonResponse({"result": True, "data": data})


def fail(code: str, message: str, status: int = None) -> JsonResponse:
    return JsonResponse(
        {"result": False, "code": code, "message": message},
        status=status or ERROR_HTTP_STATUS.get(code, 500),
    )
