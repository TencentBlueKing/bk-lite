"""Export the active Wiki generation as an OKF v0.2 ZIP bundle."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import timezone as dt_timezone
from pathlib import PurePosixPath

import yaml
from django.utils import timezone

from apps.opspilot.services.wiki.active_generation_query_service import assert_read_scope_current, bind_read_scope, page_queryset, page_snapshot
from apps.opspilot.services.wiki.markdown_export_service import DEFAULT_MAX_EXPORT_PAGES, QuotaExceededError, safe_markdown_filename
from apps.opspilot.services.wiki.okf_import_service import (
    _INLINE_IMAGE_RE,
    _REF_DEF_RE,
    _iter_okf_body_segments,
    _split_markdown_destination,
    concept_id_from_archive_path,
    is_reserved_okf_path,
)
from apps.opspilot.services.wiki.parsed_media_service import _is_safe_media_locator, _normalize_media_locator, open_media_bytes
from apps.opspilot.services.wiki.relation_service import LINK_RE
from apps.opspilot.services.wiki.structure_service import UNCLASSIFIED_DIRECTORY_KEY
from apps.opspilot.services.wiki.title_service import title_identity_key

DEFAULT_MAX_OKF_EXPORT_BYTES = 200 * 1024 * 1024
OKF_EXPORT_VERSION = "0.2"
GENERATED_BY = "process:opspilot-llm-wiki/1"
_INTERNAL_OKF_KEYS = frozenset({"trust_tier", "concept_id", "okf_version"})
_CORE_OKF_KEYS = frozenset({"type", "title", "tags"})
_INVALID_SEGMENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE = re.compile(r"\s+")
_OKF_TAG_PREFIX = "okf:"
_ZIP_UTF8_FLAG = 0x800


class _ExportDumper(yaml.SafeDumper):
    pass


def _represent_str(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data))


_ExportDumper.add_representer(str, _represent_str)
_ExportDumper.add_representer(type(None), lambda dumper, _data: dumper.represent_scalar("tag:yaml.org,2002:null", "null"))


def posix_safe_segment(value):
    text = _INVALID_SEGMENT.sub("_", str(value or "").strip())
    text = _WHITESPACE.sub("_", text).strip("._")
    if text in {"", ".", ".."}:
        return "untitled"
    return text


def zip_root_name(knowledge_base_name):
    return f"{posix_safe_segment(knowledge_base_name)}-okf"


def posix_relpath(target, start):
    target_parts = PurePosixPath(str(target or "").replace("\\", "/")).parts
    start_parts = PurePosixPath(str(start or "").replace("\\", "/")).parts if start not in {"", "."} else ()
    index = 0
    while index < len(target_parts) and index < len(start_parts) and target_parts[index] == start_parts[index]:
        index += 1
    ups = ("..",) * (len(start_parts) - index)
    downs = target_parts[index:]
    if not ups and not downs:
        return "."
    return PurePosixPath(*ups, *downs).as_posix()


def _okf_meta(snapshot):
    version = snapshot.page_version
    meta = dict(getattr(version, "meta_snapshot", None) or {}) if version is not None else {}
    okf = meta.get("okf")
    return dict(okf) if isinstance(okf, dict) else {}, meta


def _is_okf_imported(meta):
    return meta.get("source") == "okf_import"


def _directory_export_parts(breadcrumb):
    parts = []
    for node in breadcrumb or ():
        if not isinstance(node, dict):
            continue
        if str(node.get("key") or "") == UNCLASSIFIED_DIRECTORY_KEY:
            continue
        segment = posix_safe_segment(node.get("name") or "")
        if segment and segment != "untitled":
            parts.append(segment)
        elif str(node.get("name") or "").strip():
            parts.append(segment)
    return parts


def _concept_id_for_snapshot(snapshot, okf, meta):
    raw = str(okf.get("concept_id") or "").strip()
    if raw:
        return concept_id_from_archive_path(raw)
    archive_path = str(meta.get("archive_path") or "").strip()
    if archive_path and PurePosixPath(archive_path).suffix.lower() in {".md", ".markdown"}:
        return concept_id_from_archive_path(archive_path)
    title = str(okf.get("title") or snapshot.title or "").strip() or "page"
    filename = safe_markdown_filename(title, snapshot.page_id)
    stem = concept_id_from_archive_path(filename)
    parts = _directory_export_parts(snapshot.directory_breadcrumb)
    return "/".join([*parts, stem]) if parts else stem


def _disambiguate_concept_id(concept_id, page_id, taken):
    candidate = concept_id or f"page-{page_id}"
    if is_reserved_okf_path(f"{PurePosixPath(candidate).name}.md"):
        candidate = f"{candidate}-{page_id}"
    if candidate not in taken:
        return candidate
    return f"{candidate}-{page_id}"


def _export_tags(okf, page_tags):
    raw = okf.get("tags")
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
    elif isinstance(raw, str):
        values = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        values = [str(item).strip() for item in (page_tags or []) if str(item).strip()]
    seen = set()
    tags = []
    for tag in values:
        if tag.casefold().startswith(_OKF_TAG_PREFIX):
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def _has_deprecated_tag(page_tags):
    return any(str(tag).strip().casefold() == "okf:deprecated" for tag in (page_tags or []))


def _version_timestamp(snapshot):
    version = snapshot.page_version
    value = getattr(version, "updated_at", None) or getattr(version, "created_at", None) or timezone.now()
    if timezone.is_aware(value):
        value = value.astimezone(dt_timezone.utc)
    elif timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone()).astimezone(dt_timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _synthesize_generated(snapshot):
    return {"by": GENERATED_BY, "at": _version_timestamp(snapshot)}


def _page_frontmatter(snapshot, okf, meta):
    data = {}
    data["type"] = str(okf.get("type") or snapshot.page_type or "concept").strip() or "concept"
    data["title"] = str(okf.get("title") or snapshot.title or "").strip()
    tags = _export_tags(okf, snapshot.tags)
    if tags:
        data["tags"] = tags
    for key, value in okf.items():
        name = str(key)
        if name in _CORE_OKF_KEYS or name in _INTERNAL_OKF_KEYS or name in data:
            continue
        if value is None:
            continue
        data[name] = value
    concept_id = str(okf.get("concept_id") or "").strip()
    if concept_id:
        data["concept_id"] = concept_id
    if "generated" not in data and not _is_okf_imported(meta) and not concept_id:
        data["generated"] = _synthesize_generated(snapshot)
    if "status" not in data and _has_deprecated_tag(snapshot.tags):
        data["status"] = "deprecated"
    return data


def _dump_frontmatter(mapping):
    dumped = yaml.dump(
        mapping,
        Dumper=_ExportDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10000,
    )
    return dumped.strip()


def _peel_description_blockquote(body, description):
    text = str(description or "").strip()
    content = body or ""
    if not text:
        return content
    stripped = content.lstrip("\n")
    prefix = f"> {text}"
    if not stripped.startswith(prefix):
        return content
    rest = stripped[len(prefix) :]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    if rest.startswith("\n"):
        rest = rest[1:]
    return rest


def _compose_markdown(frontmatter, body, title):
    content = _peel_description_blockquote(body or "", frontmatter.get("description"))
    content = content.strip("\n")
    if not content:
        content = f"# {title}"
    return f"---\n{_dump_frontmatter(frontmatter)}\n---\n\n{content}\n"


def _locator_from_destination(raw, knowledge_base_id):
    dest, _title = _split_markdown_destination(raw)
    dest = str(dest or "").split("#", 1)[0].strip()
    if not dest:
        return None
    locator = _normalize_media_locator(dest)
    if not locator.startswith("wiki/media/"):
        return None
    if not _is_safe_media_locator(locator, knowledge_base_id=knowledge_base_id):
        return None
    return locator


def _read_media_bytes(locator):
    try:
        handle, _content_type = open_media_bytes(locator)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    except Exception:
        return None
    try:
        with handle:
            payload = handle.read()
    except Exception:
        return None
    return payload or None


def _asset_name_for(digest, locator, taken):
    suffix = PurePosixPath(locator).suffix.casefold() or ".bin"
    if suffix == ".jpeg":
        suffix = ".jpg"
    elif suffix == ".tif":
        suffix = ".tiff"
    name = f"{digest[:16]}{suffix}"
    existing = taken.get(name)
    if existing and existing != digest:
        name = f"{digest}{suffix}"
    taken[name] = digest
    return name


def _rewrite_image_segment(segment, knowledge_base_id, href_by_locator):
    def replace_inline(match):
        dest, title = _split_markdown_destination(match.group(2))
        locator = _locator_from_destination(dest, knowledge_base_id)
        href = href_by_locator.get(locator or "")
        if not href:
            return match.group(0)
        suffix = f" {title}" if title else ""
        return f"![{match.group(1)}]({markdown_destination(href)}{suffix})"

    def replace_def(match):
        locator = _locator_from_destination(match.group(2), knowledge_base_id)
        href = href_by_locator.get(locator or "")
        if not href:
            return match.group(0)
        return match.group(0).replace(match.group(2), href, 1)

    updated = _INLINE_IMAGE_RE.sub(replace_inline, segment)
    return _REF_DEF_RE.sub(replace_def, updated)


def _rewrite_images(body, knowledge_base_id, href_by_locator):
    if not href_by_locator:
        return body or ""
    output = []
    for segment, in_code in _iter_okf_body_segments(body):
        output.append(segment if in_code else _rewrite_image_segment(segment, knowledge_base_id, href_by_locator))
    return "".join(output)


def _collect_markdown_locators(body, knowledge_base_id):
    locators = []
    seen = set()
    for segment, in_code in _iter_okf_body_segments(body):
        if in_code:
            continue
        destinations = [match.group(2) for match in _INLINE_IMAGE_RE.finditer(segment)]
        destinations.extend(match.group(2) for match in _REF_DEF_RE.finditer(segment))
        for dest in destinations:
            locator = _locator_from_destination(dest, knowledge_base_id)
            if not locator or locator in seen:
                continue
            seen.add(locator)
            locators.append(locator)
    return locators


def _rewrite_wikilink_segment(segment, titles_to_concept, stats):
    def replace(match):
        target = (match.group(1) or "").strip()
        label = match.group(2)
        concept_id = titles_to_concept.get(title_identity_key(target))
        if not concept_id:
            stats["unresolved"] += 1
            return match.group(0)
        text = (label if label is not None else target).strip() or target
        stats["rewritten"] += 1
        href = markdown_destination(f"/{concept_id}.md")
        return f"[{text}]({href})"

    return LINK_RE.sub(replace, segment)


def _rewrite_wikilinks(body, titles_to_concept):
    stats = {"rewritten": 0, "unresolved": 0}
    output = []
    for segment, in_code in _iter_okf_body_segments(body):
        if in_code:
            output.append(segment)
            continue
        output.append(_rewrite_wikilink_segment(segment, titles_to_concept, stats))
    return "".join(output), stats


def _title_lookup(entries):
    buckets = {}
    for entry in entries:
        keys = {title_identity_key(entry["title"])}
        original = str(entry["okf"].get("title") or "").strip()
        if original:
            keys.add(title_identity_key(original))
        for key in keys:
            buckets.setdefault(key, set()).add(entry["concept_id"])
    return {key: next(iter(ids)) for key, ids in buckets.items() if len(ids) == 1}


def _writestr(archive, name, data):
    payload = data.encode("utf-8") if isinstance(data, str) else data
    info = zipfile.ZipInfo(filename=str(name))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.flag_bits |= _ZIP_UTF8_FLAG
    archive.writestr(info, payload)
    written = archive.filelist[-1]
    written.flag_bits |= _ZIP_UTF8_FLAG


def _purpose_excerpt(text):
    text = str(text or "").strip()
    if not text:
        return ""
    return text[:500].rstrip()


def _one_line(text):
    return " ".join(str(text or "").split())


def markdown_destination(href):
    dest = str(href or "")
    if any(ch in dest for ch in "() \t"):
        return f"<{dest}>"
    return dest


def _export_log_date(exported_at):
    text = str(exported_at or "").strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text or "1970-01-01"


def _index_entry_line(entry):
    title = _one_line(entry.get("title") or entry.get("concept_id") or "untitled")
    href = markdown_destination(f"/{entry['concept_id']}.md")
    description = _one_line((entry.get("okf") or {}).get("description") or entry.get("description") or "")
    if description:
        return f"* [{title}]({href}) - {description}"
    return f"* [{title}]({href})"


def _group_index_entries(entries, directory_names):
    groups = {}
    seen = []
    for entry in entries:
        parts = PurePosixPath(entry["concept_id"]).parts
        heading = parts[0] if len(parts) >= 2 else ""
        if heading not in groups:
            groups[heading] = []
            seen.append(heading)
        groups[heading].append(entry)
    preferred = [name for name in directory_names if name in groups]
    remainder = [name for name in seen if name not in preferred]
    return [(name, groups[name]) for name in (*preferred, *remainder)]


def _index_markdown(knowledge_base, *, generation_id, exported_at, concept_count, directory_names, entries=()):
    lines = [
        "---",
        f'okf_version: "{OKF_EXPORT_VERSION}"',
        "---",
        "",
        f"# {knowledge_base.name}",
        "",
    ]
    excerpt = _purpose_excerpt(getattr(knowledge_base, "introduction", "") or "")
    if excerpt:
        lines.extend([excerpt, ""])
    for heading, items in _group_index_entries(entries, directory_names):
        lines.append(f"## {heading or '其他'}")
        lines.append("")
        lines.extend(_index_entry_line(item) for item in items)
        lines.append("")
    lines.extend(
        [
            f"导出时间: {exported_at}",
            f"generation: {generation_id if generation_id is not None else ''}",
            f"概念数: {concept_count}",
            "",
        ]
    )
    return "\n".join(lines)


def _log_markdown(knowledge_base, *, generation_id, exported_at, concept_count):
    generation = generation_id if generation_id is not None else ""
    return (
        "# Directory Update Log\n\n"
        f"## {_export_log_date(exported_at)}\n"
        f"* **Export**: exported {concept_count} concepts from {knowledge_base.name}"
        f" (generation {generation})\n"
    )


def _directory_display_names(structure):
    names = []
    seen = set()
    for node in (structure or {}).get("directories") or []:
        if not isinstance(node, dict):
            continue
        if str(node.get("key") or "") == UNCLASSIFIED_DIRECTORY_KEY:
            continue
        if str(node.get("status") or "active") != "active":
            continue
        name = str(node.get("name") or "").strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def build_okf_export_zip(knowledge_base, *, max_pages=None, max_bytes=None):
    page_limit = DEFAULT_MAX_EXPORT_PAGES if max_pages is None else int(max_pages)
    byte_limit = DEFAULT_MAX_OKF_EXPORT_BYTES if max_bytes is None else int(max_bytes)
    scope = bind_read_scope(knowledge_base)
    pages = list(page_queryset(knowledge_base, statuses=("active",), read_scope=scope).order_by("id"))
    if len(pages) > page_limit:
        raise QuotaExceededError(
            "max_pages",
            f"active 页面数 {len(pages)} 超过导出上限 {page_limit},请缩小范围或拆分导出",
        )

    root = zip_root_name(knowledge_base.name)
    exported_at = timezone.now().astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    entries = []
    taken = set()
    for page in pages:
        snapshot = page_snapshot(page, knowledge_base=knowledge_base)
        okf, meta = _okf_meta(snapshot)
        concept_id = _disambiguate_concept_id(
            _concept_id_for_snapshot(snapshot, okf, meta),
            snapshot.page_id,
            taken,
        )
        taken.add(concept_id)
        title = str(okf.get("title") or snapshot.title or "").strip()
        entries.append(
            {
                "snapshot": snapshot,
                "okf": okf,
                "meta": meta,
                "concept_id": concept_id,
                "title": title,
                "body": snapshot.body or "",
            }
        )

    titles_to_concept = _title_lookup(entries)
    assets = {}
    digest_to_name = {}
    name_to_digest = {}
    locator_to_name = {}
    missing_assets = 0
    unresolved_links = 0
    payloads = []

    for entry in entries:
        knowledge_base_id = knowledge_base.pk
        for locator in _collect_markdown_locators(entry["body"], knowledge_base_id):
            if locator in locator_to_name:
                continue
            payload = _read_media_bytes(locator)
            if payload is None:
                missing_assets += 1
                continue
            digest = hashlib.sha256(payload).hexdigest()
            name = digest_to_name.get(digest) or _asset_name_for(digest, locator, name_to_digest)
            digest_to_name[digest] = name
            assets[name] = payload
            locator_to_name[locator] = name

        href_by_locator = {}
        start = PurePosixPath(entry["concept_id"]).parent.as_posix()
        for locator, name in locator_to_name.items():
            href_by_locator[locator] = posix_relpath(f"assets/{name}", start)

        body, link_stats = _rewrite_wikilinks(entry["body"], titles_to_concept)
        unresolved_links += link_stats["unresolved"]
        body = _rewrite_images(body, knowledge_base_id, href_by_locator)
        frontmatter = _page_frontmatter(entry["snapshot"], entry["okf"], entry["meta"])
        markdown = _compose_markdown(frontmatter, body, entry["title"])
        payloads.append((f"{root}/{entry['concept_id']}.md", markdown))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _writestr(
            archive,
            f"{root}/index.md",
            _index_markdown(
                knowledge_base,
                generation_id=scope.generation_id,
                exported_at=exported_at,
                concept_count=len(entries),
                directory_names=_directory_display_names(scope.structure_snapshot),
                entries=entries,
            ),
        )
        _writestr(
            archive,
            f"{root}/log.md",
            _log_markdown(
                knowledge_base,
                generation_id=scope.generation_id,
                exported_at=exported_at,
                concept_count=len(entries),
            ),
        )
        for path, markdown in payloads:
            _writestr(archive, path, markdown)
        for name, payload in sorted(assets.items()):
            _writestr(archive, f"{root}/assets/{name}", payload)

    content = buffer.getvalue()
    if len(content) > byte_limit:
        raise QuotaExceededError(
            "max_bytes",
            f"导出内容超过 {byte_limit // (1024 * 1024)} MB 上限,已停止",
        )
    assert_read_scope_current(scope)
    stats = {
        "pages": len(entries),
        "images": len(assets),
        "missing_assets": missing_assets,
        "unresolved_links": unresolved_links,
    }
    return content, stats


__all__ = [
    "DEFAULT_MAX_OKF_EXPORT_BYTES",
    "OKF_EXPORT_VERSION",
    "build_okf_export_zip",
    "markdown_destination",
    "posix_relpath",
    "posix_safe_segment",
    "zip_root_name",
]
