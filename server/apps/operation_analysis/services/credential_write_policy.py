import os

from django.core.exceptions import ImproperlyConfigured

from apps.core.logger import operation_analysis_logger as logger

ALLOW_INSECURE_CREDENTIAL_WRITES_ENV = "OPERATION_ANALYSIS_ALLOW_INSECURE_CREDENTIAL_WRITES"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def validate_credential_write_key(key: str) -> None:
    """拒绝用空白密钥生成新的运营分析凭据密文。"""
    if isinstance(key, str) and key.strip():
        return

    if os.getenv(ALLOW_INSECURE_CREDENTIAL_WRITES_ENV, "").strip().lower() in _TRUE_VALUES:
        logger.warning("[CredentialWrite] 临时兼容开关已启用，允许以空白 SECRET_KEY 写入运营分析凭据")
        return

    message = "SECRET_KEY 未配置，禁止写入运营分析凭据；请配置非空密钥，"
    message += f"或仅在紧急回滚时启用 {ALLOW_INSECURE_CREDENTIAL_WRITES_ENV}"
    raise ImproperlyConfigured(message)
