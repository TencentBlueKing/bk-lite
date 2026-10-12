"""Notify consumers after a credential secret version advances."""

from __future__ import annotations

from django.db import transaction

from apps.core.logger import system_mgmt_logger as logger
from apps.rpc.base import RpcClient

CREDENTIAL_REFRESH_NATS_METHODS = {"monitor": "monitor_refresh_credential_refs"}
NOTIFY_TIMEOUT_SECONDS = 5
NOTIFY_FAILED_TEMPLATE = "event=credential_refresh_notify_failed module=%s failed_stage=rpc error_type=%s id_count=%s"


def schedule_credential_refresh(credential_id):
    """Register an on-commit notify. A failed notify does not roll back the save."""

    def notify():
        for module, method in CREDENTIAL_REFRESH_NATS_METHODS.items():
            try:
                RpcClient().run(method, credential_ids=[credential_id], _timeout=NOTIFY_TIMEOUT_SECONDS)
            except Exception as exc:
                logger.warning(
                    NOTIFY_FAILED_TEMPLATE,
                    module,
                    type(exc).__name__,
                    1,
                )

    transaction.on_commit(notify, robust=True)
