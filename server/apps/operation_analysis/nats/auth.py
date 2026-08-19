"""运营分析内部 NATS 请求的短时签名。"""

import os

from django.core import signing
from rest_framework.exceptions import PermissionDenied

AUTH_SALT = "apps.operation_analysis.nats.get_operation_analysis_module_data.v1"
DEFAULT_AUTH_MAX_AGE_SECONDS = 120
MAX_PAGE_SIZE = 500


def _positive_integer(value, name, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name} must be a positive integer")
    if isinstance(value, str) and not value.isdecimal():
        raise ValueError(f"{name} must be a positive integer")
    try:
        value = int(value)
        if value <= 0 or (maximum is not None and value > maximum):
            raise ValueError
    except (TypeError, ValueError):
        message = f"{name} must be a positive integer"
        if maximum is not None:
            message += f" no greater than {maximum}"
        raise ValueError(message) from None
    return value


def _request_params(module, child_module, page, page_size, group_id):
    page = _positive_integer(page, "page")
    page_size = _positive_integer(page_size, "page_size", MAX_PAGE_SIZE)
    group_id = _positive_integer(group_id, "group_id")

    return {
        "module": module,
        "child_module": child_module,
        "page": page,
        "page_size": page_size,
        "group_id": group_id,
    }


def sign_module_data_request(module, child_module, page, page_size, group_id):
    """签发绑定完整查询参数、可由 Django 密钥轮换校验的短时令牌。"""

    return signing.dumps(
        _request_params(module, child_module, page, page_size, group_id),
        salt=AUTH_SALT,
    )


def verify_module_data_request(token, module, child_module, page, page_size, group_id):
    """校验令牌有效期及其绑定的完整查询参数。"""

    try:
        max_age = int(os.getenv("OPERATION_ANALYSIS_NATS_AUTH_MAX_AGE", DEFAULT_AUTH_MAX_AGE_SECONDS))
        signed_params = signing.loads(token, salt=AUTH_SALT, max_age=max_age)
        expected_params = _request_params(module, child_module, page, page_size, group_id)
    except (signing.BadSignature, TypeError, ValueError):
        raise PermissionDenied("Operation analysis NATS authentication failed") from None

    if signed_params != expected_params:
        raise PermissionDenied("Operation analysis NATS authentication failed")
    return expected_params
