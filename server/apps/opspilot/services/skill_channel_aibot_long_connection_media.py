"""把技能生成的文件经企微长连接分片上传，再按 media_id 回复文件消息。"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
from typing import Any, Callable

_ATTACHMENT_URL_RE = re.compile(r"/api/(?:proxy|v1)/opspilot/bot_mgmt/workflow_attachment/download/([A-Za-z0-9_.:\-]+)/?")
_FILENAME_RE = re.compile(r"""['"]filename['"]\s*:\s*['"]([^'"]+)['"]""")

# 企微长连接：普通文件 5 字节到 20MB，单片不超过 512KB，最多 100 片。
_MIN_FILE_BYTES = 5
_MAX_FILE_BYTES = 20 * 1024 * 1024
_CHUNK_BYTES = 512 * 1024
_MAX_FILENAME_BYTES = 256

Exchange = Callable[[dict], dict]


class WecomMediaRejected(ValueError):
    """文件大小不在企微长连接允许的范围内。"""


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


def upload_wecom_file(exchange: Exchange, *, filename: str, content: bytes) -> str:
    """分片上传并返回 media_id。exchange 发送一帧并返回企微回执。"""
    if len(content) < _MIN_FILE_BYTES or len(content) > _MAX_FILE_BYTES:
        raise WecomMediaRejected("WecomMediaRejected")
    chunks = [content[start : start + _CHUNK_BYTES] for start in range(0, len(content), _CHUNK_BYTES)]
    safe_name = _safe_filename(filename)
    init_ack = _require_ok(
        exchange(
            {
                "cmd": "aibot_upload_media_init",
                "headers": {"req_id": uuid.uuid4().hex},
                "body": {
                    "type": "file",
                    "filename": safe_name,
                    "total_size": len(content),
                    "total_chunks": len(chunks),
                    "md5": hashlib.md5(content).hexdigest(),
                },
            }
        )
    )
    upload_id = init_ack.get("upload_id")
    if not isinstance(upload_id, str) or not upload_id:
        raise WecomMediaRejected("WecomMediaRejected")
    for index, chunk in enumerate(chunks):
        _require_ok(
            exchange(
                {
                    "cmd": "aibot_upload_media_chunk",
                    "headers": {"req_id": uuid.uuid4().hex},
                    "body": {
                        "upload_id": upload_id,
                        "chunk_index": index,
                        "base64_data": base64.b64encode(chunk).decode("ascii"),
                    },
                }
            )
        )
    finish_ack = _require_ok(
        exchange(
            {
                "cmd": "aibot_upload_media_finish",
                "headers": {"req_id": uuid.uuid4().hex},
                "body": {"upload_id": upload_id},
            }
        )
    )
    media_id = finish_ack.get("media_id")
    if not isinstance(media_id, str) or not media_id:
        raise WecomMediaRejected("WecomMediaRejected")
    return media_id


def _require_ok(ack: dict) -> dict:
    if not isinstance(ack, dict):
        raise WecomMediaRejected("WecomMediaRejected")
    errcode = ack.get("errcode", 0)
    if errcode not in (0, "0", None):
        raise WecomMediaRejected("WecomMediaRejected")
    body = ack.get("body")
    return body if isinstance(body, dict) else {}


def _safe_filename(filename: str) -> str:
    base = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "file"
    raw = base.encode("utf-8")
    if len(raw) <= _MAX_FILENAME_BYTES:
        return base
    return raw[:_MAX_FILENAME_BYTES].decode("utf-8", errors="ignore") or "file"
