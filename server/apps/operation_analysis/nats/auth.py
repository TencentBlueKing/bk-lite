"""运营分析内部 NATS 请求的短时签名。"""

import os

from django.core import signing
from rest_framework.exceptions import PermissionDenied

AUTH_SALT = "apps.operation_analysis.nats.get_operation_analysis_module_data.v1"
DEFAULT_AUTH_MAX_AGE_SECONDS = 120


def _request_params(module, child_module, page, page_size, group_id):
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
    except (signing.BadSignature, TypeError, ValueError):
        raise PermissionDenied("Operation analysis NATS authentication failed") from None

    if signed_params != _request_params(module, child_module, page, page_size, group_id):
        raise PermissionDenied("Operation analysis NATS authentication failed")


def allow_legacy_unsigned_requests():
    """显式回滚开关；默认关闭，避免无意恢复越权路径。"""

    return os.getenv("OPERATION_ANALYSIS_NATS_ALLOW_UNSIGNED", "false").lower() in {"1", "true", "yes"}
