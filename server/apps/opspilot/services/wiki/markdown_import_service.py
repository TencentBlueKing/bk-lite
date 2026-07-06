"""Wiki Markdown import helpers."""

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from django.db import transaction

from apps.opspilot.services.wiki.page_service import import_markdown_page

_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
_FRONT_MATTER_BOUNDARY = "---"
_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_NUMERIC_PREFIX_RE = re.compile(r"^\d+[-_]+")


@dataclass
class MarkdownDocument:
    filename: str
    title: str
    page_type: str
    body: str
    tags: list[str] = field(default_factory=list)
    original_id: str = ""


@dataclass
class MarkdownImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    pages: list[dict] = field(default_factory=list)

    @property
    def page_ids(self):
        return [page["id"] for page in self.pages]

    def as_dict(self):
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "pages": self.pages,
        }


def _parse_scalar(value):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip("'\"")


def _parse_front_matter(front_lines):
    metadata = {}
    current_list_key = ""
    for raw_line in front_lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if current_list_key and stripped.startswith("- "):
            metadata.setdefault(current_list_key, []).append(_parse_scalar(stripped[2:]))
            continue
        if ":" not in line:
            current_list_key = ""
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            metadata[key] = _parse_scalar(value)
            current_list_key = ""
        else:
            metadata[key] = []
            current_list_key = key
    return metadata


def _split_front_matter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_BOUNDARY:
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONT_MATTER_BOUNDARY:
            metadata = _parse_front_matter(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return metadata, body
    return {}, text


def _title_from_filename(filename):
    stem = PurePosixPath(filename).stem
    title = _NUMERIC_PREFIX_RE.sub("", stem).replace("_", " ").strip()
    return title or "未命名页面"


def _first_heading(body):
    match = _HEADING_RE.search(body or "")
    return match.group(1).strip() if match else ""


def _strip_leading_title_heading(body, title):
    lines = (body or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip() == f"# {title}".strip():
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def _coerce_tags(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def parse_markdown_document(filename, content):
    """Parse one Markdown document into a Wiki page import payload."""
    metadata, body = _split_front_matter(content)
    title = str(metadata.get("title") or _first_heading(body) or _title_from_filename(filename)).strip()
    page_type = str(metadata.get("page_type") or "concept").strip() or "concept"
    return MarkdownDocument(
        filename=filename,
        title=title,
        page_type=page_type,
        body=_strip_leading_title_heading(body, title),
        tags=_coerce_tags(metadata.get("tags")),
        original_id=str(metadata.get("id") or ""),
    )


def _iter_markdown_files(content, filename):
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix in _MARKDOWN_EXTENSIONS:
        yield PurePosixPath(filename or "import.md").name, content.decode("utf-8")
        return
    if suffix != ".zip":
        raise ValueError("仅支持导入 Markdown 文件或 Markdown zip")

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if PurePosixPath(name).suffix.lower() not in _MARKDOWN_EXTENSIONS:
                yield name, None
                continue
            yield name, archive.read(info).decode("utf-8")


@transaction.atomic
def import_markdown_archive(knowledge_base, content, filename="", operator=""):
    """Import .md or .zip Markdown content as Wiki pages."""
    result = MarkdownImportResult()
    for doc_filename, doc_content in _iter_markdown_files(content, filename):
        if doc_content is None:
            result.skipped += 1
            continue
        document = parse_markdown_document(doc_filename, doc_content)
        if not document.title:
            result.skipped += 1
            continue
        page, created = import_markdown_page(
            knowledge_base,
            page_type=document.page_type,
            title=document.title,
            body=document.body,
            tags=document.tags,
            operator=operator,
            source_meta={
                "type": "markdown_import",
                "filename": document.filename,
                "original_id": document.original_id,
            },
        )
        if created:
            result.created += 1
        else:
            result.updated += 1
        result.pages.append(
            {
                "id": page.id,
                "title": page.title,
                "page_type": page.page_type,
                "status": page.status,
                "action": "created" if created else "updated",
            }
        )
    return result
