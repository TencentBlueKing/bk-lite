import os
from datetime import datetime, timedelta, timezone

from django.core.exceptions import ImproperlyConfigured

from apps.core.logger import operation_analysis_logger as logger

ALLOW_INSECURE_CREDENTIAL_WRITES_ENV = "OPERATION_ANALYSIS_ALLOW_INSECURE_CREDENTIAL_WRITES"
INSECURE_CREDENTIAL_WRITES_UNTIL_ENV = "OPERATION_ANALYSIS_INSECURE_CREDENTIAL_WRITES_UNTIL"
_MAX_INSECURE_WRITE_WINDOW = timedelta(hours=1)
_TRUE_VALUES = {"1", "true", "yes", "on"}


def validate_credential_write_key(key: str) -> None:
    """拒绝用空白密钥生成新的运营分析凭据密文。"""
    if isinstance(key, str) and key.strip():
        return

    if os.getenv(ALLOW_INSECURE_CREDENTIAL_WRITES_ENV, "").strip().lower() in _TRUE_VALUES:
        deadline_value = os.getenv(INSECURE_CREDENTIAL_WRITES_UNTIL_ENV, "").strip()
        try:
            deadline = datetime.fromisoformat(deadline_value.replace("Z", "+00:00"))
        except ValueError:
            deadline = None
        now = datetime.now(timezone.utc)
        if deadline and deadline.tzinfo and now < deadline <= now + _MAX_INSECURE_WRITE_WINDOW:
            logger.warning("[CredentialWrite] 临时兼容开关已启用，允许以空白 SECRET_KEY 写入运营分析凭据；到期时间=%s", deadline.isoformat())
            return

    message = "SECRET_KEY 未配置，禁止写入运营分析凭据；请配置非空密钥，"
    message += f"或仅在紧急回滚时同时配置 {ALLOW_INSECURE_CREDENTIAL_WRITES_ENV} 与 {INSECURE_CREDENTIAL_WRITES_UNTIL_ENV}"
    raise ImproperlyConfigured(message)
