"""Generation-consistent native Wiki archive export."""

import hashlib
import io
import json
import re
import zipfile

from apps.opspilot.models import WikiGeneration, WikiStructureRevision
from apps.opspilot.services.wiki.active_generation_query_service import assert_read_scope_current, bind_read_scope, page_queryset, page_snapshot
from apps.opspilot.services.wiki.generation_navigation_service import render_index_markdown, render_overview_markdown
from apps.opspilot.services.wiki.markdown_export_service import (
    DEFAULT_MAX_EXPORT_BYTES,
    DEFAULT_MAX_EXPORT_PAGES,
    QuotaExceededError,
    safe_markdown_filename,
)

NATIVE_ARCHIVE_FORMAT = "opspilot-wiki-native-v1"
_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _yaml_string(value):
    return json.dumps(str(value or ""), ensure_ascii=False)


def _directory_segment(key):
    value = _SAFE_KEY.sub("_", str(key or "")).strip("._")
    return value or "unclassified"


def _render_page(snapshot):
    front = [
        "---",
        f"id: {snapshot.page_id}",
        f"version_id: {snapshot.page_version_id or ''}",
        f"generation_id: {snapshot.generation_id or ''}",
        f"title: {_yaml_string(snapshot.title)}",
        f"page_type: {_yaml_string(snapshot.page_type)}",
        f"status: {_yaml_string(snapshot.page_status)}",
        f"contribution: {_yaml_string(snapshot.contribution)}",
        f"directory_key: {_yaml_string(snapshot.directory_key)}",
        f"directory_assignment_mode: {_yaml_string(snapshot.assignment_mode)}",
        "tags:",
    ]
    front.extend(f"  - {_yaml_string(tag)}" for tag in snapshot.tags)
    front.extend(["---", "", f"# {snapshot.title}", "", snapshot.body or ""])
    return ("\n".join(front).rstrip() + "\n").encode("utf-8")


def build_native_markdown_export_zip(knowledge_base, *, max_pages=None, max_bytes=None):
    page_limit = DEFAULT_MAX_EXPORT_PAGES if max_pages is None else int(max_pages)
    byte_limit = DEFAULT_MAX_EXPORT_BYTES if max_bytes is None else int(max_bytes)
    scope = bind_read_scope(knowledge_base)
    structure_fingerprint = ""
    if scope.structure_revision_id is not None:
        structure_fingerprint = (
            WikiStructureRevision.objects.filter(
                pk=scope.structure_revision_id,
                knowledge_base=knowledge_base,
            )
            .values_list("fingerprint", flat=True)
            .get()
        )
    pages = list(page_queryset(knowledge_base, statuses=("active",), read_scope=scope).order_by("id"))
    if len(pages) > page_limit:
        raise QuotaExceededError(
            "max_pages",
            f"active 页面数 {len(pages)} 超过导出上限 {page_limit},请缩小范围或拆分导出",
        )

    structure = scope.structure_snapshot or {"format_version": 1, "page_types": [], "directories": []}
    directories = structure.get("directories") or []
    page_entries = []
    page_payloads = []
    page_paths = {}
    for page in pages:
        snapshot = page_snapshot(page, knowledge_base=knowledge_base)
        payload = _render_page(snapshot)
        archive_path = f"pages/{_directory_segment(snapshot.directory_key)}/" f"{safe_markdown_filename(snapshot.title, snapshot.page_id)}"
        page_entries.append(
            {
                "page_id": snapshot.page_id,
                "page_version_id": snapshot.page_version_id,
                "title": snapshot.title,
                "page_type": snapshot.page_type,
                "tags": snapshot.tags,
                "contribution": snapshot.contribution,
                "directory_key": snapshot.directory_key,
                "directory_breadcrumb": list(snapshot.directory_breadcrumb),
                "directory_assignment_mode": snapshot.assignment_mode,
                "archive_path": archive_path,
                "content_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
        page_payloads.append((archive_path, payload))
        page_paths[snapshot.page_id] = archive_path

    navigation_payloads = []
    navigation_entries = []
    if scope.generation_id is not None:
        generation = WikiGeneration.objects.get(
            pk=scope.generation_id,
            knowledge_base=knowledge_base,
        )
        navigation_payloads.extend(
            [
                (
                    "index.md",
                    render_index_markdown(
                        generation,
                        page_paths=page_paths,
                    ).encode("utf-8"),
                    "index",
                    None,
                ),
                (
                    "overview.md",
                    render_overview_markdown(generation).encode("utf-8"),
                    "overview",
                    None,
                ),
            ]
        )
        for overview in generation.overviews.select_related("directory").filter(directory_id__isnull=False):
            archive_path = f"directories/{_directory_segment(overview.directory.key)}/overview.md"
            navigation_payloads.append(
                (
                    archive_path,
                    render_overview_markdown(
                        generation,
                        directory_id=overview.directory_id,
                    ).encode("utf-8"),
                    "directory_overview",
                    overview.directory.key,
                )
            )
        navigation_entries = [
            {
                "kind": kind,
                "directory_key": directory_key,
                "archive_path": archive_path,
                "content_sha256": hashlib.sha256(payload).hexdigest(),
            }
            for archive_path, payload, kind, directory_key in navigation_payloads
        ]
    manifest = {
        "format": NATIVE_ARCHIVE_FORMAT,
        "knowledge_base": {
            "id": knowledge_base.pk,
            "name": knowledge_base.name,
            "purpose_md": knowledge_base.purpose_md,
            "schema_md": knowledge_base.schema_md,
        },
        "generation": {"id": scope.generation_id},
        "structure_revision": {"id": scope.structure_revision_id},
        "structure_fingerprint": structure_fingerprint,
        "directories": [
            {
                "key": node.get("key"),
                "name": node.get("name"),
                "parent_key": (node.get("parent") or {}).get("key"),
                "status": node.get("status"),
                "origin": node.get("origin"),
            }
            for node in directories
        ],
        "pages": page_entries,
        "navigation": navigation_entries,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("structure.json", _json_bytes(structure))
        for node in directories:
            key = _directory_segment(node.get("key"))
            archive.writestr(f"directories/{key}/.keep", b"")
        for path, payload in page_payloads:
            archive.writestr(path, payload)
        for path, payload, _kind, _directory_key in navigation_payloads:
            archive.writestr(path, payload)
        if buffer.tell() > byte_limit:
            raise QuotaExceededError(
                "max_bytes",
                f"导出内容超过 {byte_limit // (1024 * 1024)} MB 上限,已停止",
            )
    result = (buffer.getvalue(), len(page_entries))
    assert_read_scope_current(scope)
    return result


__all__ = ["NATIVE_ARCHIVE_FORMAT", "build_native_markdown_export_zip"]
