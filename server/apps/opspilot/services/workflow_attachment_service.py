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


def _install_single_attempt_minio_client(storage) -> None:
    """django-minio-backend 会缓存 Minio 客户端，默认再重试 5 次。这里换成只连一次的连接池。"""
    pool = _minio_http_pool()
    storage.HTTP_CLIENT = pool
    for attr in ("_MinioBackend__CLIENT", "_MinioBackend__CLIENT_EXT"):
        client = getattr(storage, attr, None)
        if client is not None and getattr(client, "_http", None) is not pool:
            client._http = pool


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

    storage = WorkflowAttachmentAsset._meta.get_field("file").storage
    _install_single_attempt_minio_client(storage)
    existing_asset = WorkflowAttachmentAsset.objects.filter(execution_id=execution_id, attachment_id=attachment_id).first()
    previous_file_name = existing_asset.file.name if (existing_asset and existing_asset.file) else None
    try:
        asset, _ = WorkflowAttachmentAsset.objects.update_or_create(
            execution_id=execution_id,
            attachment_id=attachment_id,
            defaults={
                "flow_id": flow_id,
                "source_node_id": source_node_id,
                "filename": filename,
                "mime_type": mime_type,
                "file": ContentFile(content_bytes, name=filename),
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


def _block_text(value) -> str:
    if isinstance(value, str):
        return value
    return _inline_text(value)


def _pptx_slides(content: str, title: str) -> list[dict]:
    """一级、二级标题各成一页；列表、段落和表格行放进当前页。"""
    slides: list[dict] = []
    current: dict | None = None

    def start(slide_title: str) -> None:
        nonlocal current
        current = {"title": (slide_title or title or " ").strip() or " ", "bullets": []}
        slides.append(current)

    if _should_prefix_title(content, title):
        start(title)
    for block in _iter_markdown_blocks(content):
        kind = block[0]
        if kind == "heading" and block[1] <= 2:
            start(_block_text(block[2]))
            continue
        if current is None:
            start(title)
        if kind == "heading":
            current["bullets"].append(_block_text(block[2]))
        elif kind in {"ul", "ol"}:
            current["bullets"].extend(_block_text(item) for item in block[1])
        elif kind == "paragraph":
            current["bullets"].append(_block_text(block[1]))
        elif kind == "code":
            current["bullets"].append(block[1])
        elif kind == "table":
            for row in block[2]:
                left = _block_text(row[0]) if row else ""
                right = _block_text(row[1]) if len(row) > 1 else ""
                current["bullets"].append(f"{left}：{right}" if right else left)
    if not slides:
        start(title)
    return slides


def _apply_pptx_run_font(run, font_name: str = "微软雅黑") -> None:
    from pptx.oxml.ns import qn

    run.font.name = font_name
    properties = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        element = properties.find(qn(tag))
        if element is None:
            element = properties.makeelement(qn(tag), {})
            properties.append(element)
        element.set("typeface", font_name)


def _build_pptx_bytes(content: str, title: str) -> bytes:
    # 显著启动成本：python-pptx 仅在生成幻灯片时需要，不得随 Django setup 加载。
    from pptx import Presentation

    presentation = Presentation()
    layout = presentation.slide_layouts[1]
    for slide_data in _pptx_slides(content, title):
        slide = presentation.slides.add_slide(layout)
        slide.shapes.title.text = slide_data["title"][:200]
        text_frame = slide.placeholders[1].text_frame
        bullets = slide_data["bullets"] or [""]
        text_frame.text = bullets[0][:1000]
        for paragraph in text_frame.paragraphs:
            for run in paragraph.runs:
                _apply_pptx_run_font(run)
        for item in bullets[1:]:
            paragraph = text_frame.add_paragraph()
            paragraph.text = item[:1000]
            paragraph.level = 0
            for run in paragraph.runs:
                _apply_pptx_run_font(run)
        if slide.shapes.title is not None:
            for paragraph in slide.shapes.title.text_frame.paragraphs:
                for run in paragraph.runs:
                    _apply_pptx_run_font(run)
    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()
