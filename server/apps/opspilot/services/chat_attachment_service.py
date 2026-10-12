"""对话附件：上传校验、解析缓存、发送门禁与按预算注入。"""

from __future__ import annotations

import base64
import os
from datetime import timedelta

from celery import current_app
from celery.exceptions import SoftTimeLimitExceeded
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.token_utils import count_text_tokens, get_encoding
from apps.opspilot.models import ChatAttachment
from apps.opspilot.services.llm_context_budget import DEFAULT_CHAT_SCENE_OUTPUT_TOKENS, working_budget_for_model

MAX_ATTACHMENTS = 5
DOCUMENT_MAX_BYTES = 20 * 1024 * 1024
IMAGE_MAX_BYTES = 5 * 1024 * 1024
ORPHAN_AGE = timedelta(hours=24)
PENDING_STALE_AGE = timedelta(minutes=10)
PARSE_QUEUE = "opspilot_chat_parse"
PARSE_TASK_NAME = "apps.opspilot.tasks.parse_chat_attachment"
TRUNCATION_MARKER = "文件已截断"

DOCUMENT_EXTENSIONS = {"pdf", "docx", "pptx", "xlsx", "csv", "txt", "md"}
IMAGE_EXTENSIONS = {"jpeg", "jpg", "png", "gif", "webp"}
HEAVY_EXTENSIONS = {"pdf", "docx", "pptx", "xlsx"}
LIGHT_TEXT_EXTENSIONS = {"txt", "md", "csv"}

MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "txt": "text/plain",
    "md": "text/markdown",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}

UPLOAD_ACCEPTED_TEMPLATE = "chat_attachment stored: attachment_id=%s status=%s"
UPLOAD_REJECTED_TEMPLATE = "chat_attachment rejected: failed_stage=%s error_type=%s"
PARSE_FINISHED_TEMPLATE = "chat_attachment parse finished: attachment_id=%s status=%s"
PARSE_FAILED_TEMPLATE = "chat_attachment parse failed: attachment_id=%s failed_stage=%s error_type=%s"
IMAGES_DROPPED_TEMPLATE = "chat_attachment images dropped: count=%s reason=model_not_multimodal"
PENDING_CONVERGED_TEMPLATE = "chat_attachment pending converged: failed_count=%s"
ORPHAN_CLEANED_TEMPLATE = "chat_attachment orphan cleanup: deleted_count=%s"


class ChatAttachmentError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "chat_attachment_rejected"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def attachment_token_budget(llm_model) -> int:
    """文档注入总预算与单文件上限，都取知识注入预算，不另造窗口。"""
    budget = working_budget_for_model(llm_model, scene_output_default=DEFAULT_CHAT_SCENE_OUTPUT_TOKENS)
    return budget.knowledge_inject_tokens


def normalize_attachment_ids(raw) -> list[int]:
    if raw in (None, "", []):
        return []
    if not isinstance(raw, list):
        raise ChatAttachmentError("attachment_ids 必须是数组")
    if len(raw) > MAX_ATTACHMENTS:
        raise ChatAttachmentError("单条消息最多 5 个附件", code="too_many_attachments")
    ids: list[int] = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError) as exc:
            raise ChatAttachmentError("附件 ID 无效", code="invalid_attachment_id") from exc
        if value <= 0 or value in ids:
            raise ChatAttachmentError("附件 ID 无效", code="invalid_attachment_id")
        ids.append(value)
    return ids


def store_upload(*, filename: str, data: bytes, owner_key: str, team_id: str) -> ChatAttachment:
    """校验并落库。轻文本与图片在请求内就绪；重格式只投递解析任务，调用方不等待。"""
    try:
        kind, extension, mime_type = classify_upload(filename, data)
    except ChatAttachmentError as exc:
        logger.warning(UPLOAD_REJECTED_TEMPLATE, "validate", exc.code)
        raise
    safe_name = _safe_filename(filename, extension)
    parsed_text = ""
    status = ChatAttachment.STATUS_PENDING
    if kind == "image":
        status = ChatAttachment.STATUS_READY
    elif extension in LIGHT_TEXT_EXTENSIONS:
        parsed_text = _decode_light_text(data)
        status = ChatAttachment.STATUS_READY
    attachment = ChatAttachment.objects.create(
        file=ContentFile(data, name=safe_name),
        original_name=safe_name,
        mime_type=mime_type,
        size=len(data),
        status=status,
        parsed_text=parsed_text,
        owner_key=owner_key,
        team_id=str(team_id),
    )
    if extension in HEAVY_EXTENSIONS:
        current_app.send_task(PARSE_TASK_NAME, args=[attachment.id], queue=PARSE_QUEUE)
    logger.info(UPLOAD_ACCEPTED_TEMPLATE, attachment.id, attachment.status)
    return attachment


def classify_upload(filename: str, data: bytes) -> tuple[str, str, str]:
    extension = _extension(filename)
    if extension not in DOCUMENT_EXTENSIONS and extension not in IMAGE_EXTENSIONS:
        raise ChatAttachmentError("不支持的文件类型", code="unsupported_type")
    if not data:
        raise ChatAttachmentError("文件内容为空", code="empty_file")
    if _looks_executable(data):
        raise ChatAttachmentError("不支持的文件类型", code="unsupported_type")
    if extension in IMAGE_EXTENSIONS:
        if len(data) > IMAGE_MAX_BYTES:
            raise ChatAttachmentError("文件大小超出限制", code="file_too_large")
        detected = _detect_raster_content_type(data)
        expected = MIME_BY_EXTENSION[extension]
        if detected != expected:
            raise ChatAttachmentError("文件内容与扩展名不符", code="magic_mismatch")
        return "image", extension, expected
    if len(data) > DOCUMENT_MAX_BYTES:
        raise ChatAttachmentError("文件大小超出限制", code="file_too_large")
    if extension == "pdf":
        if not data.startswith(b"%PDF"):
            raise ChatAttachmentError("文件内容与扩展名不符", code="magic_mismatch")
    elif extension in {"docx", "pptx", "xlsx"}:
        if not data.startswith(b"PK\x03\x04"):
            raise ChatAttachmentError("文件内容与扩展名不符", code="magic_mismatch")
    elif extension in LIGHT_TEXT_EXTENSIONS:
        if data.startswith(b"%PDF") or data.startswith(b"PK") or _detect_raster_content_type(data):
            raise ChatAttachmentError("文件内容与扩展名不符", code="magic_mismatch")
        _decode_light_text(data)
    return "document", extension, MIME_BY_EXTENSION[extension]


def load_sendable_attachments(raw_ids, owner_key: str, team_id: str) -> list[ChatAttachment]:
    """只读数据库状态。非 ready、越权或超过 5 个立即拒绝，不等待解析。"""
    ids = normalize_attachment_ids(raw_ids)
    if not ids:
        return []
    found = {item.id: item for item in ChatAttachment.objects.filter(id__in=ids, owner_key=owner_key, team_id=str(team_id))}
    ordered: list[ChatAttachment] = []
    for attachment_id in ids:
        attachment = found.get(attachment_id)
        if attachment is None:
            raise ChatAttachmentError("无权访问该附件", status=403, code="attachment_forbidden")
        if attachment.status == ChatAttachment.STATUS_PENDING:
            raise ChatAttachmentError("文件解析中，请稍后再发送", code="attachment_pending")
        if attachment.status != ChatAttachment.STATUS_READY:
            raise ChatAttachmentError("文件解析失败，无法发送", code="attachment_failed")
        ordered.append(attachment)
    return ordered


def apply_current_turn_attachments(user_message, raw_ids, *, owner_key: str, team_id: str, llm_model):
    """调试聊天等无历史回填入口：只注入当轮附件，不写 message 外键。"""
    attachments = load_sendable_attachments(raw_ids, owner_key, team_id)
    if not attachments:
        return user_message
    token_budget = attachment_token_budget(llm_model)
    include_images = llm_model is None or getattr(llm_model, "is_multimodal", True)
    composed, _remaining = compose_user_message(
        user_message,
        attachments,
        token_budget=token_budget,
        per_file_cap=token_budget,
        include_images=include_images,
    )
    return composed


def bind_attachments(attachments: list[ChatAttachment], *, conversation, message) -> None:
    if not attachments:
        return
    ChatAttachment.objects.filter(id__in=[item.id for item in attachments]).update(
        conversation=conversation,
        message=message,
    )


def compose_user_message(user_message, attachments: list[ChatAttachment], *, token_budget: int, per_file_cap: int, include_images: bool):
    """当轮文档按预算注入文本；图片转 data URI。返回 (user_message, remaining_budget)。"""
    text = _message_text(user_message)
    remaining = token_budget
    blocks: list[str] = []
    image_uris: list[str] = []
    dropped_images = 0
    for attachment in attachments:
        if _is_image(attachment):
            if include_images:
                image_uris.append(_image_data_uri(attachment))
            else:
                dropped_images += 1
            continue
        block, used = _take_document(attachment, remaining, per_file_cap)
        remaining = max(0, remaining - used)
        blocks.append(block)
    if dropped_images:
        logger.info(IMAGES_DROPPED_TEMPLATE, dropped_images)
    if blocks:
        text = f"{text}\n\n" + "\n\n".join(blocks) if text else "\n\n".join(blocks)
    if not image_uris:
        return text, remaining
    return [{"type": "image_url", "image_url": uri} for uri in image_uris] + [{"type": "message", "message": text}], remaining


def history_document_suffixes(message_ids: list[int], *, token_budget: int, per_file_cap: int) -> dict[int, str]:
    """历史文档重新注入。预算用尽后更老的文件只留占位，图片不回放。"""
    if token_budget is None or not message_ids:
        return {}
    grouped: dict[int, list[ChatAttachment]] = {}
    queryset = ChatAttachment.objects.filter(message_id__in=message_ids, status=ChatAttachment.STATUS_READY).order_by("id")
    for attachment in queryset:
        if _is_image(attachment):
            continue
        grouped.setdefault(attachment.message_id, []).append(attachment)
    remaining = token_budget
    suffixes: dict[int, str] = {}
    for message_id in reversed(message_ids):
        blocks = []
        for attachment in grouped.get(message_id, []):
            block, used = _take_document(attachment, remaining, per_file_cap)
            remaining = max(0, remaining - used)
            blocks.append(block)
        if blocks:
            suffixes[message_id] = "\n\n".join(blocks)
    return suffixes


def parse_chat_attachment(attachment_id: int) -> None:
    """Celery 任务入口。只读已落库文件，成功写 parsed_text；失败或超时转为 failed。"""
    attachment = ChatAttachment.objects.filter(id=attachment_id).first()
    if attachment is None or attachment.status != ChatAttachment.STATUS_PENDING:
        return
    try:
        with attachment.file.open("rb") as handle:
            data = handle.read()
        # MarkItDown 会加载音频等转换器，只在解析任务里导入。
        from apps.opspilot.services.wiki.parsing.markitdown_parser import MarkItDownParser

        parsed = MarkItDownParser().parse_file(data, attachment.original_name)
        attachment.parsed_text = parsed or ""
        attachment.status = ChatAttachment.STATUS_READY
        attachment.failure_reason = ""
        attachment.save(update_fields=["parsed_text", "status", "failure_reason"])
        logger.info(PARSE_FINISHED_TEMPLATE, attachment.id, attachment.status)
    except SoftTimeLimitExceeded as exc:
        _mark_parse_failed(attachment, "timeout", exc)
    except Exception as exc:
        _mark_parse_failed(attachment, "parse", exc)


def cleanup_chat_attachments(*, now=None) -> dict[str, int]:
    """孤儿（无消息且超过 24h）删除；卡住的 pending 超过 10 分钟转为 failed。"""
    current = now or timezone.now()
    failed_count = ChatAttachment.objects.filter(
        status=ChatAttachment.STATUS_PENDING,
        created_at__lt=current - PENDING_STALE_AGE,
    ).update(status=ChatAttachment.STATUS_FAILED, failure_reason="解析超时")
    logger.info(PENDING_CONVERGED_TEMPLATE, failed_count)
    deleted_count = 0
    orphans = ChatAttachment.objects.filter(message__isnull=True, created_at__lt=current - ORPHAN_AGE)
    for attachment in orphans.iterator():
        attachment.delete()
        deleted_count += 1
    logger.info(ORPHAN_CLEANED_TEMPLATE, deleted_count)
    return {"failed_count": failed_count, "deleted_count": deleted_count}


def serialize_attachment(attachment: ChatAttachment) -> dict:
    return {
        "id": attachment.id,
        "name": attachment.original_name,
        "mime": attachment.mime_type,
        "size": attachment.size,
        "status": attachment.status,
    }


def _take_document(attachment: ChatAttachment, remaining: int, per_file_cap: int) -> tuple[str, int]:
    if remaining <= 0:
        return _placeholder(attachment.original_name), 0
    return render_document(attachment.original_name, attachment.parsed_text or "", min(per_file_cap, remaining))


def render_document(name: str, parsed_text: str, allowance: int) -> tuple[str, int]:
    header = _placeholder(name)
    header_tokens = count_text_tokens(header)
    if allowance <= header_tokens:
        return header, header_tokens if allowance >= header_tokens else 0
    body = parsed_text or ""
    full = f"{header}\n{body}" if body else header
    full_tokens = count_text_tokens(full)
    if full_tokens <= allowance:
        return full, full_tokens
    marker = f"\n{TRUNCATION_MARKER}"
    marker_tokens = count_text_tokens(marker)
    newline_tokens = count_text_tokens("\n")
    room = allowance - header_tokens - marker_tokens - newline_tokens
    if room <= 0:
        return header, header_tokens
    snippet = _truncate_to_tokens(body, room)
    block = f"{header}\n{snippet}{marker}"
    return block, count_text_tokens(block)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0 or not text:
        return ""
    encoding = get_encoding()
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoding.decode(tokens[:max_tokens])


def _placeholder(name: str) -> str:
    return f"[文件: {name}]"


def _mark_parse_failed(attachment: ChatAttachment, stage: str, exc: BaseException) -> None:
    attachment.status = ChatAttachment.STATUS_FAILED
    attachment.failure_reason = "解析超时" if stage == "timeout" else "解析失败"
    attachment.save(update_fields=["status", "failure_reason"])
    logger.error(
        PARSE_FAILED_TEMPLATE,
        attachment.id,
        stage,
        type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def _message_text(user_message) -> str:
    if isinstance(user_message, str):
        return user_message
    if isinstance(user_message, list):
        for item in user_message:
            if isinstance(item, dict) and item.get("type") != "image_url":
                text = item.get("message", item.get("text", ""))
                if isinstance(text, str):
                    return text
        return ""
    return str(user_message or "")


def _is_image(attachment: ChatAttachment) -> bool:
    return (attachment.mime_type or "").startswith("image/")


def _image_data_uri(attachment: ChatAttachment) -> str:
    with attachment.file.open("rb") as handle:
        data = handle.read()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{attachment.mime_type};base64,{encoded}"


def _extension(filename: str) -> str:
    base = os.path.basename(filename or "")
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def _safe_filename(filename: str, extension: str) -> str:
    base = os.path.basename(filename or "").replace("\\", "/").split("/")[-1]
    base = base.strip() or f"attachment.{extension}"
    return base[-255:]


def _looks_executable(data: bytes) -> bool:
    return data.startswith(b"MZ") or data.startswith(b"\x7fELF")


def _detect_raster_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _decode_light_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ChatAttachmentError("文件内容与扩展名不符", code="magic_mismatch") from exc
