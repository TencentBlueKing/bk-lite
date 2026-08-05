"""Wiki Markdown import helpers."""

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

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

    @property
    def archive_path(self):
        return self.filename


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


def _safe_archive_path(value):
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("压缩包包含非法路径")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("压缩包包含绝对路径")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("压缩包包含路径穿越")
    return path.as_posix()


def _iter_markdown_files(content, filename):
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix in _MARKDOWN_EXTENSIONS:
        yield PurePosixPath(filename or "import.md").name, content.decode("utf-8")
        return
    if suffix != ".zip":
        raise ValueError("仅支持导入 Markdown 文件或 Markdown zip")

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        archive_paths = set()
        for info in archive.infolist():
            archive_path = _safe_archive_path(info.filename.rstrip("/"))
            identity = archive_path.casefold()
            if identity in archive_paths:
                raise ValueError("ZIP 存在大小写等价的重复路径")
            archive_paths.add(identity)
            if info.is_dir():
                continue
            if PurePosixPath(archive_path).suffix.lower() not in _MARKDOWN_EXTENSIONS:
                yield archive_path, None
                continue
            yield archive_path, archive.read(info).decode("utf-8")
