"""OKF v0.2 bundle parsing helpers for Wiki Markdown import."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree

import yaml

from apps.opspilot.services.wiki.markdown_import_service import _title_from_filename, split_front_matter_block
from apps.opspilot.services.wiki.title_service import title_identity_key, validate_display_title

OKF_IMPORT_FORMAT = "okf"
RESERVED_OKF_FILENAMES = frozenset({"index.md", "log.md"})
MARKDOWN_SUFFIXES = {".md", ".markdown"}
CONSUMED_FRONTMATTER_KEYS = frozenset({"type", "title", "tags"})
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_INLINE_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\n]+)\)")
_REF_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\[([^\]]*)\]")
_REF_DEF_RE = re.compile(
    r"^ {0,3}\[([^\]]+)\]:\s+(\S+)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*$",
    re.MULTILINE,
)
_HTML_IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_SVG_EVENT_RE = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
OKF_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff"}
OKF_IMAGE_MISSING_LIMIT = 50
_PAGE_MEDIA_OWNER = "pages"
_SUFFIX_CONTENT_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class OkfParseError(ValueError):
    def __init__(self, reason, message=""):
        self.reason = str(reason)
        super().__init__(message or self.reason)


def is_okf_import_format(value):
    return str(value or "").strip().casefold() == OKF_IMPORT_FORMAT


def is_reserved_okf_path(path):
    return PurePosixPath(path).name.casefold() in RESERVED_OKF_FILENAMES


def concept_id_from_archive_path(path):
    posix = PurePosixPath(str(path or "").replace("\\", "/"))
    if posix.suffix.lower() in MARKDOWN_SUFFIXES:
        posix = posix.with_suffix("")
    return posix.as_posix().strip("/")


def detect_bundle_root(paths):
    """Return the unique top-level directory to strip, or empty string."""
    members = [str(path or "").replace("\\", "/").strip("/") for path in paths if str(path or "").strip("/")]
    if not members:
        return ""
    tops = {PurePosixPath(path).parts[0] for path in members}
    if len(tops) != 1:
        return ""
    root = next(iter(tops))
    if not any(len(PurePosixPath(path).parts) > 1 for path in members):
        return ""
    if not any(PurePosixPath(path).suffix.lower() in MARKDOWN_SUFFIXES for path in members):
        return ""
    return root


def strip_bundle_root(path, bundle_root):
    posix = str(path or "").replace("\\", "/").strip("/")
    root = str(bundle_root or "").strip("/")
    if not root:
        return posix
    prefix = f"{root}/"
    if posix == root:
        return ""
    if posix.startswith(prefix):
        return posix[len(prefix) :]
    return posix


def coerce_okf_tags(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def coerce_verified(value):
    if value in (None, "", []):
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def derive_trust_tier(verified):
    events = coerce_verified(verified)
    if not events:
        return "unverified"
    for event in events:
        actor = str(event.get("by") or "")
        if actor.startswith("human:"):
            return "human_reviewed"
    return "machine_confirmed"


def map_okf_page_type(okf_type, page_types):
    original = str(okf_type or "").strip()
    lookup = {str(item).casefold(): str(item) for item in page_types or [] if str(item).strip()}
    matched = bool(original) and original.casefold() in lookup
    page_type = lookup.get(original.casefold(), "concept") if original else "concept"
    extra_tags = [] if matched else ([f"okf:{original}"] if original else [])
    return page_type, matched, extra_tags


def inject_description(body, description):
    text = str(description or "").strip()
    content = body or ""
    if not text:
        return content
    if text in content[:200]:
        return content
    prefix = f"> {text}"
    if not content.strip():
        return prefix
    return f"{prefix}\n\n{content}"


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def build_okf_meta(frontmatter, *, okf_version="", concept_id="", okf_type="", original_title="", trust_tier="unverified"):
    remainder = {str(key): _jsonable(value) for key, value in dict(frontmatter or {}).items() if key not in CONSUMED_FRONTMATTER_KEYS}
    remainder.update(
        {
            "okf_version": okf_version or "",
            "concept_id": concept_id,
            "type": okf_type,
            "title": original_title,
            "trust_tier": trust_tier,
        }
    )
    return remainder


def read_okf_version(text):
    raw, _body = split_front_matter_block(text)
    if raw is None:
        return ""
    try:
        loaded = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return ""
    if not isinstance(loaded, dict) or "okf_version" not in loaded:
        return ""
    value = loaded.get("okf_version")
    return "" if value is None else str(value).strip()


def parse_okf_document(path, text):
    """Parse one OKF concept document.

    Raises OkfParseError with reason ``yaml_invalid`` or ``type_missing``.
    """
    raw, body = split_front_matter_block(text)
    if raw is None:
        raise OkfParseError("yaml_invalid", "缺少 YAML frontmatter")
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise OkfParseError("yaml_invalid", "YAML frontmatter 无法解析") from error
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise OkfParseError("yaml_invalid", "YAML frontmatter 必须是 mapping")
    okf_type = str(loaded.get("type") or "").strip()
    if not okf_type:
        raise OkfParseError("type_missing", "缺少 type")
    title = str(loaded.get("title") or "").strip() or _title_from_filename(path)
    return {
        "archive_path": path,
        "concept_id": concept_id_from_archive_path(path),
        "title": title,
        "okf_original_title": title,
        "okf_type": okf_type,
        "description": str(loaded.get("description") or "").strip(),
        "tags": coerce_okf_tags(loaded.get("tags")),
        "body": body or "",
        "verified": coerce_verified(loaded.get("verified")),
        "okf_status": str(loaded.get("status") or "").strip(),
        "okf_frontmatter": _jsonable(loaded),
    }


def _disambiguate_suffix(archive_path, depth):
    parts = PurePosixPath(archive_path).parts[:-1]
    stem = PurePosixPath(archive_path).stem
    if not parts:
        return stem
    if depth <= len(parts):
        return "/".join(parts[-depth:])
    return "/".join((*parts, stem))


def disambiguate_okf_titles(items):
    """Return items with unique titles using parent-path suffixes.

    First occurrence of a title identity (archive_path sort order) keeps the
    original title; later collisions become ``Title (parent)``.
    """
    ordered = sorted(items, key=lambda item: str(item.get("archive_path") or ""))
    used = set()
    result_by_path = {}
    for item in ordered:
        archive_path = item["archive_path"]
        original = item["title"]
        title = original
        renamed_from = ""
        depth = 1
        max_depth = len(PurePosixPath(archive_path).parts) + 1
        while title_identity_key(title) in used:
            renamed_from = original
            suffix = _disambiguate_suffix(archive_path, depth)
            title = f"{original} ({suffix})"
            depth += 1
            if depth > max_depth + 2:
                title = f"{original} ({archive_path})"
                break
        used.add(title_identity_key(title))
        result_by_path[archive_path] = {
            "archive_path": archive_path,
            "title": title,
            "renamed_from": renamed_from,
        }
    return [result_by_path[item["archive_path"]] for item in ordered]


def _resolve_link_target(target, current_path):
    raw = str(target or "").strip()
    if not raw or raw.startswith("#"):
        return None
    if _SCHEME_RE.match(raw):
        return None
    path = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not path:
        return None
    if path.startswith("/"):
        resolved = PurePosixPath(path.lstrip("/"))
    else:
        resolved = PurePosixPath(current_path).parent / path
    parts = []
    for part in resolved.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    posix = PurePosixPath(*parts).as_posix() if parts else ""
    return concept_id_from_archive_path(posix)


def _rewrite_segment(segment, current_path, titles_by_concept_id, stats):
    def replace(match):
        text, target = match.group(1), match.group(2)
        concept_id = _resolve_link_target(target, current_path)
        if concept_id is None:
            return match.group(0)
        title = titles_by_concept_id.get(concept_id)
        if not title:
            stats["unresolved"] += 1
            return match.group(0)
        stats["rewritten"] += 1
        return f"[[{title}|{text}]]"

    return _LINK_RE.sub(replace, segment)


def _iter_okf_body_segments(body):
    lines = (body or "").splitlines(keepends=True)
    pending = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    def flush(in_code):
        segment = "".join(pending)
        pending.clear()
        return segment, in_code

    for line in lines:
        fence = _FENCE_RE.match(line.lstrip())
        if fence:
            marker = fence.group(1)
            if not in_fence:
                if pending:
                    yield flush(False)
                pending.append(line)
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
                continue
            remainder = line.strip().lstrip(fence_char)
            if marker[0] == fence_char and len(marker) >= fence_len and remainder == "":
                pending.append(line)
                yield flush(True)
                in_fence = False
                continue
        pending.append(line)
    if pending:
        yield flush(in_fence)


def rewrite_okf_links(body, current_path, titles_by_concept_id):
    stats = {"rewritten": 0, "unresolved": 0}
    output = []
    for segment, in_code in _iter_okf_body_segments(body):
        if in_code:
            output.append(segment)
            continue
        output.append(_rewrite_segment(segment, current_path, titles_by_concept_id, stats))
    return "".join(output), stats


def _split_markdown_destination(raw):
    text = str(raw or "").strip()
    title = ""
    if text.startswith("<") and ">" in text:
        closing = text.index(">")
        dest = text[1:closing].strip()
        rest = text[closing + 1 :].strip()
        if rest:
            title = rest
        return dest, title
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        return text, title
    for quote in ('"', "'"):
        padded = f" {quote}"
        index = text.find(padded)
        if index > 0:
            return text[:index].strip(), text[index:].strip()
    return text, title


def _decode_image_path(path):
    try:
        return unquote(path, errors="strict")
    except Exception:
        return path


def classify_okf_image_target(target, current_path):
    dest, _title = _split_markdown_destination(target)
    dest = dest.strip()
    if not dest or dest.startswith("#"):
        return {"skip": True}
    if dest.replace("\\", "/").startswith(("wiki/media/", "/wiki/media/", "./wiki/media/")):
        return {"skip": True}
    if _SCHEME_RE.match(dest):
        return {"skip": True}
    if "?" in dest.split("#", 1)[0]:
        return {"reason": "invalid_query", "target": dest, "image_path": ""}
    path = dest.split("#", 1)[0].strip().replace("\\", "/")
    path = _decode_image_path(path)
    if not path:
        return {"skip": True}
    resolved = _resolve_bundle_path(path, current_path)
    if resolved is None:
        return {"reason": "outside_bundle", "target": dest, "image_path": path}
    suffix = PurePosixPath(resolved).suffix.casefold()
    if suffix not in OKF_IMAGE_SUFFIXES:
        return {"reason": "not_image", "target": dest, "image_path": resolved}
    return {"reason": None, "target": dest, "image_path": resolved}


def _resolve_bundle_path(path, current_path):
    if path.startswith("/"):
        resolved = PurePosixPath(path.lstrip("/"))
    else:
        resolved = PurePosixPath(str(current_path or "").replace("\\", "/")).parent / path
    parts = []
    escaped = False
    for part in resolved.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                escaped = True
            continue
        parts.append(part)
    if escaped:
        return None
    return PurePosixPath(*parts).as_posix() if parts else ""


def validate_okf_image_bytes(data, suffix):
    payload = data or b""
    ext = str(suffix or "").casefold()
    if not payload:
        return "not_image", ""
    if ext == ".svg":
        return _validate_svg_bytes(payload)
    expected = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(ext)
    detected = _detect_raster_content_type(payload)
    if not expected or detected != expected:
        return "not_image", ""
    return None, expected


def _detect_raster_content_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "image/tiff"
    return ""


def _validate_svg_bytes(data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "not_image", ""
    lowered = text.casefold()
    if "<script" in lowered or "javascript:" in lowered or _SVG_EVENT_RE.search(text):
        return "not_image", ""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return "not_image", ""
    tag = root.tag.rsplit("}", 1)[-1]
    if tag.casefold() != "svg":
        return "not_image", ""
    return None, "image/svg+xml"


def page_media_locator(knowledge_base_id, digest, suffix):
    ext = str(suffix or "").casefold()
    if ext == ".jpeg":
        ext = ".jpg"
    elif ext == ".tif":
        ext = ".tiff"
    return f"wiki/media/{int(knowledge_base_id)}/{_PAGE_MEDIA_OWNER}/{digest}{ext}"


def collect_okf_image_refs(body, current_path):
    html_unchecked = 0
    refs = []
    for segment, in_code in _iter_okf_body_segments(body):
        if in_code:
            continue
        html_unchecked += len(_HTML_IMG_RE.findall(segment))
        definitions = {str(name).strip().casefold(): value for name, value in _REF_DEF_RE.findall(segment) if str(name).strip()}
        used_refs = set()
        for match in _REF_IMAGE_RE.finditer(segment):
            alt, ref_name = match.group(1), match.group(2)
            key = (ref_name or alt).strip().casefold()
            used_refs.add(key)
            dest = definitions.get(key)
            classified = classify_okf_image_target(dest, current_path) if dest else {"reason": "not_found", "image_path": "", "target": ""}
            if classified.get("skip"):
                continue
            refs.append(
                {
                    "kind": "definition",
                    "ref": key,
                    **classified,
                }
            )
        for match in _INLINE_IMAGE_RE.finditer(segment):
            classified = classify_okf_image_target(match.group(2), current_path)
            if classified.get("skip"):
                continue
            refs.append({"kind": "inline", **classified})
    return refs, html_unchecked


def rewrite_okf_images(body, current_path, locator_by_path):
    locators = {str(path).replace("\\", "/"): locator for path, locator in dict(locator_by_path or {}).items()}
    if not locators:
        return body or ""

    def rewrite_segment(segment):
        def replace_inline(match):
            dest, title = _split_markdown_destination(match.group(2))
            classified = classify_okf_image_target(dest, current_path)
            locator = locators.get(classified.get("image_path") or "")
            if not locator:
                return match.group(0)
            suffix = f" {title}" if title else ""
            return f"![{match.group(1)}]({locator}{suffix})"

        def replace_def(match):
            classified = classify_okf_image_target(match.group(2), current_path)
            locator = locators.get(classified.get("image_path") or "")
            if not locator:
                return match.group(0)
            return match.group(0).replace(match.group(2), locator, 1)

        updated = _INLINE_IMAGE_RE.sub(replace_inline, segment)
        return _REF_DEF_RE.sub(replace_def, updated)

    output = []
    for segment, in_code in _iter_okf_body_segments(body):
        output.append(segment if in_code else rewrite_segment(segment))
    return "".join(output)


def plan_okf_images(documents, *, knowledge_base_id, read_member):
    missing = []
    uploads = {}
    html_unchecked = 0
    pages_with_images = 0
    rewritten = []
    for document in documents:
        archive_path = document["archive_path"]
        body = document.get("body") or ""
        refs, html_count = collect_okf_image_refs(body, archive_path)
        html_unchecked += html_count
        locator_by_path = {}
        page_has_image = False
        for ref in refs:
            image_path = ref.get("image_path") or ""
            reason = ref.get("reason")
            if reason:
                missing.append({"archive_path": archive_path, "image_path": image_path or ref.get("target") or "", "reason": reason})
                continue
            key = image_path.casefold()
            if key in uploads:
                locator_by_path[image_path] = uploads[key]["locator"]
                page_has_image = True
                continue
            payload = read_member(image_path)
            if payload is None:
                missing.append({"archive_path": archive_path, "image_path": image_path, "reason": "not_found"})
                continue
            suffix = PurePosixPath(image_path).suffix
            invalid, content_type = validate_okf_image_bytes(payload, suffix)
            if invalid:
                missing.append({"archive_path": archive_path, "image_path": image_path, "reason": invalid})
                continue
            digest = hashlib.sha256(payload).hexdigest()
            locator = page_media_locator(knowledge_base_id, digest, suffix)
            uploads[key] = {
                "locator": locator,
                "relative": image_path,
                "content_type": content_type,
                "bytes": len(payload),
            }
            locator_by_path[image_path] = locator
            page_has_image = True
        if page_has_image:
            pages_with_images += 1
        rewritten.append({**document, "body": rewrite_okf_images(body, archive_path, locator_by_path)})
    unique = list(uploads.values())
    stats = {
        "count": len(unique),
        "bytes": sum(item["bytes"] for item in unique),
        "pages": pages_with_images,
        "html_unchecked": html_unchecked,
    }
    return (
        rewritten,
        stats,
        [{"locator": item["locator"], "relative": item["relative"], "content_type": item["content_type"]} for item in unique],
        missing,
    )


def bound_okf_image_missing(missing):
    items = list(missing or [])
    total = len(items)
    truncated = total > OKF_IMAGE_MISSING_LIMIT
    return {
        "missing": items[:OKF_IMAGE_MISSING_LIMIT],
        "truncated": truncated,
        "total": total,
    }


def _unique_tags(values):
    seen = set()
    result = []
    for item in values:
        tag = str(item).strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        result.append(tag)
    return result


def prepare_okf_documents(documents, *, page_types, okf_version="", canonical_title_fn=None):
    """Apply type mapping, title disambiguation, link rewrite, and description inject."""
    normalized = []
    for document in documents:
        title = document["title"]
        if canonical_title_fn is not None:
            title = canonical_title_fn(title)
        title = validate_display_title(title)
        normalized.append({**document, "title": title})

    disambiguated = disambiguate_okf_titles([{"archive_path": document["archive_path"], "title": document["title"]} for document in normalized])
    by_path = {item["archive_path"]: item for item in disambiguated}
    titles_by_concept_id = {document["concept_id"]: by_path[document["archive_path"]]["title"] for document in normalized}

    type_counts = {}
    prepared = []
    for document in normalized:
        item = by_path[document["archive_path"]]
        page_type, matched, extra_tags = map_okf_page_type(document["okf_type"], page_types)
        trust_tier = derive_trust_tier(document.get("verified"))
        tags = _unique_tags(
            [
                *(document.get("tags") or []),
                *extra_tags,
                f"okf:{trust_tier}",
            ]
        )
        if str(document.get("okf_status") or "").strip().casefold() == "deprecated":
            tags = _unique_tags([*tags, "okf:deprecated"])
        body, link_stats = rewrite_okf_links(
            document.get("body") or "",
            document["archive_path"],
            titles_by_concept_id,
        )
        body = inject_description(body, document.get("description") or "")
        key = (document["okf_type"], page_type, matched)
        type_counts[key] = type_counts.get(key, 0) + 1
        original_title = document.get("okf_original_title") or document["title"]
        prepared.append(
            {
                **document,
                "title": item["title"],
                "renamed_from": item.get("renamed_from") or "",
                "page_type": page_type,
                "tags": tags,
                "body": body,
                "okf_link_stats": link_stats,
                "okf_page_type_matched": matched,
                "okf_meta": build_okf_meta(
                    document.get("okf_frontmatter") or {},
                    okf_version=okf_version,
                    concept_id=document["concept_id"],
                    okf_type=document["okf_type"],
                    original_title=original_title,
                    trust_tier=trust_tier,
                ),
            }
        )

    type_mapping = [
        {
            "okf_type": okf_type,
            "page_type": page_type,
            "matched": matched,
            "count": count,
        }
        for (okf_type, page_type, matched), count in sorted(
            type_counts.items(),
            key=lambda item: (item[0][0].casefold(), item[0][1].casefold()),
        )
    ]
    stats = {
        "okf_version": okf_version or "",
        "type_mapping": type_mapping,
        "links": {
            "rewritten": sum(document["okf_link_stats"]["rewritten"] for document in prepared),
            "unresolved": sum(document["okf_link_stats"]["unresolved"] for document in prepared),
        },
        "renamed_count": sum(1 for document in prepared if document.get("renamed_from")),
    }
    return prepared, stats


__all__ = [
    "OKF_IMPORT_FORMAT",
    "OkfParseError",
    "build_okf_meta",
    "coerce_okf_tags",
    "coerce_verified",
    "concept_id_from_archive_path",
    "detect_bundle_root",
    "derive_trust_tier",
    "disambiguate_okf_titles",
    "inject_description",
    "is_okf_import_format",
    "is_reserved_okf_path",
    "map_okf_page_type",
    "parse_okf_document",
    "OKF_IMAGE_MISSING_LIMIT",
    "bound_okf_image_missing",
    "classify_okf_image_target",
    "collect_okf_image_refs",
    "page_media_locator",
    "plan_okf_images",
    "prepare_okf_documents",
    "read_okf_version",
    "rewrite_okf_images",
    "rewrite_okf_links",
    "strip_bundle_root",
    "validate_okf_image_bytes",
]
