"""连通性测试的结论映射。正式采集不读取这里。"""

from __future__ import annotations

import math
from typing import Mapping

from core.collection.contracts import AccessCheckRow
from core.collection.enums import AccessProbeStatus
from core.collection.runtime import CollectionRequest
from core.logger import logger, safe_log_value

_CLOUD_MODELS = frozenset({"aliyun", "aliyun_account", "qcloud", "hwcloud", "fusioninsight"})
_SHARED_PREFLIGHT = frozenset({"tcp", "remote", "https", "tls"})
_IDENTITY_KEYS = (
    "credential_id",
    "username",
    "user",
    "password",
    "accessKey",
    "accessSecret",
    "secret_id",
    "secret_key",
    "token",
    "community",
)


def credential_is_present(credential: Mapping[str, object] | None) -> bool:
    if not credential:
        return False
    return any(str(credential.get(key) or "").strip() for key in _IDENTITY_KEYS)


def credential_label(credential: Mapping[str, object], index: int) -> str:
    name = str(credential.get("credential_name") or credential.get("name") or "").strip()
    return name or f"凭据 {index}"


def credential_public_id(credential: Mapping[str, object], index: int) -> str:
    return str(credential.get("credential_id") or f"credential-{index}")


def shared_endpoint(request: CollectionRequest) -> bool:
    model_id = str(request.params.get("model_id") or "").strip()
    if model_id in _CLOUD_MODELS:
        return False
    kind = str(request.params.get("preflight_kind") or "").strip().lower()
    return kind in _SHARED_PREFLIGHT


def stops_remaining_credentials(request: CollectionRequest, status: AccessProbeStatus) -> bool:
    if status == AccessProbeStatus.RATE_LIMITED:
        return True
    return status == AccessProbeStatus.TARGET_UNREACHABLE and shared_endpoint(request)


def conclusion_for(status: AccessProbeStatus) -> tuple[str, bool]:
    if status == AccessProbeStatus.READY:
        return "credential_ok", True
    if status == AccessProbeStatus.AUTH_FAILED:
        return "credential_rejected", True
    if status == AccessProbeStatus.CAPABILITY_DENIED:
        return "permission_denied", True
    if status == AccessProbeStatus.NO_RESPONSE:
        return "no_response", True
    if status == AccessProbeStatus.TARGET_UNREACHABLE:
        return "network_unreachable", True
    if status == AccessProbeStatus.SERVICE_UNAVAILABLE:
        return "service_unavailable", True
    if status in {AccessProbeStatus.TLS_VALIDATION_FAILED, AccessProbeStatus.PROTOCOL_MISMATCH}:
        return "protocol_or_tls", True
    if status == AccessProbeStatus.RATE_LIMITED:
        return "rate_limited", True
    if status == AccessProbeStatus.NOT_SUPPORTED:
        return "unsupported", False
    return "probe_error", True


def preflight_rows(target: str, credentials, error_code: str) -> tuple[AccessCheckRow, ...]:
    present = [credential for credential in credentials if credential_is_present(credential)]
    if not present:
        return (
            AccessCheckRow(
                target=target,
                credential_id="",
                credential_name="",
                conclusion="no_credential",
                detail_code="",
                attempted=False,
            ),
        )
    rows = []
    for index, credential in enumerate(present, 1):
        rows.append(
            AccessCheckRow(
                target=target,
                credential_id=credential_public_id(credential, index),
                credential_name=credential_label(credential, index),
                conclusion="network_unreachable" if index == 1 else "not_tested",
                detail_code=error_code if index == 1 else "",
                attempted=False,
            )
        )
    return tuple(rows)


_SINGLE_CALLBACK_ROWS = 50
_BATCH_GROUPS = 8
_MIN_BATCH_ROWS = 20
_MAX_BATCH_ROWS = 50


def access_row_count(request: CollectionRequest) -> int:
    """按目标 × 对该目标生效的凭据计数。没有凭据时每个目标仍有一行。"""
    credentials = [credential for credential in request.credentials if credential_is_present(credential)]
    if not credentials:
        return len(request.targets)
    total = 0
    for target in request.targets:
        matched = 0
        for credential in credentials:
            bound = str(credential.get("target_host") or credential.get("host") or "").strip()
            if bound and bound != target:
                continue
            matched += 1
        total += matched or 1
    return total


def access_check_batch_size(row_count: int) -> int:
    """不足 50 行一次送回。更多时按总数切成大约 8 批，每批落在 20 到 50 行。"""
    total = max(int(row_count or 0), 1)
    if total < _SINGLE_CALLBACK_ROWS:
        return total
    sized = math.ceil(total / _BATCH_GROUPS)
    return min(_MAX_BATCH_ROWS, max(_MIN_BATCH_ROWS, sized))


async def emit_access_check_batches(target_rows, publish, *, total: int, batch_size: int | None = None):
    """按行数凑批。不足一批的留到结束时用 finished 送回。"""
    size = access_check_batch_size(total) if batch_size is None else max(int(batch_size), 1)
    buffer = []
    since_flush = 0
    try:
        async for rows in target_rows:
            buffer.extend(rows)
            since_flush += len(rows)
            if size < total and since_flush >= size:
                since_flush = 0
                if await publish("running", tuple(buffer)):
                    buffer.clear()
        await publish("finished", tuple(buffer))
    finally:
        close = getattr(target_rows, "aclose", None)
        if callable(close):
            await close()


def log_access_conclusion(target: str, credential_id: str, conclusion: str, detail_code: str) -> None:
    """记录已经归类的网络或凭据结论。只写稳定码，不写口令或异常正文。"""
    if conclusion not in {"network_unreachable", "credential_rejected"}:
        return
    logger.info(
        "event=access_check_classified target=%s credential_id=%s conclusion=%s detail_code=%s",
        safe_log_value(target, max_length=255),
        safe_log_value(credential_id),
        conclusion,
        safe_log_value(detail_code),
    )


def skipped_row(target: str, credential: Mapping[str, object], index: int) -> AccessCheckRow:
    return AccessCheckRow(
        target=target,
        credential_id=credential_public_id(credential, index),
        credential_name=credential_label(credential, index),
        conclusion="not_tested",
        detail_code="",
        attempted=False,
    )
