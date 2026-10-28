"""流程列表导入/导出。

包格式（schema_version=1）::

    workflow-pack.zip
    ├── manifest.json
    ├── workflows/0001.json
    └── files/0001-report.docx

JSON 只带名称、描述、定义、画布，以及这份流程引用的文件。
不带流程 id、组织、engine_name、版本、is_builtin 和执行记录。
通知渠道、模型、记忆空间的编号留在定义里。
文档模板和上传知识的旧凭证会从 JSON 里拿掉，文件字节放进 files/；
每条记录写明节点、字段和相对路径。导入时在当前环境重新存储，并写回新的上传引用。
导出失败的流程不写入压缩包，失败原因由导出接口返回给页面。
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any, NoReturn

from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.core.logger import workflow_logger as logger
from apps.workflow.serializers import WORKFLOW_NAME_CONFLICT_MESSAGE, WorkflowSerializer
from apps.workflow.services.agent_knowledge_inputs import (
    AGENT_KNOWLEDGE_TOKEN_SALT,
    MAX_AGENT_KNOWLEDGE_FILE_BYTES,
    MAX_AGENT_KNOWLEDGE_FILES,
    MAX_AGENT_KNOWLEDGE_TOTAL_BYTES,
    store_uploaded_agent_knowledge,
)
from apps.workflow.services.object_store import ArtifactTooLarge, WorkflowObjectStore
from apps.workflow.services.report_template_inputs import REPORT_TEMPLATE_TOKEN_SALT, store_uploaded_report_template
from apps.workflow.services.reports import MAX_TEMPLATE_BYTES, ReportTemplateError, parse_report_template

PACK_FORMAT = "bklite.workflow-pack"
PACK_SCHEMA_VERSION = 1
# 解压后总大小是产品限额。成员数量只拦异常压缩包，不是流程条数上限。
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_PACK_MEMBERS = 10000
MAX_COMPRESSION_RATIO = 100
DOCUMENT_ATOM = "bklite_document_render"
AGENT_ATOM = "bklite_agent"
TEMPLATE_FIELD = "template"
KNOWLEDGE_FIELD = "knowledge_files"
_FILE_SPECS = {
    TEMPLATE_FIELD: {
        "atom": DOCUMENT_ATOM,
        "multiple": False,
        "max_bytes": MAX_TEMPLATE_BYTES,
        "suffixes": {".docx", ".xlsx"},
        "fallback_suffix": ".docx",
        "fallback_stem": "template",
        "invalid": "文档模板无效",
        "missing": "文档模板缺失",
        "unreadable": "文档模板无法读取",
        "too_large": "文档模板超过 5MB",
        "bad_path": "文档模板路径非法",
        "object_prefix": "workflow/templates/",
    },
    KNOWLEDGE_FIELD: {
        "atom": AGENT_ATOM,
        "multiple": True,
        "max_bytes": MAX_AGENT_KNOWLEDGE_FILE_BYTES,
        "max_count": MAX_AGENT_KNOWLEDGE_FILES,
        "max_total": MAX_AGENT_KNOWLEDGE_TOTAL_BYTES,
        "suffixes": {".md"},
        "fallback_suffix": ".md",
        "fallback_stem": "knowledge",
        "invalid": "上传知识无效",
        "missing": "上传知识缺失",
        "unreadable": "上传知识无法读取",
        "too_large": "上传知识超过 10MB",
        "bad_path": "上传知识路径非法",
        "object_prefix": "workflow/knowledge/uploads/",
    },
}
_FILE_NAME = re.compile(r"[^\w\u4e00-\u9fff.-]+")


class PackRejected(Exception):
    """整包拒绝：不导入、不导出任何流程。"""


class PackFileError(Exception):
    """这一条流程的文件读不出来。"""


def export_workflow_pack(queryset, ids: list[int], *, store=None) -> tuple[bytes | None, list[dict[str, str]]]:
    """导出编辑器当前定义。全部失败时返回 (None, failures)。"""
    store = store or WorkflowObjectStore()
    found = {item.pk: item for item in queryset.filter(pk__in=ids)}
    failures: list[dict[str, str]] = []
    packaged: list[dict[str, Any]] = []
    total = 0
    sequence = 1
    for workflow_id in ids:
        workflow = found.get(workflow_id)
        if workflow is None:
            failures.append({"name": str(workflow_id), "reason": "流程不存在或无权导出"})
            continue
        try:
            payload, files, sequence = _export_one(workflow, store, sequence)
        except PackFileError as error:
            failures.append({"name": workflow.name, "reason": str(error)})
            continue
        except Exception as error:
            _log_unexpected("workflow_pack_export_item_failed", error, workflow_id=workflow.pk, failed_stage="export_item")
            failures.append({"name": workflow.name, "reason": "导出失败"})
            continue
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        file_bytes = sum(len(content) for _, content in files)
        total += len(encoded) + file_bytes
        if total > MAX_UNCOMPRESSED_BYTES:
            _reject("size", "压缩包解压后总大小超过 200MB")
        packaged.append({"payload": payload, "encoded": encoded, "files": files})
    logger.info(
        "event=workflow_pack_exported exported=%s failed=%s",
        len(packaged),
        len(failures),
    )
    if not packaged:
        return None, failures
    return _write_archive(packaged), failures


def import_workflow_pack(
    upload,
    *,
    request,
    team: list[int],
    username: str,
    domain: str,
    store=None,
    max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
) -> dict[str, list]:
    """每份 JSON 在选定组织新建一条草稿。单条失败不影响已经导入的流程。"""
    if not team:
        raise ValueError("请选择组织")
    store = store or WorkflowObjectStore()
    entries = _read_pack(upload, max_uncompressed_bytes=max_uncompressed_bytes)
    created: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for entry in entries:
        item_created, item_failed = _import_one(
            entry,
            request=request,
            team=team,
            username=username,
            domain=domain,
            store=store,
        )
        if item_created is not None:
            created.append(item_created)
        if item_failed is not None:
            failed.append(item_failed)
    logger.info(
        "event=workflow_pack_imported created=%s failed=%s",
        len(created),
        len(failed),
    )
    return {"created": created, "failed": failed, "rebind": []}


def _export_one(workflow, store, sequence: int) -> tuple[dict[str, Any], list[tuple[str, bytes]], int]:
    definition = workflow.definition if isinstance(workflow.definition, dict) else None
    canvas = workflow.canvas_metadata if isinstance(workflow.canvas_metadata, dict) else {}
    if definition is None:
        raise PackFileError("流程定义无效")
    definition = copy.deepcopy(definition)
    canvas = copy.deepcopy(canvas)
    files: list[tuple[str, bytes]] = []
    records: list[dict[str, str]] = []
    for task in _walk_tasks(definition.get("tasks")):
        packed, sequence = _export_task_files(task, store, sequence, workflow_id=workflow.pk)
        for path, content, record in packed:
            files.append((path, content))
            records.append(record)
    payload = {
        "name": workflow.name,
        "description": workflow.description or "",
        "definition": definition,
        "canvas_metadata": canvas,
        "files": records,
    }
    return payload, files, sequence


def _export_task_files(task: dict[str, Any], store, sequence: int, *, workflow_id: int) -> tuple[list[tuple[str, bytes, dict[str, str]]], int]:
    if not isinstance(task, dict):
        return [], sequence
    inputs = task.get("inputParameters")
    if not isinstance(inputs, dict):
        return [], sequence
    reference = task.get("taskReferenceName")
    if task.get("name") == DOCUMENT_ATOM and ("template" in inputs or "template_snapshot" in inputs):
        if not isinstance(reference, str) or not reference:
            raise PackFileError(_FILE_SPECS[TEMPLATE_FIELD]["unreadable"])
        content, filename = _read_document_template(inputs, store)
        path, sequence = _pack_file(TEMPLATE_FIELD, filename, content, sequence)
        inputs.pop("template", None)
        inputs.pop("template_snapshot", None)
        return [(path, content, _file_record(reference, TEMPLATE_FIELD, path, filename))], sequence
    if task.get("name") == AGENT_ATOM and inputs.get("knowledge_files") not in (None, [], ""):
        if not isinstance(reference, str) or not reference:
            raise PackFileError(_FILE_SPECS[KNOWLEDGE_FIELD]["unreadable"])
        packed = _export_knowledge_files(inputs, store, sequence, workflow_id=workflow_id, reference=reference)
        inputs.pop("knowledge_files", None)
        return packed
    return [], sequence


def _export_knowledge_files(
    inputs: dict[str, Any], store, sequence: int, *, workflow_id: int, reference: str
) -> tuple[list[tuple[str, bytes, dict[str, str]]], int]:
    spec = _FILE_SPECS[KNOWLEDGE_FIELD]
    references = inputs.get("knowledge_files")
    if not isinstance(references, list) or not 1 <= len(references) <= spec["max_count"]:
        raise PackFileError(spec["unreadable"])
    packed = []
    total = 0
    for item in references:
        if not isinstance(item, dict) or item.get("kind") != "workflow_agent_knowledge":
            raise PackFileError(spec["unreadable"])
        content, filename = _read_knowledge_file(item, store, workflow_id=workflow_id)
        total += len(content)
        if total > spec["max_total"]:
            raise PackFileError(spec["unreadable"])
        path, sequence = _pack_file(KNOWLEDGE_FIELD, filename, content, sequence)
        packed.append((path, content, _file_record(reference, KNOWLEDGE_FIELD, path, filename)))
    return packed, sequence


def _pack_file(field: str, filename: str, content: bytes, sequence: int) -> tuple[str, int]:
    spec = _FILE_SPECS[field]
    safe_name = _safe_pack_filename(
        filename,
        content,
        suffixes=spec["suffixes"],
        fallback_suffix=spec["fallback_suffix"],
        fallback_stem=spec["fallback_stem"],
    )
    path = f"files/{sequence:04d}-{safe_name}"
    return path, sequence + 1


def _file_record(reference: str, field: str, path: str, filename: str) -> dict[str, str]:
    return {"task_reference": reference, "field": field, "path": path, "filename": filename}


def _read_document_template(inputs: dict[str, Any], store) -> tuple[bytes, str]:
    spec = _FILE_SPECS[TEMPLATE_FIELD]
    template = inputs.get("template")
    if isinstance(template, dict) and template.get("kind") == "uploaded":
        payload = _signed_payload(template.get("token"), REPORT_TEMPLATE_TOKEN_SALT, spec["unreadable"])
        filename = str(payload.get("name") or f"template.{payload.get('format') or 'docx'}")
        return _read_object(store, payload, spec), filename
    snapshot = inputs.get("template_snapshot")
    if isinstance(snapshot, dict):
        fmt = str(snapshot.get("format") or "")
        prefix = str(snapshot.get("filename_prefix") or "report").strip() or "report"
        filename = f"{prefix}.{fmt}" if fmt else prefix
        return _read_object(store, snapshot, spec), filename
    raise PackFileError(spec["unreadable"])


def _read_knowledge_file(reference: dict[str, Any], store, *, workflow_id: int) -> tuple[bytes, str]:
    spec = _FILE_SPECS[KNOWLEDGE_FIELD]
    payload = _signed_payload(reference.get("token"), AGENT_KNOWLEDGE_TOKEN_SALT, spec["unreadable"])
    if payload.get("workflow_id") != workflow_id:
        raise PackFileError(spec["unreadable"])
    object_key = str(payload.get("object_key") or "").replace("\\", "/")
    parts = object_key.split("/")
    if len(parts) < 6 or parts[:3] != ["workflow", "knowledge", "uploads"] or parts[4] != str(workflow_id):
        raise PackFileError(spec["unreadable"])
    filename = str(payload.get("name") or reference.get("name") or "knowledge.md")
    content = _read_object(store, payload, spec)
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PackFileError(spec["unreadable"]) from error
    if not content.strip():
        raise PackFileError(spec["unreadable"])
    return content, filename


def _signed_payload(token: Any, salt: str, unreadable: str) -> dict[str, Any]:
    if not isinstance(token, str) or not token:
        raise PackFileError(unreadable)
    try:
        payload = signing.loads(token, salt=salt)
    except signing.BadSignature as error:
        raise PackFileError(unreadable) from error
    if not isinstance(payload, dict):
        raise PackFileError(unreadable)
    return payload


def _read_object(store, payload: dict[str, Any], spec: dict[str, Any]) -> bytes:
    object_key = str(payload.get("object_key") or "").replace("\\", "/")
    if not object_key.startswith(spec["object_prefix"]) or ".." in object_key.split("/"):
        raise PackFileError(spec["unreadable"])
    expected_size = payload.get("size")
    expected_sha = str(payload.get("sha256") or "")
    try:
        content, _, _ = store.get(object_key, max_bytes=spec["max_bytes"])
    except ArtifactTooLarge as error:
        raise PackFileError(spec["too_large"]) from error
    except (OSError, FileNotFoundError) as error:
        raise PackFileError(spec["unreadable"]) from error
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or len(content) != expected_size
        or hashlib.sha256(content).hexdigest() != expected_sha
    ):
        raise PackFileError(spec["unreadable"])
    if len(content) > spec["max_bytes"]:
        raise PackFileError(spec["too_large"])
    return content


def _import_one(entry: dict[str, Any], *, request, team: list[int], username: str, domain: str, store) -> tuple[dict | None, dict | None]:
    name = entry.get("name")
    label = name.strip()[:120] if isinstance(name, str) else ""
    try:
        created = _create_imported_workflow(
            entry,
            request=request,
            team=team,
            username=username,
            domain=domain,
            store=store,
        )
    except (serializers.ValidationError, ReportTemplateError, ValueError, PackFileError) as error:
        return None, {"name": label or "未命名", "reason": _safe_reason(error)}
    except IntegrityError as error:
        if _is_name_conflict(error):
            return None, {"name": label or "未命名", "reason": WORKFLOW_NAME_CONFLICT_MESSAGE}
        _log_unexpected("workflow_pack_import_item_failed", error, failed_stage="create")
        return None, {"name": label or "未命名", "reason": "导入失败"}
    except Exception as error:
        _log_unexpected("workflow_pack_import_item_failed", error, failed_stage="create")
        return None, {"name": label or "未命名", "reason": "导入失败"}
    return {"name": created.name, "id": created.pk}, None


def _create_imported_workflow(entry: dict[str, Any], *, request, team: list[int], username: str, domain: str, store):
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("流程名称不能为空")
    if len(name.strip()) > 120:
        raise ValueError("流程名称过长")
    description = entry.get("description") or ""
    if not isinstance(description, str):
        raise ValueError("流程描述无效")
    if len(description) > 500:
        raise ValueError("流程描述过长")
    definition = entry.get("definition")
    canvas = entry.get("canvas_metadata")
    if not isinstance(definition, dict) or not isinstance(canvas, dict):
        raise ValueError("流程定义无效")
    definition = copy.deepcopy(definition)
    canvas = copy.deepcopy(canvas)
    files = _prepared_files(entry, definition)
    _reject_unpacked_files(definition, files)
    _strip_packed_inputs(definition)
    serializer = WorkflowSerializer(
        data={"name": name.strip(), "description": description, "definition": definition, "canvas_metadata": canvas},
        context={"request": request, "team": team},
    )
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        workflow = serializer.save(
            team=team,
            created_by=username,
            updated_by=username,
            domain=domain,
            updated_by_domain=domain,
        )
        if files:
            definition = copy.deepcopy(workflow.definition)
            _bind_files(
                definition,
                files,
                workflow_id=workflow.pk,
                team_id=team[0],
                username=username,
                domain=domain,
                store=store,
            )
            workflow.definition = definition
            workflow.save(update_fields=["definition"])
    return workflow


def _prepared_files(entry: dict[str, Any], definition: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("files") or []
    if not isinstance(raw, list):
        raise ValueError("流程文件无效")
    prepared = []
    seen_single: set[str] = set()
    knowledge_count: dict[str, int] = {}
    knowledge_total: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("流程文件无效")
        reference = item.get("task_reference")
        field = item.get("field")
        spec = _FILE_SPECS.get(field) if isinstance(field, str) else None
        if spec is None or not isinstance(reference, str) or not reference:
            raise ValueError("流程文件无效")
        filename = item.get("filename")
        content = item.get("content")
        if not isinstance(filename, str) or not filename or len(filename) > 255 or PurePosixPath(filename).name != filename:
            raise ValueError(spec["invalid"])
        if not _is_pack_file_path(item.get("path")):
            raise ValueError(spec["bad_path"])
        if not spec["multiple"] and reference in seen_single:
            raise ValueError(spec["invalid"])
        if item.get("oversized") or (isinstance(content, (bytes, bytearray)) and len(content) > spec["max_bytes"]):
            raise ValueError(spec["too_large"])
        if not isinstance(content, (bytes, bytearray)):
            raise ValueError(spec["missing"])
        task = _task_for_field(definition, reference, spec["atom"])
        if task is None:
            raise ValueError(spec["invalid"])
        payload = bytes(content)
        if field == TEMPLATE_FIELD:
            seen_single.add(reference)
            parse_report_template(payload, PurePosixPath(filename).suffix.lower().lstrip("."))
        else:
            count = knowledge_count.get(reference, 0) + 1
            total = knowledge_total.get(reference, 0) + len(payload)
            if count > spec["max_count"]:
                raise ValueError(spec["invalid"])
            if total > spec["max_total"]:
                raise ValueError("知识文件总大小超过 20 MiB 限额")
            _validate_knowledge_bytes(payload, filename)
            knowledge_count[reference] = count
            knowledge_total[reference] = total
        prepared.append({"task_reference": reference, "field": field, "filename": filename, "content": payload})
    return prepared


def _validate_knowledge_bytes(content: bytes, filename: str) -> None:
    if PurePosixPath(filename).suffix.lower() != ".md":
        raise ValueError("文件类型不受支持，请上传 .md 文件")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("知识文件必须使用 UTF-8 编码") from error
    if not content.strip():
        raise ValueError("知识文件不能为空")


def _bind_files(
    definition: dict[str, Any], files: list[dict[str, Any]], *, workflow_id: int, team_id: int, username: str, domain: str, store
) -> None:
    knowledge: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        if item["field"] == TEMPLATE_FIELD:
            task = _task_for_field(definition, item["task_reference"], DOCUMENT_ATOM)
            if task is None:
                raise ValueError(_FILE_SPECS[TEMPLATE_FIELD]["invalid"])
            inputs = _input_parameters(task)
            inputs.pop("template_snapshot", None)
            inputs["template"] = store_uploaded_report_template(
                SimpleUploadedFile(item["filename"], item["content"]),
                workflow_id=workflow_id,
                workflow_version=0,
                team=team_id,
                username=username,
                domain=domain,
                store=store,
            )
            continue
        knowledge.setdefault(item["task_reference"], []).append(item)
    for reference, items in knowledge.items():
        task = _task_for_field(definition, reference, AGENT_ATOM)
        if task is None:
            raise ValueError(_FILE_SPECS[KNOWLEDGE_FIELD]["invalid"])
        inputs = _input_parameters(task)
        inputs["knowledge_files"] = [
            store_uploaded_agent_knowledge(
                SimpleUploadedFile(item["filename"], item["content"]),
                workflow_id=workflow_id,
                team=team_id,
                store=store,
            )
            for item in items
        ]


def _read_pack(upload, *, max_uncompressed_bytes: int) -> list[dict[str, Any]]:
    content = _read_upload(upload)
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        _reject("format", "上传文件不是有效的 ZIP 包")
    with archive:
        members = _validate_members(archive.infolist(), max_uncompressed_bytes=max_uncompressed_bytes)
        manifest = _read_manifest(archive, members)
        return [_load_workflow_entry(archive, item, members) for item in manifest]


def _read_upload(upload) -> bytes:
    read = getattr(upload, "read", None)
    if read is None:
        _reject("format", "上传文件不是有效的 ZIP 包")
    content = read(MAX_UNCOMPRESSED_BYTES + 1)
    if not isinstance(content, (bytes, bytearray)):
        _reject("format", "上传文件不是有效的 ZIP 包")
    if len(content) > MAX_UNCOMPRESSED_BYTES:
        _reject("size", "压缩包超过 200MB")
    return bytes(content)


def _validate_members(members, *, max_uncompressed_bytes: int) -> dict[str, Any]:
    if len(members) > MAX_PACK_MEMBERS:
        _reject("member_count", "压缩包文件数量异常")
    names = [member.filename for member in members]
    if len(names) != len(set(names)):
        _reject("path", "压缩包包含重复文件名")
    total = 0
    kept: dict[str, Any] = {}
    for member in members:
        filename = member.filename
        if filename.endswith("/"):
            if not _safe_member_name(filename.rstrip("/")):
                _reject("path", "压缩包包含非法路径")
            continue
        if not _safe_member_name(filename):
            _reject("path", "压缩包包含非法路径")
        if getattr(member, "flag_bits", 0) & 0x1:
            _reject("format", "压缩包无法读取")
        if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            _reject("format", "压缩包无法读取")
        mode = member.external_attr >> 16
        if mode & 0o170000 == 0o120000:
            _reject("path", "压缩包包含非法路径")
        if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
            _reject("compression", "压缩包压缩比异常")
        total += member.file_size
        if total > max_uncompressed_bytes:
            _reject("size", "压缩包解压后总大小超过 200MB")
        if _is_macos_junk(filename):
            continue
        kept[filename] = member
    return _unwrap_single_directory(kept)


def _read_manifest(archive: zipfile.ZipFile, members: dict[str, Any]) -> list[dict[str, Any]]:
    if "manifest.json" not in members:
        _reject("format", "不支持的流程压缩包")
    try:
        manifest = json.loads(_member_bytes(archive, members, "manifest.json"))
    except (json.JSONDecodeError, UnicodeDecodeError, RuntimeError, zipfile.BadZipFile):
        _reject("format", "不支持的流程压缩包")
    if not isinstance(manifest, dict):
        _reject("format", "不支持的流程压缩包")
    schema_version = manifest.get("schema_version")
    if manifest.get("format") != PACK_FORMAT or type(schema_version) is not int or schema_version != PACK_SCHEMA_VERSION:
        _reject("format", "不支持的流程压缩包")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        _reject("format", "压缩包里没有流程")
    for item in workflows:
        filename = item.get("file") if isinstance(item, dict) else None
        if not isinstance(filename, str) or not filename.startswith("workflows/") or not filename.endswith(".json"):
            _reject("path", "压缩包包含非法路径")
        if filename not in members or not _safe_member_name(filename):
            _reject("path", "压缩包包含非法路径")
    return workflows


def _load_workflow_entry(archive: zipfile.ZipFile, item: dict[str, Any], members: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(_member_bytes(archive, members, item["file"]))
    except (json.JSONDecodeError, UnicodeDecodeError, RuntimeError, zipfile.BadZipFile, KeyError):
        return {"name": str(item.get("name") or ""), "definition": None, "canvas_metadata": None, "files": []}
    if not isinstance(payload, dict):
        return {"name": "", "definition": None, "canvas_metadata": None, "files": []}
    records = []
    for record in payload.get("files") or []:
        if not isinstance(record, dict):
            records.append(record)
            continue
        path = record.get("path")
        member = members.get(path) if isinstance(path, str) else None
        if member is None:
            records.append({**record, "content": None})
            continue
        field = record.get("field")
        spec = _FILE_SPECS.get(field) if isinstance(field, str) else None
        limit = spec["max_bytes"] if spec else MAX_AGENT_KNOWLEDGE_FILE_BYTES
        if member.file_size > limit:
            records.append({**record, "content": b"", "oversized": True})
            continue
        try:
            content = _member_bytes(archive, members, path)
        except (RuntimeError, zipfile.BadZipFile, KeyError):
            content = None
        records.append({**record, "content": content})
    payload["files"] = records
    return payload


def _write_archive(packaged: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    manifest_items = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(packaged, start=1):
            filename = f"workflows/{index:04d}.json"
            archive.writestr(filename, item["encoded"])
            for path, content in item["files"]:
                archive.writestr(path, content)
            manifest_items.append({"file": filename, "name": item["payload"].get("name") or ""})
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": PACK_FORMAT,
                    "schema_version": PACK_SCHEMA_VERSION,
                    "workflows": manifest_items,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )
    return buffer.getvalue()


def _reject_unpacked_files(definition: dict[str, Any], files: list[dict[str, Any]]) -> None:
    packed = {(item["field"], item["task_reference"]) for item in files}
    for task in _walk_tasks(definition.get("tasks")):
        if not isinstance(task, dict):
            continue
        inputs = task.get("inputParameters")
        reference = task.get("taskReferenceName")
        if not isinstance(inputs, dict) or not isinstance(reference, str):
            continue
        if task.get("name") == DOCUMENT_ATOM and ("template" in inputs or "template_snapshot" in inputs):
            if (TEMPLATE_FIELD, reference) not in packed:
                raise ValueError(_FILE_SPECS[TEMPLATE_FIELD]["missing"])
        if task.get("name") == AGENT_ATOM and inputs.get("knowledge_files") not in (None, [], ""):
            if (KNOWLEDGE_FIELD, reference) not in packed:
                raise ValueError(_FILE_SPECS[KNOWLEDGE_FIELD]["missing"])


def _strip_packed_inputs(definition: dict[str, Any]) -> None:
    for task in _walk_tasks(definition.get("tasks")):
        if not isinstance(task, dict):
            continue
        inputs = task.get("inputParameters")
        if not isinstance(inputs, dict):
            continue
        if task.get("name") == DOCUMENT_ATOM:
            inputs.pop("template", None)
            inputs.pop("template_snapshot", None)
        elif task.get("name") == AGENT_ATOM and inputs.get("knowledge_files") not in (None, [], ""):
            inputs.pop("knowledge_files", None)


def _task_for_field(definition: dict[str, Any], reference: str, atom: str) -> dict[str, Any] | None:
    for task in _walk_tasks(definition.get("tasks")):
        if isinstance(task, dict) and task.get("name") == atom and task.get("taskReferenceName") == reference:
            return task
    return None


def _input_parameters(task: dict[str, Any]) -> dict[str, Any]:
    inputs = task.get("inputParameters")
    if not isinstance(inputs, dict):
        inputs = {}
        task["inputParameters"] = inputs
    return inputs


def _walk_tasks(tasks: Any):
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        yield task
        for key in ("loopOver", "defaultCase"):
            yield from _walk_tasks(task.get(key))
        for branch in (task.get("decisionCases") or {}).values():
            yield from _walk_tasks(branch)
        for branch in task.get("forkTasks") or []:
            yield from _walk_tasks(branch)


def _is_macos_junk(name: str) -> bool:
    return any(part == "__MACOSX" or part == ".DS_Store" or part.startswith("._") for part in PurePosixPath(name).parts)


def _unwrap_single_directory(members: dict[str, Any]) -> dict[str, Any]:
    """访达压缩整个文件夹时，会把文件夹名放在压缩包最外层。"""
    if "manifest.json" in members:
        return members
    prefixes = set()
    for name in members:
        parts = PurePosixPath(name).parts
        if len(parts) < 2:
            return members
        prefixes.add(parts[0])
    if len(prefixes) != 1:
        return members
    prefix = prefixes.pop()
    logical: dict[str, Any] = {}
    for name, member in members.items():
        stripped = str(PurePosixPath(name).relative_to(prefix))
        if stripped in logical:
            _reject("path", "压缩包包含重复文件名")
        logical[stripped] = member
    if "manifest.json" not in logical:
        return members
    return logical


def _member_bytes(archive: zipfile.ZipFile, members: dict[str, Any], logical_name: str) -> bytes:
    return archive.read(members[logical_name].filename)


def _safe_member_name(name: str) -> bool:
    if not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def _is_pack_file_path(path: Any) -> bool:
    return isinstance(path, str) and path.startswith("files/") and _safe_member_name(path)


def _safe_pack_filename(filename: str, content: bytes, *, suffixes: set[str], fallback_suffix: str, fallback_stem: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in suffixes:
        suffix = fallback_suffix
    stem = _FILE_NAME.sub("-", PurePosixPath(filename).stem).strip("-._")[:80] or fallback_stem
    digest = hashlib.sha256(content).hexdigest()[:8]
    return f"{stem}-{digest}{suffix}"


def _safe_reason(error: Exception) -> str:
    if isinstance(error, serializers.ValidationError):
        return _validation_text(error.detail)[:300]
    text = str(error).replace("\r", " ").replace("\n", " ").strip()
    return (text or "导入失败")[:300]


def _validation_text(detail: Any) -> str:
    if isinstance(detail, dict):
        parts = []
        for key, value in detail.items():
            text = value[0] if isinstance(value, list) and value else value
            parts.append(str(text) if key == "name" else f"{key}: {text}")
        return "；".join(parts)
    if isinstance(detail, list):
        return "；".join(str(item) for item in detail)
    return str(detail)


def _is_name_conflict(error: IntegrityError) -> bool:
    cause = getattr(error, "__cause__", None)
    diagnostics = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostics, "constraint_name", "")
    return constraint_name == "uq_workflow_active_name_team" or "uq_workflow_active_name_team" in str(error)


def _log_unexpected(event: str, error: Exception, *, failed_stage: str, workflow_id: int | None = None) -> None:
    safe_error = RuntimeError("workflow pack item failed")
    if workflow_id is None:
        logger.error(
            "event=%s failed_stage=%s error_type=%s",
            event,
            failed_stage,
            type(error).__name__,
            exc_info=(type(safe_error), safe_error, error.__traceback__),
        )
        return
    logger.error(
        "event=%s workflow_id=%s failed_stage=%s error_type=%s",
        event,
        workflow_id,
        failed_stage,
        type(error).__name__,
        exc_info=(type(safe_error), safe_error, error.__traceback__),
    )


def _reject(stage: str, message: str) -> NoReturn:
    logger.warning(
        "event=workflow_pack_rejected failed_stage=%s error_type=PackRejected",
        stage,
    )
    raise PackRejected(message)
