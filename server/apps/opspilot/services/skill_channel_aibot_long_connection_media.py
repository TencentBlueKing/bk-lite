"""把技能生成的文件经企微长连接分片上传，再按 media_id 回复文件消息。"""

from __future__ import annotations

import base64
import hashlib
import re
import time
import uuid
from typing import Any, Callable

from apps.core.logger import opspilot_logger as logger

_ATTACHMENT_URL_RE = re.compile(r"/api/(?:proxy|v1)/opspilot/bot_mgmt/workflow_attachment/download/([A-Za-z0-9_.:\-]+)/?")
_FILENAME_RE = re.compile(r"""['"]filename['"]\s*:\s*['"]([^'"]+)['"]""")

# 企微长连接：普通文件 5 字节到 20MB，单片不超过 512KB，最多 100 片。
_MIN_FILE_BYTES = 5
_MAX_FILE_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_CHUNK_BYTES = 512 * 1024
_MAX_FILENAME_BYTES = 256
# 与企微 Node SDK 一致：分片失败后再试 2 次（共 3 次）。
_CHUNK_UPLOAD_MAX_RETRIES = 2
_CHUNK_RETRY_BACKOFF_SECONDS = 0.2

Exchange = Callable[[dict], dict]


class WecomMediaRejected(ValueError):
    """企微素材上传被拒绝或回执不完整。"""

    def __init__(
        self,
        stage: str,
        *,
        errcode: object = None,
        errmsg: str | None = None,
        reason: str | None = None,
    ):
        self.stage = stage
        self.errcode = errcode
        self.errmsg = (errmsg or "").strip() or None
        self.reason = (reason or "").strip() or None
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [f"stage={self.stage}"]
        if self.errcode is not None and self.errcode != "":
            parts.append(f"errcode={self.errcode}")
        if self.errmsg:
            parts.append(f"errmsg={self.errmsg}")
        if self.reason:
            parts.append(f"reason={self.reason}")
        return " ".join(parts)


def generated_file_from_agui_event(event: dict[str, Any]) -> tuple[str, bytes] | None:
    """从 AG-UI 的 report_file_download 取出文件名和原文。其他事件返回 None。"""
    if not isinstance(event, dict) or event.get("type") != "CUSTOM" or event.get("name") != "report_file_download":
        return None
    value = event.get("value")
    if not isinstance(value, dict):
        return None
    filename = value.get("filename")
    encoded = value.get("content_base64")
    if not isinstance(filename, str) or not filename.strip():
        return None
    if not isinstance(encoded, str) or not encoded:
        return None
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None
    if not content:
        return None
    return filename, content


def attachment_from_tool_result(event: dict[str, Any]) -> tuple[str, str] | None:
    """从生成附件的工具结果里取出文件名和下载令牌。没有下载地址时返回 None。"""
    if not isinstance(event, dict) or event.get("type") != "TOOL_CALL_RESULT":
        return None
    content = event.get("content")
    if not isinstance(content, str) or "workflow_attachment/download/" not in content:
        return None
    matched = _ATTACHMENT_URL_RE.search(content)
    if matched is None:
        return None
    filename = ""
    name = _FILENAME_RE.search(content)
    if name is not None:
        filename = name.group(1)
    return filename, matched.group(1)


def upload_wecom_file(exchange: Exchange, *, filename: str, content: bytes, media_type: str = "file") -> str:
    """分片上传并返回 media_id。exchange 发送一帧并返回企微回执。"""
    limit = _MAX_IMAGE_BYTES if media_type == "image" else _MAX_FILE_BYTES
    if len(content) < _MIN_FILE_BYTES or len(content) > limit:
        raise WecomMediaRejected("validate_size", reason="out_of_range")
    chunks = [content[start : start + _CHUNK_BYTES] for start in range(0, len(content), _CHUNK_BYTES)]
    safe_name = _safe_filename(filename)
    init_ack = _exchange_ok(
        exchange,
        {
            "cmd": "aibot_upload_media_init",
            "headers": {"req_id": uuid.uuid4().hex},
            "body": {
                "type": media_type,
                "filename": safe_name,
                "total_size": len(content),
                "total_chunks": len(chunks),
                "md5": hashlib.md5(content).hexdigest(),
            },
        },
        "upload_init",
        retries=0,
    )
    upload_id = init_ack.get("upload_id")
    if not isinstance(upload_id, str) or not upload_id:
        _log_incomplete_ack("upload_init", init_ack)
        raise WecomMediaRejected("upload_init", reason="missing_upload_id")
    for index, chunk in enumerate(chunks):
        _exchange_ok(
            exchange,
            {
                "cmd": "aibot_upload_media_chunk",
                "headers": {"req_id": uuid.uuid4().hex},
                "body": {
                    "upload_id": upload_id,
                    "chunk_index": index,
                    "base64_data": base64.b64encode(chunk).decode("ascii"),
                },
            },
            f"upload_chunk:{index}",
            retries=_CHUNK_UPLOAD_MAX_RETRIES,
        )
    finish_ack = _exchange_ok(
        exchange,
        {
            "cmd": "aibot_upload_media_finish",
            "headers": {"req_id": uuid.uuid4().hex},
            "body": {"upload_id": upload_id},
        },
        "upload_finish",
        retries=0,
    )
    media_id = finish_ack.get("media_id")
    if not isinstance(media_id, str) or not media_id:
        _log_incomplete_ack("upload_finish", finish_ack)
        raise WecomMediaRejected("upload_finish", reason="missing_media_id")
    return media_id


def _exchange_ok(exchange: Exchange, payload: dict, stage: str, *, retries: int) -> dict:
    attempts = max(1, retries + 1)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return _require_ok(exchange(payload), stage)
        except WecomMediaRejected as exc:
            last_exc = exc
        except Exception as exc:
            last_exc = _normalize_exchange_error(exc, stage)
        if attempt + 1 < attempts:
            time.sleep(_CHUNK_RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue
        if isinstance(last_exc, WecomMediaRejected):
            raise last_exc
        if last_exc is not None:
            raise last_exc
        raise WecomMediaRejected(stage, reason="unknown")
    raise WecomMediaRejected(stage, reason="unknown")


def _normalize_exchange_error(exc: BaseException, stage: str) -> WecomMediaRejected:
    if isinstance(exc, WecomMediaRejected):
        return exc
    message = str(exc)
    matched = re.search(r"errcode=(\d+)", message)
    errmsg_m = re.search(r"errmsg=([^,)]+)", message)
    if matched or isinstance(exc, TimeoutError):
        return WecomMediaRejected(
            stage,
            errcode=matched.group(1) if matched else "-",
            errmsg=(errmsg_m.group(1).strip() if errmsg_m else message[:200]),
            reason=type(exc).__name__,
        )
    return WecomMediaRejected(stage, reason=type(exc).__name__)


def _require_ok(ack: dict, stage: str) -> dict:
    if not isinstance(ack, dict):
        raise WecomMediaRejected(stage, reason="invalid_ack")
    errcode = ack.get("errcode", 0)
    if errcode not in (0, "0", None):
        raise WecomMediaRejected(stage, errcode=errcode, errmsg=str(ack.get("errmsg") or ""))
    body = ack.get("body")
    return body if isinstance(body, dict) else {}


def _log_incomplete_ack(stage: str, ack: dict) -> None:
    if isinstance(ack, dict):
        body = ack.get("body")
        body_keys = sorted(body.keys()) if isinstance(body, dict) else []
        logger.debug(
            "event=wecom_aibot_media_incomplete_ack stage=%s errcode=%s has_errmsg=%s body_keys=%s",
            stage,
            ack.get("errcode"),
            bool(ack.get("errmsg")),
            ",".join(body_keys)[:120],
        )
    else:
        logger.debug("event=wecom_aibot_media_incomplete_ack stage=%s ack_type=%s", stage, type(ack).__name__)


def _safe_filename(filename: str) -> str:
    base = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "file"
    raw = base.encode("utf-8")
    if len(raw) <= _MAX_FILENAME_BYTES:
        return base
    return raw[:_MAX_FILENAME_BYTES].decode("utf-8", errors="ignore") or "file"
