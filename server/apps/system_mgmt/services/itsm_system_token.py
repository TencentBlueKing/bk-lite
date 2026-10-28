"""用外部传入的明文初始化 ITSM 系统密钥。"""

import re

from django.db import IntegrityError, transaction

from apps.core.logger import system_mgmt_logger as logger
from apps.core.openapi.token_scope import SCOPE_ALL
from apps.system_mgmt.models import SystemAPIToken

ITSM_SYSTEM_ID = "itsm"
ITSM_TOKEN_NAME = "itsm"
_KEY_RE = re.compile(r"^bksys_[0-9a-f]{64}$")

_CREATED_LOG = "event=itsm_system_token_created system_id=%s token_id=%s"
_EXISTS_LOG = "event=itsm_system_token_exists system_id=%s token_id=%s"
_REPLACED_LOG = "event=itsm_system_token_replaced system_id=%s token_id=%s"
_REJECTED_LOG = "event=itsm_system_token_rejected failed_stage=%s error_type=%s"
_REJECTED_ROW_LOG = "event=itsm_system_token_rejected failed_stage=%s error_type=%s system_id=%s token_id=%s"


class ItsmSystemTokenError(Exception):
    """预期失败。消息不含密钥材料。"""


def get_or_create_itsm_token(key: str) -> str:
    if not isinstance(key, str) or _KEY_RE.fullmatch(key) is None:
        logger.warning(_REJECTED_LOG, "validate_key", "ItsmSystemTokenError")
        raise ItsmSystemTokenError("ITSM 系统密钥格式不正确")

    secret_hash = SystemAPIToken.hash_secret(key)
    with transaction.atomic():
        other = (
            SystemAPIToken.objects.select_for_update().filter(secret_hash=secret_hash).exclude(system_id=ITSM_SYSTEM_ID, name=ITSM_TOKEN_NAME).first()
        )
        if other is not None:
            logger.warning(_REJECTED_ROW_LOG, "lookup", "ItsmSystemTokenError", other.system_id, other.pk)
            raise ItsmSystemTokenError("该密钥已绑定其他系统")

        row = SystemAPIToken.objects.select_for_update().filter(system_id=ITSM_SYSTEM_ID, name=ITSM_TOKEN_NAME).first()
        if row is None:
            try:
                with transaction.atomic():
                    row = SystemAPIToken.objects.create(
                        system_id=ITSM_SYSTEM_ID,
                        name=ITSM_TOKEN_NAME,
                        secret_hash=secret_hash,
                        scope=dict(SCOPE_ALL),
                        enabled=True,
                        expires_at=None,
                        created_by="system",
                        created_by_domain="domain.com",
                    )
            except IntegrityError:
                row = SystemAPIToken.objects.select_for_update().filter(system_id=ITSM_SYSTEM_ID, name=ITSM_TOKEN_NAME).first()
                if row is None:
                    logger.warning(_REJECTED_LOG, "create", "IntegrityError")
                    raise ItsmSystemTokenError("ITSM 系统密钥已存在") from None
                return _apply_existing(row, secret_hash)
            logger.info(_CREATED_LOG, row.system_id, row.pk)
            return "created"
        return _apply_existing(row, secret_hash)


def _apply_existing(row, secret_hash: str) -> str:
    if row.secret_hash == secret_hash:
        logger.info(_EXISTS_LOG, row.system_id, row.pk)
        return "exists"
    row.secret_hash = secret_hash
    row.save(update_fields=["secret_hash", "updated_at"])
    logger.info(_REPLACED_LOG, row.system_id, row.pk)
    return "replaced"
