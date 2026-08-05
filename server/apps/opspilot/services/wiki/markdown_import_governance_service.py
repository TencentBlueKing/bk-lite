"""Secure Markdown import preflight and one-time execution."""

import hashlib
import io
import json
import re
import secrets
import stat
import unicodedata
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath

from django.db import transaction
from django.utils import timezone

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, PageVersion, WikiGeneration, WikiImportPreflight, WikiKnowledgeBase
from apps.opspilot.services.wiki.build_generation_service import (
    begin_build_generation,
    fail_build_generation,
    finalize_build_generation,
    stage_ai_page,
)
from apps.opspilot.services.wiki.directory_assignment_service import resolve_page_directory
from apps.opspilot.services.wiki.markdown_import_service import parse_markdown_document
from apps.opspilot.services.wiki.structure_service import (
    UNCLASSIFIED_DIRECTORY_KEY,
    StructureServiceError,
    preview_native_structure_restore,
    restore_native_structure,
    save_structure,
)
from apps.opspilot.services.wiki.title_service import InvalidWikiTitle, canonical_title, title_identity_key, validate_display_title

NATIVE_ARCHIVE_FORMAT = "opspilot-wiki-native-v1"
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
TOKEN_TTL_MINUTES = 15
_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._:-]{0,63}$")
_ERROR_DETAIL_TEXT_LIMIT = 160


class MarkdownImportGovernanceError(Exception):
    def __init__(self, code, message, *, status_code=422, retryable=False, details=None):
        self.code = str(code)
        self.status_code = int(status_code)
        self.retryable = bool(retryable)
        self.details = dict(details or {})
        super().__init__(message)


def _bounded_text_details(field, value):
    text = "" if value is None else str(value)
    bounded_text = "".join("\ufffd" if unicodedata.category(character) == "Cs" else character for character in text[:_ERROR_DETAIL_TEXT_LIMIT])
    return {
        field: bounded_text,
        f"{field}_length": len(text),
        f"{field}_sha256": hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest(),
        f"{field}_truncated": len(text) > _ERROR_DETAIL_TEXT_LIMIT,
    }


@dataclass(frozen=True)
class InspectedArchive:
    archive_kind: str
    documents: tuple[dict, ...]
    manifest: dict
    structure: dict
    skipped_entries: int
    archive_sha256: str


def _safe_member_path(name):
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise MarkdownImportGovernanceError("zip_entry_path_invalid", "压缩包包含非法路径")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise MarkdownImportGovernanceError("zip_entry_path_invalid", "压缩包包含绝对路径")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise MarkdownImportGovernanceError("zip_entry_path_invalid", "压缩包包含路径穿越")
    return path.as_posix()


def _decode_utf8(payload, path):
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MarkdownImportGovernanceError(
            "archive_text_not_utf8",
            "导入文本必须使用 UTF-8 编码",
            details={"path": path},
        ) from error


def _document(path, payload, *, metadata=None):
    text = _decode_utf8(payload, path)
    parsed = parse_markdown_document(path, text)
    metadata = dict(metadata or {})
    return {
        "archive_path": path,
        "title": parsed.title,
        "page_type": parsed.page_type,
        "tags": parsed.tags,
        "body": parsed.body,
        "original_id": parsed.original_id,
        "directory_key": metadata.get("directory_key") or "",
        "directory_assignment_mode": metadata.get("directory_assignment_mode") or "auto",
        "content_sha256": hashlib.sha256(payload).hexdigest(),
    }


def inspect_markdown_archive(content, filename=""):  # noqa: C901
    if not isinstance(content, (bytes, bytearray)):
        raise MarkdownImportGovernanceError("archive_content_invalid", "导入内容必须为 bytes")
    content = bytes(content)
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        raise MarkdownImportGovernanceError(
            "archive_size_exceeded",
            "导入归档为空或超过大小限制",
            details={"max_bytes": MAX_ARCHIVE_BYTES, "actual_bytes": len(content)},
        )
    archive_sha256 = hashlib.sha256(content).hexdigest()
    suffix = PurePosixPath(filename or "").suffix.casefold()
    if suffix in _MARKDOWN_SUFFIXES:
        return InspectedArchive(
            archive_kind="markdown",
            documents=(_document(PurePosixPath(filename or "import.md").name, content),),
            manifest={},
            structure={},
            skipped_entries=0,
            archive_sha256=archive_sha256,
        )
    if suffix != ".zip":
        raise MarkdownImportGovernanceError("archive_type_unsupported", "仅支持 Markdown 或 ZIP")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise MarkdownImportGovernanceError("zip_invalid", "ZIP 文件损坏") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise MarkdownImportGovernanceError("zip_entry_limit", "ZIP 条目数超过限制")
        total_size = 0
        names = set()
        payloads = {}
        skipped = 0
        for info in infos:
            name = _safe_member_path(info.filename.rstrip("/")) if not info.is_dir() else _safe_member_path(info.filename.rstrip("/"))
            identity = name.casefold()
            if identity in names:
                raise MarkdownImportGovernanceError("zip_duplicate_entry", "ZIP 存在大小写等价的重复路径", details={"path": name})
            names.add(identity)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise MarkdownImportGovernanceError("zip_symlink_forbidden", "ZIP 不允许符号链接", details={"path": name})
            if info.flag_bits & 0x1:
                raise MarkdownImportGovernanceError("zip_encrypted_forbidden", "ZIP 不允许加密条目", details={"path": name})
            if info.is_dir():
                continue
            if info.file_size > MAX_FILE_BYTES:
                raise MarkdownImportGovernanceError("zip_file_size_limit", "ZIP 单文件超过限制", details={"path": name})
            total_size += info.file_size
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise MarkdownImportGovernanceError("zip_uncompressed_limit", "ZIP 解压总大小超过限制")
            if info.file_size and info.compress_size == 0:
                raise MarkdownImportGovernanceError("zip_compression_ratio", "ZIP 压缩比异常", details={"path": name})
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise MarkdownImportGovernanceError("zip_compression_ratio", "ZIP 压缩比超过限制", details={"path": name})
            if name in {"manifest.json", "structure.json"} or PurePosixPath(name).suffix.casefold() in _MARKDOWN_SUFFIXES:
                payloads[name] = archive.read(info)
            else:
                skipped += 1

    manifest = {}
    structure = {}
    archive_kind = "third_party"
    if "manifest.json" in payloads:
        try:
            manifest = json.loads(_decode_utf8(payloads["manifest.json"], "manifest.json"))
        except json.JSONDecodeError as error:
            raise MarkdownImportGovernanceError("manifest_invalid", "manifest.json 不是合法 JSON") from error
        if manifest.get("format") == NATIVE_ARCHIVE_FORMAT:
            archive_kind = "native"
            if "structure.json" not in payloads:
                raise MarkdownImportGovernanceError("native_structure_missing", "原生归档缺少 structure.json")
            try:
                structure = json.loads(_decode_utf8(payloads["structure.json"], "structure.json"))
            except json.JSONDecodeError as error:
                raise MarkdownImportGovernanceError("native_structure_invalid", "structure.json 不是合法 JSON") from error

    manifest_pages = {item.get("archive_path"): item for item in manifest.get("pages", []) if isinstance(item, dict)}
    documents = []
    for path, payload in sorted(payloads.items()):
        if PurePosixPath(path).suffix.casefold() not in _MARKDOWN_SUFFIXES:
            continue
        metadata = manifest_pages.get(path, {})
        document = _document(path, payload, metadata=metadata)
        if archive_kind == "native":
            expected_hash = metadata.get("content_sha256")
            if not metadata or expected_hash != document["content_sha256"]:
                raise MarkdownImportGovernanceError(
                    "native_page_hash_mismatch",
                    "原生归档页面映射或内容哈希不一致",
                    details={"path": path},
                )
        documents.append(document)
    if not documents and archive_kind != "native":
        raise MarkdownImportGovernanceError("archive_has_no_markdown", "归档中没有 Markdown 页面")
    if archive_kind == "native":
        manifest_directories = manifest.get("directories")
        structure_directories = structure.get("directories") if isinstance(structure, dict) else None
        manifest_page_entries = manifest.get("pages")
        if not isinstance(manifest_directories, list) or not isinstance(structure_directories, list):
            raise MarkdownImportGovernanceError("native_structure_invalid", "原生目录清单格式无效")
        if not isinstance(manifest_page_entries, list):
            raise MarkdownImportGovernanceError("native_manifest_pages_invalid", "原生页面清单格式无效")

        manifest_keys = [item.get("key") for item in manifest_directories if isinstance(item, dict)]
        structure_keys = [item.get("key") for item in structure_directories if isinstance(item, dict)]
        if (
            len(manifest_keys) != len(manifest_directories)
            or len(structure_keys) != len(structure_directories)
            or len(manifest_keys) != len(set(manifest_keys))
            or len(structure_keys) != len(set(structure_keys))
            or any(not _KEY_RE.fullmatch(str(key or "")) for key in manifest_keys + structure_keys)
            or set(manifest_keys) != set(structure_keys)
        ):
            raise MarkdownImportGovernanceError(
                "native_directory_key_invalid",
                "原生归档目录 key 非法、重复或 manifest/structure 不一致",
            )
        structure_key_set = set(structure_keys)
        for item in structure_directories:
            parent = item.get("parent")
            if parent is not None and (not isinstance(parent, dict) or parent.get("key") not in structure_key_set):
                raise MarkdownImportGovernanceError(
                    "native_directory_parent_invalid",
                    "原生结构包含未知父目录 key",
                    details={"key": item.get("key")},
                )

        manifest_paths = set()
        for item in manifest_page_entries:
            if not isinstance(item, dict):
                raise MarkdownImportGovernanceError(
                    "native_manifest_pages_invalid",
                    "原生页面映射必须是对象",
                )
            archive_path = _safe_member_path(item.get("archive_path"))
            if archive_path in manifest_paths:
                raise MarkdownImportGovernanceError(
                    "native_manifest_page_duplicate",
                    "原生页面 archive_path 重复",
                    details={"path": archive_path},
                )
            manifest_paths.add(archive_path)
            if item.get("directory_key") not in structure_key_set:
                raise MarkdownImportGovernanceError(
                    "native_page_directory_unknown",
                    "原生页面引用未知目录 key",
                    details={
                        "path": archive_path,
                        "directory_key": item.get("directory_key"),
                    },
                )
        document_paths = {document["archive_path"] for document in documents}
        if manifest_paths != document_paths:
            raise MarkdownImportGovernanceError(
                "native_manifest_page_set_mismatch",
                "原生页面清单与 ZIP 中 Markdown 文件不一致",
                details={
                    "missing": sorted(manifest_paths - document_paths),
                    "unexpected": sorted(document_paths - manifest_paths),
                },
            )
        expected_fingerprint = manifest.get("structure_fingerprint")
        actual_fingerprint = hashlib.sha256(
            json.dumps(
                structure,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if expected_fingerprint and expected_fingerprint != actual_fingerprint:
            raise MarkdownImportGovernanceError(
                "native_structure_fingerprint_mismatch",
                "原生结构 fingerprint 与 structure.json 不一致",
            )
    return InspectedArchive(
        archive_kind=archive_kind,
        documents=tuple(documents),
        manifest=manifest,
        structure=structure,
        skipped_entries=skipped,
        archive_sha256=archive_sha256,
    )


def _existing_pages(knowledge_base):
    result = {}
    for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base).select_related("directory", "current_version").order_by("id"):
        result.setdefault(title_identity_key(page.title), page)
    return result


def _path_suggestion(knowledge_base, document, options):
    explicit_id = options.get("target_directory_id")
    if explicit_id:
        directory = knowledge_base.directories.filter(pk=explicit_id).first()
        return directory.key if directory is not None else None
    mappings = options.get("path_mappings") or {}
    folder = PurePosixPath(document["archive_path"]).parent.as_posix()
    value = mappings.get(folder)
    if value is None:
        return document.get("directory_key") or None
    if type(value) is int:
        directory = knowledge_base.directories.filter(pk=value).first()
        return directory.key if directory is not None else None
    return str(value or "").strip() or None


def _restore_structure_requested(options):
    return bool(options.get("restore_structure") or options.get("restore_native_structure"))


def _create_folders_requested(options):
    return bool(options.get("create_directories_from_folders"))


def _folder_path(document):
    parent = PurePosixPath(document["archive_path"]).parent.as_posix()
    return "" if parent == "." else parent


def _resolve_existing_directory(knowledge_base, value, *, field):
    if value in (None, ""):
        return None
    query = knowledge_base.directories.filter(status="active", accepts_pages=True)
    if type(value) is int:
        directory = query.filter(pk=value).first()
    else:
        directory = query.filter(key=str(value).strip()).first()
    if directory is None:
        raise MarkdownImportGovernanceError(
            "import_directory_invalid",
            "导入目录映射不存在、已失活或不接收页面",
            details={"field": field, "value": value},
        )
    return directory


def _folder_client_ref(folder):
    digest = hashlib.sha256(folder.encode("utf-8")).hexdigest()[:24]
    return f"import-folder-{digest}"


def _folder_structure_plan(knowledge_base, inspected, options):
    if inspected.archive_kind != "third_party":
        raise MarkdownImportGovernanceError(
            "folder_structure_requires_third_party",
            "仅第三方 ZIP 可从文件夹创建人工目录",
        )
    revision = knowledge_base.active_structure_revision
    generation = knowledge_base.active_generation
    if revision is None or generation is None:
        raise MarkdownImportGovernanceError(
            "active_structure_missing",
            "知识库缺少 active structure/generation",
            status_code=409,
        )

    snapshot = deepcopy(revision.structure_snapshot or {})
    existing_nodes = []
    existing_by_id = {}
    for raw in snapshot.get("directories") or []:
        node = {"kind": "existing", **deepcopy(raw)}
        existing_nodes.append(node)
        existing_by_id[node["id"]] = node

    target = _resolve_existing_directory(
        knowledge_base,
        options.get("target_directory_id"),
        field="target_directory_id",
    )
    root_parent = {"id": target.pk, "key": target.key} if target is not None else None
    path_mappings = dict(options.get("path_mappings") or {})
    folders = set()
    for document in inspected.documents:
        folder = _folder_path(document)
        if not folder:
            continue
        parts = PurePosixPath(folder).parts
        for index in range(1, len(parts) + 1):
            folders.add(PurePosixPath(*parts[:index]).as_posix())

    def existing_depth(directory_id, visiting=None):
        visiting = set(visiting or ())
        if directory_id in visiting:
            raise MarkdownImportGovernanceError(
                "directory_cycle",
                "现有目录父链存在循环",
                details={"directory_id": directory_id},
            )
        visiting.add(directory_id)
        node = existing_by_id.get(directory_id)
        if node is None:
            raise MarkdownImportGovernanceError(
                "directory_parent_missing",
                "现有目录父链不完整",
                details={"directory_id": directory_id},
            )
        parent = node.get("parent")
        return 1 if parent is None else existing_depth(parent["id"], visiting) + 1

    anchors = {}
    directory_bindings = {}
    new_nodes = []
    new_depths = {}
    sibling_names = {}
    for node in existing_nodes:
        if node.get("status") != "active":
            continue
        parent = node.get("parent")
        parent_token = ("existing", parent["id"]) if parent else None
        sibling_names[(parent_token, str(node["name"]).casefold())] = {
            "id": node["id"],
            "key": node["key"],
        }

    for folder in sorted(
        folders,
        key=lambda value: (len(PurePosixPath(value).parts), value.casefold()),
    ):
        mapped = path_mappings.get(folder)
        if mapped not in (None, ""):
            directory = _resolve_existing_directory(
                knowledge_base,
                mapped,
                field=f"path_mappings.{folder}",
            )
            anchor = {"id": directory.pk, "key": directory.key}
            anchors[folder] = anchor
            directory_bindings[folder] = {"kind": "existing", **anchor}
            continue

        parent_folder = PurePosixPath(folder).parent.as_posix()
        parent = anchors.get(parent_folder) if parent_folder != "." else root_parent
        parent_token = None
        if parent is not None:
            parent_token = (
                "existing" if "id" in parent else "new",
                parent.get("id", parent.get("client_ref")),
            )
        name = PurePosixPath(folder).name
        collision = sibling_names.get((parent_token, name.casefold()))
        if collision is not None:
            raise MarkdownImportGovernanceError(
                "folder_directory_name_conflict",
                "文件夹名称与目标结构中的同级目录冲突，请显式配置路径映射",
                details={"folder": folder, "directory": collision},
            )
        client_ref = _folder_client_ref(folder)
        if parent is None:
            depth = 1
        elif "id" in parent:
            depth = existing_depth(parent["id"]) + 1
        else:
            depth = new_depths[parent["client_ref"]] + 1
        if depth > 8:
            raise MarkdownImportGovernanceError(
                "directory_depth_exceeded",
                "从文件夹创建目录后将超过最大深度 8",
                details={"folder": folder, "depth": depth},
            )
        node = {
            "kind": "new",
            "client_ref": client_ref,
            "name": name,
            "description": f"由第三方归档文件夹 {folder} 创建",
            "order": len(existing_nodes) + len(new_nodes),
            "rules": {
                "allowed_page_types": [],
                "default_for_page_types": [],
            },
            "parent": deepcopy(parent),
        }
        new_nodes.append(node)
        anchor = {"client_ref": client_ref}
        anchors[folder] = anchor
        directory_bindings[folder] = {"kind": "new", **anchor}
        new_depths[client_ref] = depth
        sibling_names[(parent_token, name.casefold())] = anchor

    return {
        "payload": {
            "structure_version": revision.revision_no,
            "base_generation_id": generation.pk,
            "structure": {
                "format_version": 1,
                "page_types": list(snapshot.get("page_types") or []),
                "directories": [*existing_nodes, *new_nodes],
            },
        },
        "directory_bindings": directory_bindings,
        "new_directories": [
            {
                "folder_path": folder,
                "client_ref": binding["client_ref"],
                "name": PurePosixPath(folder).name,
            }
            for folder, binding in directory_bindings.items()
            if binding["kind"] == "new"
        ],
    }


def build_import_preview(knowledge_base, inspected, options=None):
    options = dict(options or {})
    existing = _existing_pages(knowledge_base)
    titles = set()
    rows = []
    revision = knowledge_base.active_structure_revision
    restoring_structure = _restore_structure_requested(options)
    creating_folders = _create_folders_requested(options)
    if restoring_structure and creating_folders:
        raise MarkdownImportGovernanceError(
            "import_structure_options_conflict",
            "恢复原生结构与从第三方文件夹创建目录不能同时启用",
        )
    structure_preview = None
    folder_plan = None
    if restoring_structure:
        if inspected.archive_kind != "native" or not inspected.structure:
            raise MarkdownImportGovernanceError(
                "native_structure_restore_unavailable",
                "只有包含 structure.json 的 OpsPilot 原生归档可恢复结构",
            )
        try:
            structure_preview = preview_native_structure_restore(
                knowledge_base,
                inspected.structure,
            )
        except StructureServiceError as error:
            raise MarkdownImportGovernanceError(
                error.code,
                str(error),
                status_code=error.status_code,
                retryable=error.retryable,
                details=error.details,
            ) from error
    if creating_folders:
        folder_plan = _folder_structure_plan(knowledge_base, inspected, options)
        structure_preview = {
            "restore_native_structure": False,
            "create_directories_from_folders": True,
            "create_directory_count": len(folder_plan["new_directories"]),
            "directories": folder_plan["new_directories"],
        }
    for document in inspected.documents:
        original_title = document["title"]
        canonicalized_title = original_title
        try:
            canonicalized_title = canonical_title(knowledge_base, original_title)
            title = validate_display_title(canonicalized_title)
        except InvalidWikiTitle as error:
            raise MarkdownImportGovernanceError(
                "archive_title_invalid",
                str(error),
                status_code=422,
                details={
                    "archive_path": document["archive_path"],
                    **_bounded_text_details("original_title", original_title),
                    **_bounded_text_details("canonical_title", canonicalized_title),
                },
            ) from error
        identity = title_identity_key(title)
        if identity in titles:
            raise MarkdownImportGovernanceError(
                "archive_title_duplicate",
                "归档中存在规范化后同名页面",
                details={"title": title},
            )
        titles.add(identity)
        page = existing.get(identity)
        row = {
            "archive_path": document["archive_path"],
            "title": title,
            "page_type": document["page_type"],
            "content_sha256": document["content_sha256"],
            "existing_page_id": page.pk if page is not None else None,
            "action": "create" if page is None else ("candidate" if page.contribution != "ai" else "update"),
        }
        if revision is None:
            raise MarkdownImportGovernanceError("active_structure_missing", "知识库缺少 active structure")
        if restoring_structure:
            directory_key = document.get("directory_key") or UNCLASSIFIED_DIRECTORY_KEY
            row["directory"] = {
                "directory_id": None,
                "directory_key": directory_key,
                "assignment_mode": "auto",
                "source": "native_import",
                "trace": ["native_structure_restore"],
                "route_reason": "native_structure_restore",
                "suggestion": {
                    "key": directory_key,
                    "source": "native_import",
                    "reason": "native manifest stable key",
                    "confidence": 1,
                    "schema_mismatch": False,
                    "low_confidence": False,
                },
                "redirect_chain": [],
                "structure_revision": {
                    "id": None,
                    "revision_no": None,
                    "fingerprint": inspected.manifest.get(
                        "structure_fingerprint",
                        "",
                    ),
                },
            }
        elif (
            creating_folders
            and _folder_path(document)
            and folder_plan["directory_bindings"]
            .get(
                _folder_path(document),
                {},
            )
            .get("kind")
            == "new"
        ):
            binding = folder_plan["directory_bindings"][_folder_path(document)]
            row["directory"] = {
                "directory_id": None,
                "directory_key": "",
                "pending_client_ref": binding["client_ref"],
                "assignment_mode": "auto",
                "source": "third_party_folder_preview",
                "trace": [
                    "third_party_folder",
                    _folder_path(document),
                    binding["client_ref"],
                ],
                "route_reason": "create_manual_directory_from_folder",
                "suggestion": {
                    "key": None,
                    "source": "third_party_folder",
                    "reason": _folder_path(document),
                    "confidence": 1,
                    "schema_mismatch": False,
                    "low_confidence": False,
                },
                "redirect_chain": [],
                "structure_revision": {
                    "id": revision.pk,
                    "revision_no": revision.revision_no,
                    "fingerprint": revision.fingerprint,
                },
            }
        else:
            assignment = resolve_page_directory(
                knowledge_base=knowledge_base,
                structure_revision=revision,
                page_type=document["page_type"],
                assignment_mode=page.directory_assignment_mode if page is not None else "auto",
                current_directory=page.directory if page is not None else None,
                suggested_key=_path_suggestion(knowledge_base, document, options),
                suggestion_source="native_import",
                classification_root_id=options.get("classification_root_id"),
                suggestion_reason="native manifest" if inspected.archive_kind == "native" else "archive path mapping",
            )
            row["directory"] = assignment.as_build_trace()
        rows.append(row)
    preview = {
        "archive_kind": inspected.archive_kind,
        "archive_sha256": inspected.archive_sha256,
        "skipped_entries": inspected.skipped_entries,
        "pages": rows,
        "counts": {
            "total": len(rows),
            "create": sum(row["action"] == "create" for row in rows),
            "update": sum(row["action"] == "update" for row in rows),
            "candidate": sum(row["action"] == "candidate" for row in rows),
        },
        "native_structure_available": bool(inspected.structure),
        "restore_structure_requested": restoring_structure,
        "create_directories_from_folders_requested": creating_folders,
        "structure_preview": structure_preview,
    }
    return preview


def _fingerprint(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@transaction.atomic
def preflight_markdown_import(knowledge_base, content, *, filename="", actor="", options=None):
    inspected = inspect_markdown_archive(content, filename)
    knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base.pk)
    preview = build_import_preview(knowledge_base, inspected, options=options)
    token = secrets.token_urlsafe(32)
    WikiImportPreflight.objects.create(
        knowledge_base=knowledge_base,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        actor=str(actor or "")[:150],
        archive_sha256=inspected.archive_sha256,
        filename=PurePosixPath(filename or "import").name[:255],
        archive_kind=inspected.archive_kind,
        base_generation=knowledge_base.active_generation,
        structure_revision=knowledge_base.active_structure_revision,
        structure_version=getattr(knowledge_base.active_structure_revision, "revision_no", None),
        classification_root_id=(options or {}).get("classification_root_id") or None,
        options=dict(options or {}),
        preview=preview,
        preview_fingerprint=_fingerprint(preview),
        expires_at=timezone.now() + timedelta(minutes=TOKEN_TTL_MINUTES),
        created_by=str(actor or "")[:32],
        updated_by=str(actor or "")[:32],
    )
    return {
        "token": token,
        "expires_in_seconds": TOKEN_TTL_MINUTES * 60,
        "preview": preview,
        "base_generation_id": knowledge_base.active_generation_id,
        "structure_revision_id": knowledge_base.active_structure_revision_id,
        "structure_version": getattr(knowledge_base.active_structure_revision, "revision_no", None),
    }


def _create_import_body_candidate(page, document, build, generation, operator):
    version = PageVersion.objects.create(
        page=page,
        no=(page.page_versions.order_by("-no").values_list("no", flat=True).first() or 0) + 1,
        body=document["body"],
        meta_snapshot={"source": "markdown_import", "archive_path": document["archive_path"]},
        change_type="candidate",
        build_record=build,
        created_in_generation=generation,
        is_current=False,
        created_by=operator or "",
    )
    check = CheckItem.objects.create(
        knowledge_base=page.knowledge_base,
        check_type="conflict",
        status="open",
        related={"pages": [page.pk], "source": "markdown_import", "archive_path": document["archive_path"]},
        candidate_version=version,
        suggested_actions=["use_current", "use_candidate"],
        decision_context={"decision_type": "knowledge_conflict", "source": "markdown_import"},
        created_by=operator or "",
        updated_by=operator or "",
    )
    return check


_EXECUTION_PREVIEW_KEY = "_execution"
_TERMINAL_BUILD_STATUSES = frozenset(("success", "partial"))


def _preflight_execution_result(record):
    execution = (record.preview or {}).get(_EXECUTION_PREVIEW_KEY)
    if not isinstance(execution, dict) or execution.get("status") != "success":
        return None
    result = execution.get("result")
    return dict(result) if isinstance(result, dict) else None


def _store_preflight_execution_result(record_id, result):
    if not record_id:
        return
    record = WikiImportPreflight.objects.select_for_update().get(pk=record_id)
    record.preview = {
        **(record.preview or {}),
        _EXECUTION_PREVIEW_KEY: {
            "status": "success",
            "result": dict(result),
            "completed_at": timezone.now().isoformat(),
        },
    }
    record.status = "consumed"
    record.consumed_at = record.consumed_at or timezone.now()
    record.save(update_fields=["preview", "status", "consumed_at", "updated_at"])


def _release_preflight_after_failure(record_id):
    if not record_id:
        return
    with transaction.atomic():
        record = WikiImportPreflight.objects.select_for_update().get(pk=record_id)
        if _preflight_execution_result(record) is not None:
            return
        preview = dict(record.preview or {})
        preview.pop(_EXECUTION_PREVIEW_KEY, None)
        record.preview = preview
        record.status = "active"
        record.consumed_at = None
        record.save(update_fields=["preview", "status", "consumed_at", "updated_at"])


def _complete_import_build(record, *, counts, affected_page_ids, generation_id, relation_result, import_build_id):
    if record.status in _TERMINAL_BUILD_STATUSES:
        return
    record.counts = dict(counts)
    record.affected_pages = list(affected_page_ids)
    record.maintenance = {
        **(record.maintenance or {}),
        "generation_relations": relation_result,
        "generation_import": {
            "build_record_id": import_build_id,
            "generation_id": generation_id,
        },
    }
    record.stage = "done"
    record.status = "success"
    record.progress = 100
    record.save(
        update_fields=[
            "counts",
            "affected_pages",
            "maintenance",
            "stage",
            "status",
            "progress",
            "updated_at",
        ]
    )


def _execute_generation_import(
    knowledge_base,
    inspected,
    preview,
    *,
    operator="",
    preflight_record_id=None,
    completion_build_record_id=None,
):
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        operator=operator or "",
        inputs={"archive_sha256": inspected.archive_sha256, "archive_kind": inspected.archive_kind},
        stage="generating",
        status="running",
    )
    context = begin_build_generation(
        knowledge_base,
        build,
        source_fingerprints=[{"archive_sha256": inspected.archive_sha256}],
        pipeline_version="wiki-markdown-import-v1",
        operator=operator,
    )
    page_actions = []
    directory_trace = []
    result_pages = []
    counts = {"created": 0, "updated": 0, "candidate": 0}
    result_payload = {}
    try:
        generation = WikiGeneration.objects.get(pk=context.candidate_generation_id)
        preview_by_path = {row["archive_path"]: row for row in preview["pages"]}
        existing = _existing_pages(knowledge_base)
        for document in inspected.documents:
            row = preview_by_path[document["archive_path"]]
            page = existing.get(title_identity_key(row["title"]))
            directory = row.get("directory") or {}
            if page is not None and page.contribution != "ai":
                check = _create_import_body_candidate(page, document, build, generation, operator)
                counts["candidate"] += 1
                action = {
                    "page_id": page.pk,
                    "title": page.title,
                    "action": "candidate",
                    "check_id": check.pk,
                    "archive_path": document["archive_path"],
                }
                page_actions.append(action)
                result_pages.append(action)
                continue
            staged = stage_ai_page(
                context,
                title=row["title"],
                page_type=document["page_type"],
                tags=document["tags"],
                body=document["body"],
                directory_id=directory["directory_id"],
                assignment_mode=directory["assignment_mode"],
                build_record=build,
                operator=operator,
                update_method="markdown_import",
                change_type="markdown_import",
                body_strategy="replace",
            )
            version = PageVersion.objects.get(pk=staged.page_version_id)
            version.meta_snapshot = {
                **(version.meta_snapshot or {}),
                "source": "markdown_import",
                "archive_path": document["archive_path"],
                "archive_sha256": inspected.archive_sha256,
            }
            version.save(update_fields=["meta_snapshot", "updated_at"])
            count_key = "created" if staged.action == "create" else "updated"
            counts[count_key] += 1
            action = {
                "page_id": staged.page_id,
                "page_version_id": staged.page_version_id,
                "title": staged.title,
                "action": staged.action,
                "archive_path": document["archive_path"],
                "directory_id": staged.directory_id,
            }
            page_actions.append(action)
            directory_trace.append({**directory, "page_id": staged.page_id, "archive_path": document["archive_path"]})
            result_pages.append(action)
            existing[title_identity_key(staged.title)] = KnowledgePage.objects.get(pk=staged.page_id)

        affected_page_ids = [row["page_id"] for row in result_pages]

        def activation_hook(candidate, _locked_knowledge_base, relation_result):
            payload = {
                "build_record_id": build.pk,
                "generation_id": candidate.pk,
                "counts": dict(counts),
                "pages": list(result_pages),
                "relations": relation_result,
            }
            locked_build = BuildRecord.objects.select_for_update().get(pk=build.pk)
            _complete_import_build(
                locked_build,
                counts=counts,
                affected_page_ids=affected_page_ids,
                generation_id=candidate.pk,
                relation_result=relation_result,
                import_build_id=build.pk,
            )
            if completion_build_record_id and completion_build_record_id != build.pk:
                completion = (
                    BuildRecord.objects.select_for_update()
                    .filter(
                        pk=completion_build_record_id,
                        knowledge_base_id=knowledge_base.pk,
                    )
                    .first()
                )
                if completion is not None:
                    _complete_import_build(
                        completion,
                        counts=counts,
                        affected_page_ids=affected_page_ids,
                        generation_id=candidate.pk,
                        relation_result=relation_result,
                        import_build_id=build.pk,
                    )
            _store_preflight_execution_result(preflight_record_id, payload)
            result_payload.update(payload)

        finalize_build_generation(
            context,
            build_record=build,
            page_actions=page_actions,
            directory_trace=directory_trace,
            activation_hook=activation_hook,
        )
        return dict(result_payload)
    except Exception as error:
        fail_build_generation(context, build_record=build, error=error)
        BuildRecord.objects.filter(pk=build.pk).exclude(status__in=_TERMINAL_BUILD_STATUSES).update(
            status="failed", stage="failed", errors=[str(error)]
        )
        _release_preflight_after_failure(preflight_record_id)
        raise


def _claim_preflight(knowledge_base, token, inspected, actor, preview):
    token_hash = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    with transaction.atomic():
        current = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base.pk)
        record = WikiImportPreflight.objects.select_for_update().filter(token_hash=token_hash).first()
        if record is None or record.knowledge_base_id != knowledge_base.pk:
            raise MarkdownImportGovernanceError("preflight_token_invalid", "导入预检 token 无效", status_code=409)
        if record.status != "active":
            raise MarkdownImportGovernanceError("preflight_token_consumed", "导入预检 token 已使用", status_code=409)
        if record.expires_at <= timezone.now():
            record.status = "expired"
            record.save(update_fields=["status", "updated_at"])
            raise MarkdownImportGovernanceError("preflight_token_expired", "导入预检 token 已过期", status_code=409)
        if record.actor != str(actor or "")[:150] or record.archive_sha256 != inspected.archive_sha256:
            raise MarkdownImportGovernanceError("preflight_binding_mismatch", "导入归档或操作者与预检不一致", status_code=409)
        if (
            current.active_generation_id != record.base_generation_id
            or current.active_structure_revision_id != record.structure_revision_id
            or getattr(current.active_structure_revision, "revision_no", None) != record.structure_version
        ):
            raise MarkdownImportGovernanceError(
                "preflight_cas_conflict",
                "知识库 generation 或结构已变化，请重新预检",
                status_code=409,
                retryable=True,
                details={
                    "active_generation_id": current.active_generation_id,
                    "structure_revision_id": current.active_structure_revision_id,
                },
            )
        if record.preview_fingerprint != _fingerprint(preview):
            raise MarkdownImportGovernanceError("preflight_preview_changed", "导入预览已变化，请重新预检", status_code=409)
        record.status = "consumed"
        record.consumed_at = timezone.now()
        record.preview = {
            **(record.preview or {}),
            _EXECUTION_PREVIEW_KEY: {
                "status": "running",
                "claimed_at": record.consumed_at.isoformat(),
            },
        }
        record.save(update_fields=["preview", "status", "consumed_at", "updated_at"])
        return record, current


def execute_markdown_import(
    knowledge_base,
    token,
    content,
    *,
    filename="",
    actor="",
    completion_build_record_id=None,
):
    inspected = inspect_markdown_archive(content, filename)
    probe = WikiImportPreflight.objects.filter(
        token_hash=hashlib.sha256(str(token or "").encode("utf-8")).hexdigest(),
        knowledge_base=knowledge_base,
    ).first()
    if probe is None:
        raise MarkdownImportGovernanceError("preflight_token_invalid", "导入预检 token 无效", status_code=409)
    if probe.actor != str(actor or "")[:150] or probe.archive_sha256 != inspected.archive_sha256:
        raise MarkdownImportGovernanceError("preflight_binding_mismatch", "导入归档或操作者与预检不一致", status_code=409)
    current = WikiKnowledgeBase.objects.select_related("active_structure_revision", "active_generation").get(pk=knowledge_base.pk)
    preview = build_import_preview(current, inspected, options=probe.options)
    structure_change_requested = _restore_structure_requested(probe.options) or _create_folders_requested(probe.options)
    if structure_change_requested:
        with transaction.atomic():
            record, current = _claim_preflight(
                current,
                token,
                inspected,
                actor,
                preview,
            )
            structure_result = None
            folder_plan = None
            if _restore_structure_requested(record.options):
                try:
                    structure_result = restore_native_structure(
                        current,
                        inspected.structure,
                        expected_base_generation_id=record.base_generation_id,
                        expected_structure_version=record.structure_version,
                        source_fingerprint=inspected.archive_sha256,
                        operator=actor,
                    )
                except StructureServiceError as error:
                    raise MarkdownImportGovernanceError(
                        error.code,
                        str(error),
                        status_code=error.status_code,
                        retryable=error.retryable,
                        details=error.details,
                    ) from error
            else:
                folder_plan = _folder_structure_plan(
                    current,
                    inspected,
                    record.options,
                )
                if folder_plan["new_directories"]:
                    try:
                        structure_result = save_structure(
                            current,
                            folder_plan["payload"],
                            operator=actor,
                        )
                    except StructureServiceError as error:
                        raise MarkdownImportGovernanceError(
                            error.code,
                            str(error),
                            status_code=error.status_code,
                            retryable=error.retryable,
                            details=error.details,
                        ) from error

            current = WikiKnowledgeBase.objects.select_related(
                "active_structure_revision",
                "active_generation",
            ).get(pk=current.pk)
            routed_options = dict(record.options or {})
            routed_options["restore_structure"] = False
            routed_options["restore_native_structure"] = False
            routed_options["create_directories_from_folders"] = False

            folder_report = []
            if folder_plan is not None:
                created_by_ref = {
                    item["client_ref"]: item for item in (structure_result.get("client_ref_map", []) if structure_result is not None else [])
                }
                path_mappings = dict(routed_options.get("path_mappings") or {})
                for folder, binding in folder_plan["directory_bindings"].items():
                    if binding["kind"] == "existing":
                        directory_id = binding["id"]
                        directory_key = binding["key"]
                    else:
                        created = created_by_ref.get(binding["client_ref"])
                        if created is None:
                            raise MarkdownImportGovernanceError(
                                "folder_directory_mapping_missing",
                                "结构发布后缺少文件夹目录映射",
                                details={
                                    "folder": folder,
                                    "client_ref": binding["client_ref"],
                                },
                            )
                        directory_id = created["id"]
                        directory_key = created["key"]
                    path_mappings[folder] = directory_id
                    folder_report.append(
                        {
                            "folder_path": folder,
                            "directory_id": directory_id,
                            "directory_key": directory_key,
                            "created": binding["kind"] == "new",
                        }
                    )
                routed_options["path_mappings"] = path_mappings

            routed_preview = build_import_preview(
                current,
                inspected,
                options=routed_options,
            )
            result = _execute_generation_import(
                current,
                inspected,
                routed_preview,
                operator=actor,
                preflight_record_id=record.pk,
                completion_build_record_id=completion_build_record_id,
            )
            if _restore_structure_requested(record.options):
                result["structure_restore"] = {
                    "structure_revision": structure_result["structure_revision"],
                    "governance_generation": structure_result["active_generation"],
                    "client_ref_map": structure_result["client_ref_map"],
                }
            else:
                result["folder_structure"] = {
                    "created_directory_count": sum(item["created"] for item in folder_report),
                    "directories": folder_report,
                    "structure_revision": (structure_result["structure_revision"] if structure_result is not None else None),
                    "governance_generation": (structure_result["active_generation"] if structure_result is not None else None),
                }
            _store_preflight_execution_result(record.pk, result)
            return result

    _record, current = _claim_preflight(
        current,
        token,
        inspected,
        actor,
        preview,
    )
    return _execute_generation_import(
        current,
        inspected,
        preview,
        operator=actor,
        preflight_record_id=_record.pk,
        completion_build_record_id=completion_build_record_id,
    )


__all__ = [
    "MarkdownImportGovernanceError",
    "build_import_preview",
    "execute_markdown_import",
    "inspect_markdown_archive",
    "preflight_markdown_import",
]
