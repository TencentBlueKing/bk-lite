"""Wiki Markdown export helpers."""

import io
import json
import re
import zipfile

from apps.opspilot.models import KnowledgePage

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE = re.compile(r"\s+")

# 企业治理配额:防止单次导出把整个 KB 灌满内存/网络。超限抛 QuotaExceededError,
# 由 viewset 捕获后返回 400 + 提示缩小范围或拆分。
DEFAULT_MAX_EXPORT_PAGES = 2000
DEFAULT_MAX_EXPORT_BYTES = 50 * 1024 * 1024  # 50 MB


class QuotaExceededError(ValueError):
    """导出配额超限异常。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def safe_markdown_filename(title, page_id):
    """Return a deterministic safe filename for a Wiki page."""
    safe_title = _INVALID_FILENAME_CHARS.sub("_", (title or "").strip())
    safe_title = _WHITESPACE.sub("_", safe_title).strip("._ ")
    if not safe_title:
        safe_title = "page"
    return f"{page_id}-{safe_title}.md"


def _yaml_string(value):
    return json.dumps(str(value or ""), ensure_ascii=False)


def render_page_markdown(page):
    """Render one KnowledgePage as portable Markdown with front matter."""
    body = page.current_version.body if page.current_version_id else ""
    tags = page.tags if isinstance(page.tags, list) else []
    front_matter = [
        "---",
        f"id: {page.id}",
        f"title: {_yaml_string(page.title)}",
        f"page_type: {_yaml_string(page.page_type)}",
        f"status: {_yaml_string(page.status)}",
        f"contribution: {_yaml_string(page.contribution)}",
        "tags:",
    ]
    front_matter.extend(f"  - {_yaml_string(tag)}" for tag in tags)
    front_matter.extend(["---", "", f"# {page.title}", "", body or ""])
    return "\n".join(front_matter).rstrip() + "\n"


def active_pages_for_export(knowledge_base):
    return KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version").order_by("id")


def build_markdown_export_zip(knowledge_base, *, max_pages=None, max_bytes=None):
    """Build a zip containing all active Wiki pages as Markdown files.

    Quota:超 max_pages 抛 QuotaExceededError("max_pages");超 max_bytes 抛
    "max_bytes"。两参数默认走 DEFAULT_MAX_EXPORT_PAGES / DEFAULT_MAX_EXPORT_BYTES。
    """
    page_limit = DEFAULT_MAX_EXPORT_PAGES if max_pages is None else max_pages
    byte_limit = DEFAULT_MAX_EXPORT_BYTES if max_bytes is None else max_bytes
    pages = list(active_pages_for_export(knowledge_base))
    if len(pages) > page_limit:
        raise QuotaExceededError(
            "max_pages",
            f"active 页面数 {len(pages)} 超过导出上限 {page_limit},请缩小范围或拆分导出",
        )
    buffer = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for page in pages:
            markdown = render_page_markdown(page)
            archive.writestr(
                f"pages/{safe_markdown_filename(page.title, page.id)}",
                markdown,
            )
            count += 1
            if buffer.tell() > byte_limit:
                raise QuotaExceededError(
                    "max_bytes",
                    f"导出内容超过 {byte_limit // (1024 * 1024)} MB 上限,已停止",
                )
    return buffer.getvalue(), count
