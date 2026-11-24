from __future__ import annotations

import re
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import urllib3
from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.opspilot.models import WorkflowAttachmentAsset
from apps.opspilot.services.attachment_theme import FONT as _FONT
from apps.opspilot.services.attachment_theme import HEADER_FILL as _HEADER_FILL
from apps.opspilot.services.attachment_theme import MUTED as _MUTED
from apps.opspilot.services.attachment_theme import RULE as _RULE
from apps.opspilot.services.attachment_theme import SECTION as _SECTION
from apps.opspilot.services.attachment_theme import TABLE_HEADER as _TABLE_HEADER
from apps.opspilot.services.attachment_theme import TEXT as _TEXT
from apps.opspilot.services.attachment_theme import TITLE as _TITLE
from apps.opspilot.services.attachment_theme import TextRun as _TextRun
from apps.opspilot.services.attachment_theme import build_docx_bytes as _build_docx_bytes
from apps.opspilot.services.attachment_theme import build_pdf_bytes as _build_pdf_bytes
from apps.opspilot.services.attachment_theme import build_xlsx_bytes as _build_xlsx_bytes
from apps.opspilot.services.attachment_theme import inline_text as _inline_text
from apps.opspilot.services.attachment_theme import iter_markdown_blocks as _iter_markdown_blocks
from apps.opspilot.services.attachment_theme import should_prefix_title as _should_prefix_title

# 工作流附件下载令牌的签名盐值与默认有效期(秒)。
# 使用签名 + 过期时间替代原先可被猜测且永不失效的明文 token。
WORKFLOW_ATTACHMENT_DOWNLOAD_SALT = "opspilot.workflow_attachment.download"
MINIO_CONNECTION_FAILURE_MESSAGE = "连不上 MinIO，文件没有保存。请稍后再试，或联系管理员处理 MinIO。"
_CONNECTION_ERROR_NAMES = frozenset({"NewConnectionError", "ConnectTimeoutError", "NameResolutionError", "ProtocolError"})
_MINIO_HTTP_POOL = None


def workflow_attachment_download_max_age() -> int:
    """下载令牌最大有效期(秒)，默认 24 小时，可通过 settings 覆盖。"""
    return int(getattr(settings, "WORKFLOW_ATTACHMENT_DOWNLOAD_MAX_AGE", 24 * 60 * 60))


def _attachment_download_token(asset: WorkflowAttachmentAsset) -> str:
    """令牌绑定附件主键与 execution_id，下载时校验过期和绑定关系。"""
    return signing.dumps(
        {"aid": asset.id, "eid": asset.execution_id},
        salt=WORKFLOW_ATTACHMENT_DOWNLOAD_SALT,
    )


def build_signed_attachment_download_url(asset: WorkflowAttachmentAsset) -> str:
    """为工作流附件生成带签名且会过期的下载 URL。

    URL 使用 /api/proxy/... 前缀，以便浏览器端通过 Next.js 代理路由
    转发到后台 /api/v1/... 接口，而不是被 Next.js 当作页面路由处理。
    """
    return f"/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/{_attachment_download_token(asset)}/"


def build_server_attachment_download_path(asset: WorkflowAttachmentAsset) -> str:
    """后台下载接口。由 server 从 MinIO 读出附件，不经过站点代理。"""
    return f"/api/v1/opspilot/bot_mgmt/workflow_attachment/download/{_attachment_download_token(asset)}/"


def resolve_signed_attachment_token(download_token: str) -> WorkflowAttachmentAsset | None:
    """校验签名下载令牌并返回绑定的附件，过期/非法/不匹配时抛出 BadSignature。"""
    payload = signing.loads(
        download_token,
        salt=WORKFLOW_ATTACHMENT_DOWNLOAD_SALT,
        max_age=workflow_attachment_download_max_age(),
    )
    if not isinstance(payload, dict):
        raise signing.BadSignature("Malformed download token payload")
    asset = WorkflowAttachmentAsset.objects.filter(id=payload.get("aid")).first()
    # 校验签名内绑定的 execution_id，防止令牌被篡改后指向其它附件
    if not asset or asset.execution_id != payload.get("eid"):
        return None
    return asset


_ATTACHMENT_DOWNLOAD_URL_RE = re.compile(r"/api/(?:proxy|v1)/opspilot/bot_mgmt/workflow_attachment/download/([A-Za-z0-9_.:\-]+)/?")


def refresh_attachment_download_urls(text: str) -> str:
    """历史消息里的下载令牌会过期。读会话时按原签名重签，不放宽公开下载接口。"""
    if not text or "workflow_attachment/download/" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        try:
            payload = signing.loads(
                match.group(1),
                salt=WORKFLOW_ATTACHMENT_DOWNLOAD_SALT,
                max_age=None,
            )
        except signing.BadSignature:
            return match.group(0)
        if not isinstance(payload, dict):
            return match.group(0)
        asset = WorkflowAttachmentAsset.objects.filter(id=payload.get("aid")).first()
        if not asset or asset.execution_id != payload.get("eid"):
            return match.group(0)
        return build_signed_attachment_download_url(asset)

    return _ATTACHMENT_DOWNLOAD_URL_RE.sub(_replace, text)


ATTACHMENT_FILE_TYPE_CONFIG = {
    "txt": {
        "extension": "txt",
        "mime_type": "text/plain",
    },
    "text": {
        "extension": "txt",
        "mime_type": "text/plain",
    },
    "md": {
        "extension": "md",
        "mime_type": "text/markdown",
    },
    "html": {
        "extension": "html",
        "mime_type": "text/html",
    },
    "pdf": {
        "extension": "pdf",
        "mime_type": "application/pdf",
    },
    "pptx": {
        "extension": "pptx",
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
    "ppt": {
        "extension": "pptx",
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
    "powerpoint": {
        "extension": "pptx",
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
    "docx": {
        "extension": "docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "word": {
        "extension": "docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "xlsx": {
        "extension": "xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "csv": {
        "extension": "csv",
        "mime_type": "text/csv",
    },
}


_ATTACHMENT_VERSION_RE = re.compile(r"_v(\d+)\.(\d+)$", re.IGNORECASE)
# 修订标签只接受短后缀。长标题即使以前缀开头，也是另一份文档。
_REVISION_LABEL_MAX_CHARS = 12


def attachment_name_parts(filename: str) -> tuple[str, str]:
    base = str(filename or "").replace("\\", "/").split("/")[-1]
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        return stem, ext
    return base, ""


def attachment_version_base(stem: str) -> tuple[str, tuple[int, int] | None]:
    match = _ATTACHMENT_VERSION_RE.search(stem or "")
    if not match:
        return stem, None
    return stem[: match.start()], (int(match.group(1)), int(match.group(2)))


def _revision_suffix(longer: str, shorter: str) -> str | None:
    """较短标题后只多一段短修订标签时，才视为同一份文档。"""
    if len(shorter) < 2 or len(shorter) * 2 < len(longer):
        return None
    prefix = f"{shorter}_"
    if not longer.startswith(prefix):
        return None
    label = longer[len(prefix) :]
    if not label or "_" in label or len(label) > _REVISION_LABEL_MAX_CHARS:
        return None
    return label


def _same_attachment_document(new_base: str, prior_base: str) -> bool:
    left = (new_base or "").strip()
    right = (prior_base or "").strip()
    if not left or not right:
        return False
    if left == right:
        return True
    return _revision_suffix(left, right) is not None or _revision_suffix(right, left) is not None


def _version_rank(version: tuple[int, int] | None) -> tuple[int, int, int]:
    if version is None:
        return (0, 0, 0)
    return (1, version[0], version[1])


def _best_matching_prior(
    base: str,
    prior_filenames: list[str] | None,
    *,
    known_extension_only: bool = False,
) -> tuple[str, tuple[int, int] | None, str] | None:
    """同一文档取最大版本。版本相同时用更短的基准名，仍相同则用列表中更靠后的一条。"""
    best: tuple[str, tuple[int, int] | None, str, int] | None = None
    for index, prior in enumerate(prior_filenames or []):
        prior_stem, prior_ext = attachment_name_parts(str(prior))
        prior_base, prior_version = attachment_version_base(prior_stem)
        locked_type = prior_ext.lower()
        if known_extension_only and locked_type not in ATTACHMENT_FILE_TYPE_CONFIG:
            continue
        if not _same_attachment_document(base, prior_base):
            continue
        if best is None:
            best = (prior_base, prior_version, locked_type, index)
            continue
        best_rank = _version_rank(best[1])
        candidate_rank = _version_rank(prior_version)
        if candidate_rank > best_rank:
            best = (prior_base, prior_version, locked_type, index)
            continue
        if candidate_rank < best_rank:
            continue
        if len(prior_base) < len(best[0]) or (len(prior_base) == len(best[0]) and index > best[3]):
            best = (prior_base, prior_version, locked_type, index)
    if best is None:
        return None
    return best[0], best[1], best[2]


def version_attachment_filename(filename: str, prior_filenames: list[str] | None = None) -> str:
    """首次生成为 名称_v1.0，改同一份文件则在已有最大版本上递增为 _v1.1、_v1.2。"""
    stem, ext = attachment_name_parts(filename)
    base, current = attachment_version_base(stem)
    suffix = f".{ext}" if ext else ""
    matched = _best_matching_prior(base, prior_filenames)
    if matched is not None:
        matched_base, matched_version, _locked_type = matched
        if matched_version is None:
            major, minor = 1, 1
        else:
            major, minor = matched_version[0], matched_version[1] + 1
        return f"{matched_base}_v{major}.{minor}{suffix}"
    if current is None and base:
        return f"{base}_v1.0{suffix}"
    return f"{stem}{suffix}" if stem else filename


def lock_revision_attachment_type(file_type: str, filename: str, prior_filenames: list[str] | None = None) -> tuple[str, str]:
    """改已有文件时沿用最大版本的类型。PPTX 的修改不能落成 md 或其他格式。"""
    stem, _ext = attachment_name_parts(filename)
    base, _current = attachment_version_base(stem)
    matched = _best_matching_prior(base, prior_filenames, known_extension_only=True)
    if matched is None:
        return file_type, filename
    matched_base, _matched_version, locked_type = matched
    expected = ATTACHMENT_FILE_TYPE_CONFIG[locked_type]["extension"]
    new_stem = stem or matched_base
    return locked_type, f"{new_stem}.{expected}"


def normalize_attachment_file_type(file_type: str, filename: str = "") -> tuple[str, str, str]:
    normalized_type = (file_type or "").strip().lower()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if not normalized_type and extension:
        normalized_type = extension

    if normalized_type not in ATTACHMENT_FILE_TYPE_CONFIG:
        raise ValueError(f"不支持的附件类型: {file_type or extension or 'unknown'}")

    config = ATTACHMENT_FILE_TYPE_CONFIG[normalized_type]
    expected_extension = config["extension"]
    normalized_filename = filename or f"attachment.{expected_extension}"
    if "." not in normalized_filename:
        normalized_filename = f"{normalized_filename}.{expected_extension}"
    else:
        stem, current_extension = normalized_filename.rsplit(".", 1)
        if current_extension.lower() != expected_extension:
            normalized_filename = f"{stem}.{expected_extension}"

    return normalized_type, normalized_filename, config["mime_type"]


def build_attachment_bytes(
    content: str,
    file_type: str,
    title: str = "",
    *,
    genre: str = "business_report",
    header_rows: int = 1,
    merges: list[str] | None = None,
) -> bytes:
    normalized_type, _, _ = normalize_attachment_file_type(file_type)
    safe_content = content or ""
    safe_title = title or "Attachment"

    if normalized_type in ("md", "txt", "text", "html"):
        return safe_content.encode("utf-8")
    if normalized_type == "pdf":
        return _build_pdf_bytes(safe_content, safe_title, genre=genre)
    if normalized_type in ("docx", "word"):
        return _build_docx_bytes(safe_content, safe_title, genre=genre)
    if normalized_type in ("pptx", "ppt", "powerpoint"):
        return _build_pptx_bytes(safe_content, safe_title)
    if normalized_type == "xlsx":
        return _build_xlsx_bytes(safe_content, header_rows=header_rows, merges=merges)
    if normalized_type == "csv":
        return _build_csv_bytes(safe_content)

    raise ValueError(f"不支持的附件类型: {file_type}")


def _minio_http_pool():
    """附件上传专用连接池：连接失败不重试。"""
    global _MINIO_HTTP_POOL
    if _MINIO_HTTP_POOL is None:
        _MINIO_HTTP_POOL = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=5, read=300),
            maxsize=10,
            retries=False,
        )
    return _MINIO_HTTP_POOL


def _upload_workflow_attachment_bytes(*, filename: str, content_bytes: bytes, mime_type: str) -> str:
    """用本次新建的 MinioBackend 上传。

    django-minio-backend 3.6.0 把 Minio 客户端放在实例的 ``_MinioBackend__CLIENT`` 上，
    初值为 None。``getattr`` 在实例没有该属性时会读到类上的同名缓存。
    附件字段和其他 ``MinioBackend(bucket_name="munchkin-private")`` 只要共用那个客户端，
    改 ``_http`` 或字段 storage 的 ``HTTP_CLIENT`` 就会让别的上传也不再重试。
    这里只给本次上传一个自己的 storage，连接池不装到已有客户端上。
    """
    from django_minio_backend import MinioBackend

    field = WorkflowAttachmentAsset._meta.get_field("file")
    isolated = MinioBackend(bucket_name=field.storage.bucket, http_client=_minio_http_pool())
    content = ContentFile(content_bytes, name=filename)
    content.content_type = mime_type
    object_name = field.generate_filename(WorkflowAttachmentAsset(), filename)
    return isolated.save(object_name, content)


def _is_minio_connection_error(exc: BaseException) -> bool:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (ConnectionError, TimeoutError)):
            return True
        if type(current).__name__ in _CONNECTION_ERROR_NAMES:
            return True
        for link in (getattr(current, "reason", None), current.__cause__, current.__context__):
            if isinstance(link, BaseException):
                pending.append(link)
    return False


def create_workflow_attachment_asset(
    *,
    execution_id: str,
    attachment_id: str,
    filename: str,
    content_bytes: bytes,
    mime_type: str,
    source_node_id: str = "",
    flow_id: str = "",
    created_by: str = "",
) -> WorkflowAttachmentAsset:
    if not execution_id:
        raise ValueError("execution_id 不能为空")
    if not attachment_id:
        raise ValueError("attachment_id 不能为空")

    existing_asset = WorkflowAttachmentAsset.objects.filter(execution_id=execution_id, attachment_id=attachment_id).first()
    previous_file_name = existing_asset.file.name if (existing_asset and existing_asset.file) else None
    try:
        saved_name = _upload_workflow_attachment_bytes(filename=filename, content_bytes=content_bytes, mime_type=mime_type)
        asset, _ = WorkflowAttachmentAsset.objects.update_or_create(
            execution_id=execution_id,
            attachment_id=attachment_id,
            defaults={
                "flow_id": flow_id,
                "source_node_id": source_node_id,
                "filename": filename,
                "mime_type": mime_type,
                "file": saved_name,
                "created_by": str(created_by or ""),
            },
        )
    except Exception as exc:
        if _is_minio_connection_error(exc):
            raise ValueError(MINIO_CONNECTION_FAILURE_MESSAGE) from exc
        raise
    # 替换了文件时清理旧的 MinIO 对象，避免遗留孤儿文件
    if previous_file_name and previous_file_name != asset.file.name:
        asset.file.storage.delete(previous_file_name)
    return asset


def build_workflow_attachment_id(*, execution_id: str, source_node_id: str = "", requested_attachment_id: str = "") -> str:
    normalized_attachment_id = str(requested_attachment_id or "").strip()
    if normalized_attachment_id:
        return normalized_attachment_id

    normalized_node_id = str(source_node_id or "").strip()
    if not execution_id or not normalized_node_id:
        return uuid4().hex[:12]

    existing_ids = set(
        WorkflowAttachmentAsset.objects.filter(execution_id=execution_id, source_node_id=normalized_node_id).values_list("attachment_id", flat=True)
    )
    if normalized_node_id not in existing_ids:
        return normalized_node_id

    suffix = 1
    while True:
        candidate = f"{normalized_node_id}__{suffix}"
        if candidate not in existing_ids:
            return candidate
        suffix += 1


def cleanup_expired_workflow_attachments(*, retention_days: int = 3) -> int:
    expire_before = timezone.now() - timedelta(days=retention_days)
    expired_assets = WorkflowAttachmentAsset.objects.filter(created_at__lt=expire_before)
    deleted_count = 0

    for asset in expired_assets.iterator():
        # 先删 MinIO 上的文件对象，再删数据库记录，避免遗留孤儿文件
        if asset.file:
            asset.file.delete(save=False)
        asset.delete()
        deleted_count += 1

    return deleted_count


def _build_csv_bytes(content: str) -> bytes:
    return (content or "").lstrip("\ufeff").encode("utf-8-sig")


_PPT_CALLOUT_TITLES = frozenset({"核心结论", "执行摘要", "决议"})
_PPT_COVER_LINES = 4
_PPT_BODY_LINES = 4
_PPT_CARD_LIMIT = 4
_PPT_METRIC_RE = re.compile(
    r"^(?P<value>\d+(?:\.\d+)?%?)"
    r"(?:\s*(?P<unit>条|个|次|人|台|分钟|小时|天))?"
    r"\s*(?P<label>[^，,。；;]{0,18})"
    r"(?:[，,。；;]\s*(?P<note>.*))?$"
)
_PPT_INLINE_COUNT_RE = re.compile(r"(?:^|[，,、;；\s])(?P<label>[\u4e00-\u9fffA-Za-z]{1,8})\s*(?P<value>\d+)\s*(?P<unit>条|个|次|台|人|分钟|小时|天)")
_PPT_DIST_RE = re.compile(r"^(?P<label>.{1,48}?)[：:]\s*(?P<value>\d+)\s*(?P<unit>条|个|次|台|人)?\s*(?P<note>.*)$")
_PPT_RECORD_ID_RE = re.compile(r"^(?P<id>[A-Za-z][A-Za-z0-9_-]{2,})[：:]\s*(?P<body>.+)$")
_PPT_VALUE_UNIT_RE = re.compile(r"^(?P<value>\d+)\s*(?P<unit>条|个|次|台|人|分钟|小时|天)")
_PPT_META_LABEL_RE = re.compile(r"([\u4e00-\u9fff]{2,10})：")
_PPT_CLAUSE_LABEL_RE = re.compile(r"(?:^|(?<=\s))([\u4e00-\u9fff]{2,12})：")
_PPT_LABEL_STOP = frozenset({"涉及", "均为", "其中", "约", "共", "有", "达", "为", "的", "均"})
_PPT_STATUS_WORDS = frozenset({"处理中", "待响应", "未分派", "已关闭", "已恢复", "已解决", "自动恢复", "自动关闭"})
_PPT_FIELD_PREFIXES = ("资源", "处理人", "负责人", "等级", "来源", "状态", "主机")


def _normalize_pptx_markdown(content: str) -> str:
    """模型有时把换行写成字面量 \\n，或把标题写成 #标题、1、。先收成能解析的 Markdown。"""
    text = content or ""
    if text.count("\n") < 2 and "\\n" in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^(#{1,6})([^\s#])", r"\1 \2", text)
    return re.sub(r"(?m)^(\d+)、[ \t]*", r"\1. ", text)


def _run_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return _inline_text(value).strip()


def _as_runs(value) -> list:
    if isinstance(value, str):
        return [_TextRun(value)] if value.strip() else []
    return [run for run in (value or []) if getattr(run, "text", "")]


def _blank_slide(title: str, role: str) -> dict:
    return {"role": role, "title": title, "lines": [], "table": None, "header": False, "metrics": None, "cards": None, "note": None}


def _metric_parts(text: str) -> dict | None:
    if not text or len(text) > 80:
        return None
    match = _PPT_METRIC_RE.match(text.strip())
    if match is None:
        return None
    value = match.group("value")
    digits = value[:-1] if value.endswith("%") else value
    if "." not in digits and not value.endswith("%") and len(digits) > 3:
        return None
    label = (match.group("label") or "").strip()
    unit = match.group("unit") or ""
    if not label and not unit:
        return None
    return {"value": value, "unit": unit, "label": label, "note": (match.group("note") or "").strip()}


def _card_parts(runs) -> dict | None:
    text = _run_text(runs)
    bold = "".join(run.text for run in _as_runs(runs) if getattr(run, "bold", False)).strip()
    rest = "".join(run.text for run in _as_runs(runs) if not getattr(run, "bold", False)).strip(" ：:;")
    if bold and rest and len(bold) <= 24:
        return {"title": bold, "body": rest}
    if "：" in text:
        title, body = text.split("：", 1)
        if 1 <= len(title.strip()) <= 24 and body.strip():
            return {"title": title.strip(), "body": body.strip()}
    return None


def _block_bits(block) -> list[str]:
    kind = block[0]
    if kind == "paragraph":
        text = _run_text(block[1])
        return [text] if text else []
    if kind in {"ul", "ol"}:
        return [text for item in block[1] if (text := _run_text(item))]
    if kind == "code":
        return [str(block[1]).strip()] if str(block[1]).strip() else []
    if kind == "heading":
        text = _run_text(block[2])
        return [text] if text else []
    return []


def _h3_cards(blocks) -> tuple[list[str], list[dict]] | None:
    headings = [block for block in blocks if block[0] == "heading" and block[1] >= 3]
    if len(headings) < 2 or any(block[0] == "table" for block in blocks):
        return None
    intro: list[str] = []
    cards: list[dict] = []
    current: dict | None = None
    for block in blocks:
        if block[0] == "heading" and block[1] >= 3:
            current = {"kicker": f"{len(cards) + 1:02d}", "title": _run_text(block[2]), "body": []}
            cards.append(current)
            continue
        bits = _block_bits(block)
        if current is None:
            intro.extend(bits)
        else:
            current["body"].extend(bits)
    for card in cards:
        card["body"] = "\n".join(card["body"])
    return intro, cards


def _metric_list(blocks) -> tuple[list, list[dict], list] | None:
    if any(block[0] in {"table", "heading"} for block in blocks):
        return None
    lists = [block for block in blocks if block[0] in {"ul", "ol"}]
    if len(lists) != 1 or not 2 <= len(lists[0][1]) <= 4:
        return None
    metrics = []
    for item in lists[0][1]:
        parts = _metric_parts(_run_text(item))
        if parts is None:
            return None
        metrics.append(parts)
    before: list = []
    after: list = []
    seen = False
    for block in blocks:
        if block[0] in {"ul", "ol"}:
            seen = True
            continue
        if block[0] == "code":
            runs = _as_runs(str(block[1]))
        elif block[0] == "paragraph":
            runs = _as_runs(block[1])
        else:
            continue
        if not runs:
            continue
        if seen:
            after.append(runs)
        else:
            before.append(runs)
    return before, metrics, after


def _ordered_cards(blocks) -> list[dict] | None:
    if any(block[0] in {"table", "heading", "ul"} for block in blocks):
        return None
    lists = [block for block in blocks if block[0] == "ol"]
    if len(lists) != 1 or not 2 <= len(lists[0][1]) <= 6:
        return None
    cards = []
    for item in lists[0][1]:
        parts = _card_parts(item)
        if parts is None:
            return None
        cards.append({"kicker": f"{len(cards) + 1:02d}", "title": parts["title"], "body": parts["body"]})
    return cards


def _card_slides(title: str, intro: list[str], cards: list[dict]) -> list[dict]:
    slides = []
    for start in range(0, len(cards), _PPT_CARD_LIMIT):
        chunk = cards[start : start + _PPT_CARD_LIMIT]
        slide = _blank_slide(title, "cards")
        if start == 0 and intro:
            slide["lines"] = [[_TextRun(line)] for line in intro if line]
        slide["cards"] = chunk
        slides.append(slide)
    return slides


def _append_run_line(pending: list, value) -> None:
    runs = _as_runs(value)
    if runs:
        pending.append(runs)


def _content_pieces(blocks) -> list[tuple]:
    """按出现顺序交出正文行或表格。没有分隔行的竖线文本也收成表。"""
    pending: list = []
    pieces: list[tuple] = []

    def flush() -> None:
        if pending:
            pieces.extend(_partition_run_lines(pending))
            pending.clear()

    for block in blocks:
        kind = block[0]
        if kind == "table":
            flush()
            header = [_run_text(cell) for cell in block[1]]
            width = len(header)
            rows = [header]
            for row in block[2]:
                cells = [_run_text(cell) for cell in row]
                rows.append(cells[:width] + [""] * max(0, width - len(cells)))
            pieces.append(("table", rows, True))
            continue
        if kind == "heading":
            _append_run_line(pending, block[2])
        elif kind in {"ul", "ol"}:
            for item in block[1]:
                _append_run_line(pending, item)
        elif kind == "paragraph":
            _append_run_line(pending, block[1])
        elif kind == "code":
            _append_run_line(pending, str(block[1]))
    flush()
    return pieces


def _partition_run_lines(lines: list) -> list[tuple]:
    pieces = []
    text: list = []

    def flush() -> None:
        if text:
            pieces.append(("lines", text[:], False))
            text.clear()

    index = 0
    while index < len(lines):
        row = _pipe_row(_run_text(lines[index]))
        if row is None:
            text.append(lines[index])
            index += 1
            continue
        width = len(row)
        rows = []
        while index < len(lines):
            nxt = _pipe_row(_run_text(lines[index]))
            if nxt is None or len(nxt) != width:
                break
            rows.append(nxt)
            index += 1
        if len(rows) >= 2:
            flush()
            pieces.append(("table", rows, False))
        else:
            text.append([_TextRun(" | ".join(rows[0]))])
    flush()
    return pieces


def _line_slides(title: str, pieces: list[tuple], *, cover: bool) -> list[dict]:
    slides = []
    first = True
    index = 0
    while index < len(pieces):
        kind, payload, has_header = pieces[index][:3]
        if kind == "lines":
            pending = payload
            while pending:
                role = "cover" if cover and first else "callout" if title in _PPT_CALLOUT_TITLES else "points"
                limit = _PPT_COVER_LINES if role == "cover" else _PPT_BODY_LINES
                chunk = pending[:limit]
                pending = pending[limit:]
                # 表格前的一两句说明留在表格页，避免单独占一页空白。
                if not pending and index + 1 < len(pieces) and pieces[index + 1][0] == "table" and len(chunk) <= 2 and role != "cover":
                    pieces[index + 1] = (pieces[index + 1][0], pieces[index + 1][1], pieces[index + 1][2], chunk)
                    first = False
                    break
                slide = _blank_slide(title, role)
                slide["lines"] = chunk
                slides.append(slide)
                first = False
            index += 1
            continue
        rows = payload
        head = rows[:1] if has_header else []
        body = rows[1:] if has_header else rows
        headline = pieces[index][3] if len(pieces[index]) > 3 else []
        chunks = [body[start : start + 7] for start in range(0, len(body), 7)] or [[]]
        for chunk_index, chunk in enumerate(chunks):
            slide = _blank_slide(title, "points")
            slide["table"] = head + chunk
            slide["header"] = has_header and bool(head)
            if chunk_index == 0:
                slide["lines"] = headline
            slides.append(slide)
        first = False
        index += 1
    if not slides:
        role = "cover" if cover else "callout" if title in _PPT_CALLOUT_TITLES else "points"
        slides.append(_blank_slide(title, role))
    return slides


def _section_bullets(blocks) -> list[str]:
    items = []
    for block in blocks:
        if block[0] in {"ul", "ol"}:
            items.extend(text for item in block[1] if (text := _run_text(item)))
    return items


def _label_after_count(tail: str) -> str:
    text = tail.strip(" ，,、的")
    if text.startswith("不同"):
        text = text[2:]
    return text[:6]


def _distribution_metrics(items: list[str]) -> list[dict] | None:
    if not 2 <= len(items) <= 6:
        return None
    metrics = []
    for item in items:
        match = _PPT_DIST_RE.match(item.strip())
        if match is None:
            return None
        note = (match.group("note") or "").strip().strip("（）()")
        metrics.append(
            {
                "value": match.group("value"),
                "unit": match.group("unit") or "",
                "label": match.group("label").strip(),
                "note": note[:40],
            }
        )
    return metrics


def _inline_facts(items: list[str]) -> tuple[list[dict], list[str]]:
    metrics = []
    notes = []
    hits = 0
    for item in items:
        found = list(_PPT_INLINE_COUNT_RE.finditer(item))
        if not found:
            notes.append(item)
            continue
        hits += 1
        taken = False
        for index, match in enumerate(found):
            if len(metrics) >= 5:
                leftover = item if not taken else item[match.start() :]
                leftover = leftover.strip(" ，,、")
                if leftover:
                    notes.append(leftover)
                break
            taken = True
            label = match.group("label")
            end = found[index + 1].start() if index + 1 < len(found) else len(item)
            tail = item[match.end() : end].strip(" ，,、")
            if label in _PPT_LABEL_STOP:
                label = _label_after_count(tail) or label
                tail = ""
            metrics.append({"value": match.group("value"), "unit": match.group("unit"), "label": label, "note": tail[:36]})
    if hits < 2 or len(metrics) < 2:
        return [], []
    if len(metrics) >= 5:
        extras = [item["note"] for item in metrics if item["note"]]
        for item in metrics:
            item["note"] = ""
        notes = [*extras, *notes]
    if len(notes) > 1:
        notes = ["；".join(note for note in notes if note)]
    return metrics, notes[:1]


def _named_field(segment: str) -> tuple[str, str] | None:
    for prefix in _PPT_FIELD_PREFIXES:
        if segment.startswith(prefix):
            value = segment[len(prefix) :].strip(" ：:")
            name = "资源" if prefix == "主机" else prefix
            return name, value or "无"
    return None


def _record_table(items: list[str]) -> list[list[str]] | None:
    parsed = []
    for item in items:
        match = _PPT_RECORD_ID_RE.match(item.strip())
        if match is None:
            return None
        segments = [part.strip() for part in re.split(r"[，,]", match.group("body")) if part.strip()]
        if not segments:
            return None
        parsed.append((match.group("id"), segments))
    if len(parsed) < 2:
        return None
    extras: list[str] = []
    built = []
    for record_id, segments in parsed:
        content = segments[0]
        fields: dict[str, str] = {}
        rest = []
        for segment in segments[1:]:
            named = _named_field(segment)
            if named is not None:
                name, value = named
            elif segment in _PPT_STATUS_WORDS:
                name, value = "状态", segment
            elif segment.startswith("无处理人"):
                name, value = "处理人", "无"
            else:
                rest.append(segment)
                continue
            if name not in extras:
                extras.append(name)
            fields[name] = value
        if rest:
            content = content + "，" + "，".join(rest)
        built.append((record_id, content, fields))
    header = ["编号", "内容", *extras]
    rows = [header]
    for record_id, content, fields in built:
        rows.append([record_id, content, *[fields.get(name, "") for name in extras]])
    return rows


def _insight_cards(items: list[str]) -> list[dict] | None:
    if not 2 <= len(items) <= 6:
        return None
    cards = []
    for item in items:
        title, body = item, ""
        if "，" in item and len(item.split("，", 1)[0]) <= 28:
            title, body = item.split("，", 1)
        cards.append({"kicker": f"{len(cards) + 1:02d}", "title": title.strip(), "body": body.strip()})
    return cards


def _meta_pairs(text: str) -> list[tuple[str, str]] | None:
    matches = list(_PPT_META_LABEL_RE.finditer(text))
    if len(matches) < 2 or text[: matches[0].start()].strip():
        return None
    pairs = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end() : end].strip()
        if not value:
            return None
        pairs.append((match.group(1), value))
    return pairs


def _decorate_cover(slide: dict) -> None:
    if slide["role"] != "cover" or slide.get("metrics"):
        return
    meta = []
    metrics = []
    for line in slide["lines"]:
        pairs = _meta_pairs(_run_text(line))
        if not pairs:
            meta.append(line)
            continue
        for label, value in pairs:
            found = _PPT_VALUE_UNIT_RE.match(value)
            if found is not None:
                metrics.append({"value": found.group("value"), "unit": found.group("unit"), "label": label, "note": ""})
            else:
                meta.append([_TextRun(f"{label}：{value}")])
    if not metrics and len(meta) == len(slide["lines"]):
        return
    slide["lines"] = meta
    if metrics:
        slide["metrics"] = metrics[:4]


def _clause_pairs(text: str) -> list[tuple[str, str]] | None:
    source = text.strip()
    matches = list(_PPT_CLAUSE_LABEL_RE.finditer(source))
    if not matches or source[: matches[0].start()].strip():
        return None
    pairs = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        body = source[match.end() : end].strip(" ，,、")
        if not body:
            return None
        pairs.append((match.group(1), body))
    return pairs


def _clause_cards(blocks) -> list[dict] | None:
    texts = []
    for block in blocks:
        texts.extend(_block_bits(block))
    if not texts:
        return None
    cards = []
    for text in texts:
        pairs = _clause_pairs(text)
        if not pairs:
            return None
        for label, body in pairs:
            cards.append({"kicker": f"{len(cards) + 1:02d}", "title": label, "body": body})
    if not 2 <= len(cards) <= 12:
        return None
    return cards


def _metrics_slide(title: str, metrics: list[dict], note: str = "") -> dict:
    slide = _blank_slide(title, "metrics")
    slide["metrics"] = metrics
    if note:
        slide["note"] = [_TextRun(note)]
    return slide


def _prose_lines(blocks) -> list[str]:
    lines = []
    for block in blocks:
        if block[0] in {"ul", "ol"}:
            continue
        lines.extend(bit for bit in _block_bits(block) if bit)
    return lines


def _text_lines(texts: list[str]) -> list:
    return [[_TextRun(text)] for text in texts if text]


def _single_note(notes: list):
    texts = [_run_text(note) for note in notes]
    texts = [text for text in texts if text]
    if not texts:
        return None
    if len(notes) == 1:
        return notes[0]
    return [_TextRun("；".join(texts))]


def _section_to_slides(section: dict, *, cover: bool) -> list[dict]:
    title = section["title"]
    blocks = section["blocks"]
    grouped = _h3_cards(blocks)
    if grouped is not None:
        return _card_slides(title, grouped[0], grouped[1])
    bullets = _section_bullets(blocks)
    if title in _PPT_CALLOUT_TITLES:
        cards = _insight_cards(bullets)
        if cards is not None:
            return _card_slides(title, _prose_lines(blocks), cards)
        return _line_slides(title, _content_pieces(blocks), cover=cover)
    metrics = _metric_list(blocks)
    if metrics is not None:
        headline, items, note = metrics
        slides = []
        if cover and headline:
            cover_slide = _blank_slide(title, "cover")
            cover_slide["lines"] = headline
            slides.append(cover_slide)
            headline = []
        slide = _blank_slide(title, "metrics")
        slide["lines"] = headline
        slide["metrics"] = items
        slide["note"] = _single_note(note)
        slides.append(slide)
        return slides
    cards = _ordered_cards(blocks)
    if cards is not None:
        return _card_slides(title, _prose_lines(blocks), cards)
    records = _record_table(bullets)
    if records is not None:
        slide = _blank_slide(title, "points")
        slide["table"] = records
        slide["header"] = True
        slide["lines"] = _text_lines(_prose_lines(blocks))
        return [slide]
    distributed = _distribution_metrics(bullets)
    if distributed is not None:
        slide = _metrics_slide(title, distributed)
        slide["lines"] = _text_lines(_prose_lines(blocks))
        return [slide]
    facts, notes = _inline_facts(bullets)
    if facts:
        slide = _metrics_slide(title, facts, notes[0] if notes else "")
        slide["lines"] = _text_lines(_prose_lines(blocks))
        return [slide]
    if not cover:
        clauses = _clause_cards(blocks)
        if clauses is not None:
            return _card_slides(title, [], clauses)
    slides = _line_slides(title, _content_pieces(blocks), cover=cover)
    if cover:
        for slide in slides:
            if slide["role"] == "cover":
                _decorate_cover(slide)
                break
    return slides


def _pptx_slides(content: str, title: str) -> list[dict]:
    """一、二级标题分页。数字列表成指标卡，三级标题和加粗有序列表成并排卡片，表格成表。"""
    content = _normalize_pptx_markdown(content)
    sections: list[dict] = []
    current: dict | None = None

    def start(slide_title: str) -> None:
        nonlocal current
        current = {"title": (slide_title or title or " ").strip() or " ", "blocks": []}
        sections.append(current)

    if _should_prefix_title(content, title):
        start(title)
    for block in _iter_markdown_blocks(content):
        if block[0] == "heading" and block[1] <= 2:
            start(_run_text(block[2]))
            continue
        if current is None:
            start(title)
        current["blocks"].append(block)
    if not sections:
        start(title)
    slides: list[dict] = []
    for index, section in enumerate(sections):
        slides.extend(_section_to_slides(section, cover=index == 0))
    return slides


def _pipe_row(line: str) -> list[str] | None:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 3 or not all(cells):
        return None
    return cells


def _apply_pptx_run_font(run, font_name: str = _FONT) -> None:
    from pptx.oxml.ns import qn

    run.font.name = font_name
    properties = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        element = properties.find(qn(tag))
        if element is None:
            element = properties.makeelement(qn(tag), {})
            properties.append(element)
        element.set("typeface", font_name)


def _pptx_paragraph(paragraph, *, before: int = 0, after: int = 0, line: float = 1.35) -> None:
    from pptx.util import Pt

    paragraph.space_before = Pt(before)
    paragraph.space_after = Pt(after)
    paragraph.line_spacing = line


def _pptx_run(paragraph, text: str, size: int, color: str, *, bold: bool = False) -> None:
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    _apply_pptx_run_font(run)


def _pptx_box(slide, left, top, width, height):
    shape = slide.shapes.add_textbox(left, top, width, height)
    shape.text_frame.word_wrap = True
    return shape.text_frame


def _pptx_bar(slide, left, top, width, height, color: str) -> None:
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE

    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(color)
    shape.line.fill.background()


def _pptx_table(slide, rows: list[list[str]], has_header: bool, *, top: float = 1.55) -> None:
    from pptx.dml.color import RGBColor
    from pptx.util import Emu, Inches, Pt

    column_count = max(len(row) for row in rows)
    padded = [row + [""] * (column_count - len(row)) for row in rows]
    table_width = Inches(12.4)
    shape = slide.shapes.add_table(len(padded), column_count, Inches(0.45), Inches(top), table_width, Inches(min(5.3, 0.46 * len(padded))))
    table = shape.table
    column_width = int(table_width / column_count)
    for index in range(column_count):
        table.columns[index].width = Emu(column_width)
    for row_index, row in enumerate(padded):
        header = has_header and row_index == 0
        for column_index, value in enumerate(row):
            cell = table.cell(row_index, column_index)
            cell.text = value
            cell.text_frame.word_wrap = True
            for paragraph in cell.text_frame.paragraphs:
                _pptx_paragraph(paragraph, line=1.2)
                for run in paragraph.runs:
                    run.font.size = Pt(12)
                    run.font.bold = header
                    run.font.color.rgb = RGBColor.from_string(_TITLE if header else _TEXT)
                    _apply_pptx_run_font(run)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(_HEADER_FILL if header else "FFFFFF")


def _pptx_lines(frame, lines, size: int, color: str, *, bullet: bool) -> None:
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        _pptx_paragraph(paragraph, after=10, line=1.4)
        runs = line if isinstance(line, list) else [_TextRun(str(line))]
        if bullet:
            _pptx_run(paragraph, "• ", size, color)
        for run in runs:
            if not getattr(run, "text", ""):
                continue
            _pptx_run(paragraph, run.text, size, color, bold=bool(getattr(run, "bold", False)))


def _pptx_metric_cards(slide, metrics, top: float, *, compact: bool = False) -> None:
    from pptx.util import Inches

    count = max(1, len(metrics))
    gap = 0.16
    width = (12.0 - gap * (count - 1)) / count
    if compact:
        width = min(width, 2.8)
    height = 1.7 if compact else 3.15
    number_size = 26 if compact or count >= 5 else 36
    for index, item in enumerate(metrics):
        left = 0.66 + index * (width + gap)
        _pptx_bar(slide, Inches(left), Inches(top), Inches(width), Inches(height), _TABLE_HEADER)
        frame = _pptx_box(slide, Inches(left + 0.14), Inches(top + 0.16), Inches(max(0.4, width - 0.28)), Inches(height - 0.28))
        _pptx_paragraph(frame.paragraphs[0], line=1.05)
        _pptx_run(frame.paragraphs[0], item["value"], number_size, _TITLE, bold=True)
        if item["unit"]:
            _pptx_run(frame.paragraphs[0], " " + item["unit"], 14 if compact else 16, _SECTION, bold=True)
        if item["label"]:
            label_size = 12 if len(item["label"]) > 16 else 14 if compact else 16
            label = frame.add_paragraph()
            _pptx_paragraph(label, before=6, line=1.25)
            _pptx_run(label, item["label"], label_size, _TEXT, bold=True)
        if item["note"] and not compact:
            note = frame.add_paragraph()
            _pptx_paragraph(note, before=6, line=1.45)
            _pptx_run(note, item["note"], 12, _MUTED)


def _pptx_info_cards(slide, cards, top: float) -> None:
    from pptx.util import Inches

    columns = 2 if len(cards) == 4 else len(cards)
    gap = 0.18
    width = (12.0 - gap * (columns - 1)) / columns
    height = 2.15 if len(cards) == 4 else 3.2
    for index, card in enumerate(cards):
        column = index % columns
        row = index // columns
        left = 0.66 + column * (width + gap)
        card_top = top + row * (height + gap)
        _pptx_bar(slide, Inches(left), Inches(card_top), Inches(width), Inches(height), _TABLE_HEADER)
        frame = _pptx_box(slide, Inches(left + 0.18), Inches(card_top + 0.16), Inches(width - 0.36), Inches(height - 0.28))
        _pptx_paragraph(frame.paragraphs[0], line=1.1)
        _pptx_run(frame.paragraphs[0], card["kicker"], 12, _SECTION, bold=True)
        title = frame.add_paragraph()
        _pptx_paragraph(title, before=8, line=1.25)
        _pptx_run(title, card["title"], 16, _TEXT, bold=True)
        for line in str(card["body"]).splitlines():
            if line.strip():
                body = frame.add_paragraph()
                _pptx_paragraph(body, before=6, line=1.45)
                _pptx_run(body, line.strip(), 13, _MUTED)


def _build_pptx_bytes(content: str, title: str) -> bytes:
    # 显著启动成本：python-pptx 仅在生成幻灯片时需要，不得随 Django setup 加载。
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Emu, Inches

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    blank = presentation.slide_layouts[6]
    slides = _pptx_slides(content, title)
    total = len(slides)
    for number, slide_data in enumerate(slides, start=1):
        slide = presentation.slides.add_slide(blank)
        role = slide_data["role"]
        if role == "callout":
            background = slide.background.fill
            background.solid()
            background.fore_color.rgb = RGBColor.from_string(_TABLE_HEADER)
            _pptx_bar(slide, Inches(0.7), Inches(1.15), Inches(11.9), Inches(5.5), "FFFFFF")
        elif role == "cover":
            _pptx_bar(slide, Emu(0), Emu(0), Inches(0.16), presentation.slide_height, _TITLE)
        else:
            _pptx_bar(slide, Emu(0), Emu(0), presentation.slide_width, Inches(0.1), _SECTION)
        cover_metrics = role == "cover" and bool(slide_data.get("metrics"))
        title_box = _pptx_box(
            slide,
            Inches(0.7),
            Inches(0.85 if cover_metrics else 1.9 if role == "cover" else 1.45 if role == "callout" else 0.4),
            Inches(11.6),
            Inches(0.9 if cover_metrics else 1.5 if role == "cover" else 0.8),
        )
        _pptx_run(
            title_box.paragraphs[0], slide_data["title"][:80], 40 if role == "cover" else 28, _TITLE if role != "callout" else _SECTION, bold=True
        )
        if role in {"points", "metrics", "cards"}:
            _pptx_bar(slide, Inches(0.7), Inches(1.25), Inches(2.2), Inches(0.04), _RULE)
        if role == "metrics" and slide_data["metrics"]:
            card_top = 1.55
            if slide_data["lines"]:
                line_count = len(slide_data["lines"])
                headline_height = 0.8 if line_count <= 1 else min(1.6, 0.4 * line_count)
                headline = _pptx_box(slide, Inches(0.7), Inches(1.4), Inches(11.6), Inches(headline_height))
                _pptx_lines(headline, slide_data["lines"], 20, _TEXT, bullet=False)
                card_top = 2.35 if line_count <= 1 else 1.4 + headline_height + 0.15
            _pptx_metric_cards(slide, slide_data["metrics"], card_top)
            if slide_data["note"]:
                note = _pptx_box(slide, Inches(0.7), Inches(6.4), Inches(9.2), Inches(0.5))
                _pptx_lines(note, [slide_data["note"]], 14, _MUTED, bullet=False)
        elif role == "cover" and slide_data.get("metrics"):
            _pptx_metric_cards(slide, slide_data["metrics"], 2.15, compact=True)
            if slide_data["lines"]:
                meta = _pptx_box(slide, Inches(0.7), Inches(4.2), Inches(11.4), Inches(2.4))
                _pptx_lines(meta, slide_data["lines"], 16, _MUTED, bullet=False)
        elif role == "cards" and slide_data["cards"]:
            card_top = 1.5
            if slide_data["lines"]:
                line_count = len(slide_data["lines"])
                intro_height = 0.55 if line_count <= 1 else min(1.3, 0.4 * line_count)
                intro = _pptx_box(slide, Inches(0.7), Inches(1.4), Inches(11.6), Inches(intro_height))
                _pptx_lines(intro, slide_data["lines"], 16, _MUTED, bullet=False)
                card_top = 2.05 if line_count <= 1 else 1.4 + intro_height + 0.1
            _pptx_info_cards(slide, slide_data["cards"], card_top)
        elif slide_data["table"]:
            table_top = 1.55
            if slide_data["lines"]:
                line_count = len(slide_data["lines"])
                headline_height = 0.7 if line_count <= 1 else min(1.4, 0.35 * line_count)
                headline = _pptx_box(slide, Inches(0.7), Inches(1.4), Inches(11.6), Inches(headline_height))
                _pptx_lines(headline, slide_data["lines"], 18, _TEXT, bullet=False)
                table_top = 2.2 if line_count <= 1 else 1.4 + headline_height + 0.1
            _pptx_table(slide, slide_data["table"], slide_data["header"], top=table_top)
        elif slide_data["lines"]:
            body = _pptx_box(
                slide,
                Inches(0.7 if role != "callout" else 1.0),
                Inches(3.6 if role == "cover" else 2.5 if role == "callout" else 1.7),
                Inches(11.4),
                Inches(3.2),
            )
            _pptx_lines(
                body,
                slide_data["lines"],
                20 if role == "cover" else 22 if role == "callout" else 20,
                _MUTED if role == "cover" else _TEXT,
                bullet=role != "cover",
            )
        if role != "cover":
            footer = _pptx_box(slide, Inches(10.4), Inches(7.05), Inches(2.3), Inches(0.3))
            footer.paragraphs[0].alignment = PP_ALIGN.RIGHT
            _pptx_run(footer.paragraphs[0], f"{number} / {total}", 12, _MUTED)
    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()
