from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from django.core import signing
from django.core.files.base import ContentFile

from apps.workflow_orchestration.models import WorkflowExecution
from apps.workflow_orchestration.services.object_store import WorkflowObjectStore
from apps.workflow_orchestration.services.reports import MAX_TEMPLATE_BYTES, parse_report_template

REPORT_TEMPLATE_TOKEN_SALT = "workflow-orchestration.report-template.v1"
REPORT_TEMPLATE_TOKEN_TTL_SECONDS = 24 * 60 * 60


def store_uploaded_report_template(
    uploaded_file,
    *,
    workflow_id: int,
    workflow_version: int,
    team: int,
    username: str,
    domain: str,
    allowed_formats: tuple[str, ...] = ("docx", "xlsx"),
    max_bytes: int = MAX_TEMPLATE_BYTES,
    store=None,
) -> dict[str, Any]:
    filename = Path(str(getattr(uploaded_file, "name", "") or "")).name
    fmt = Path(filename).suffix.lower().lstrip(".")
    if fmt not in allowed_formats:
        raise ValueError(f"文件类型不受支持，请上传 {', '.join(f'.{item}' for item in allowed_formats)}")
    content = uploaded_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"文件超过 {max_bytes // (1024 * 1024)} MiB 限额")
    parsed = parse_report_template(content, fmt)
    safe_stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", Path(filename).stem).strip("-")[:80] or "report-template"
    object_key = f"workflow-orchestration/templates/uploads/{team}/{uuid.uuid4().hex}/{safe_stem}.{parsed.format}"
    (store or WorkflowObjectStore()).put(object_key, ContentFile(content, name=filename))
    payload = {
        "workflow_id": int(workflow_id),
        "workflow_version": int(workflow_version),
        "team": int(team),
        "username": username,
        "domain": domain,
        "object_key": object_key,
        "format": parsed.format,
        "sha256": parsed.sha256,
        "size": parsed.size,
        "name": filename,
        "filename_prefix": safe_stem,
    }
    return {
        "kind": "uploaded",
        "name": filename,
        "format": parsed.format,
        "size": parsed.size,
        "placeholders": list(parsed.placeholders),
        "token": signing.dumps(payload, salt=REPORT_TEMPLATE_TOKEN_SALT, compress=True),
    }


def resolve_uploaded_report_template(reference: Any, execution: WorkflowExecution) -> dict[str, Any]:
    if not isinstance(reference, dict) or reference.get("kind") != "uploaded":
        raise ValueError("报告模板引用非法")
    token = reference.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("报告模板引用缺少凭证")
    try:
        payload = signing.loads(
            token,
            salt=REPORT_TEMPLATE_TOKEN_SALT,
            max_age=REPORT_TEMPLATE_TOKEN_TTL_SECONDS,
        )
    except signing.SignatureExpired as error:
        raise ValueError("上传的报告模板已过期，请重新上传") from error
    except signing.BadSignature as error:
        raise ValueError("报告模板引用无效") from error
    team = execution.team[0] if isinstance(execution.team, list) and len(execution.team) == 1 else None
    if (
        not isinstance(payload, dict)
        or payload.get("workflow_id") != execution.workflow_id
        or payload.get("workflow_version") != execution.workflow_version
        or payload.get("team") != team
        or payload.get("username") != execution.started_by
        or payload.get("domain") != execution.domain
    ):
        raise ValueError("报告模板引用与当前执行不匹配")
    object_key = str(payload.get("object_key") or "")
    fmt = str(payload.get("format") or "")
    sha256 = str(payload.get("sha256") or "")
    size = payload.get("size")
    if (
        not object_key.startswith(f"workflow-orchestration/templates/uploads/{team}/")
        or fmt not in {"docx", "xlsx"}
        or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= MAX_TEMPLATE_BYTES
    ):
        raise ValueError("报告模板引用内容非法")
    return payload


def snapshot_from_upload_token(token: str) -> dict[str, Any]:
    if not isinstance(token, str) or not token:
        raise ValueError("报告模板引用缺少凭证")
    try:
        payload = signing.loads(token, salt=REPORT_TEMPLATE_TOKEN_SALT, max_age=REPORT_TEMPLATE_TOKEN_TTL_SECONDS)
    except signing.SignatureExpired as error:
        raise ValueError("上传的报告模板已过期，请重新上传后再发布") from error
    except signing.BadSignature as error:
        raise ValueError("报告模板引用无效") from error
    object_key = str(payload.get("object_key") or "") if isinstance(payload, dict) else ""
    fmt = str(payload.get("format") or "") if isinstance(payload, dict) else ""
    sha256 = str(payload.get("sha256") or "") if isinstance(payload, dict) else ""
    size = payload.get("size") if isinstance(payload, dict) else None
    if (
        not object_key.startswith("workflow-orchestration/templates/")
        or fmt not in {"docx", "xlsx"}
        or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        or isinstance(size, bool)
        or not isinstance(size, int)
    ):
        raise ValueError("报告模板引用内容非法")
    return {
        "object_key": object_key,
        "format": fmt,
        "sha256": sha256,
        "size": size,
        "filename_prefix": str(payload.get("filename_prefix") or "report"),
    }


def _document_tasks(tasks: Any):
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        yield task
        for key in ("loopOver", "defaultCase"):
            yield from _document_tasks(task.get(key))
        for branch in (task.get("decisionCases") or {}).values():
            yield from _document_tasks(branch)
        for branch in task.get("forkTasks") or []:
            yield from _document_tasks(branch)


def _valid_template_snapshot(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    size = value.get("size")
    return (
        str(value.get("object_key") or "").startswith("workflow-orchestration/templates/")
        and value.get("format") in {"docx", "xlsx"}
        and re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256") or "")) is not None
        and isinstance(size, int)
        and not isinstance(size, bool)
        and 0 < size <= MAX_TEMPLATE_BYTES
    )


def freeze_document_templates(definition: dict[str, Any]) -> dict[str, Any]:
    for task in _document_tasks(definition.get("tasks")):
        if task.get("name") != "bklite_document_render":
            continue
        inputs = task.get("inputParameters")
        if not isinstance(inputs, dict):
            raise ValueError("文档生成节点发布前必须上传 Word 或 Excel 模板")
        template = inputs.get("template")
        if isinstance(template, dict) and template.get("kind") == "uploaded":
            inputs["template_snapshot"] = snapshot_from_upload_token(str(template.get("token") or ""))
            inputs.pop("template", None)
        elif not _valid_template_snapshot(inputs.get("template_snapshot")):
            raise ValueError("文档生成节点发布前必须上传 Word 或 Excel 模板")
    return definition


def verify_template_content(content: bytes, snapshot: dict[str, Any]) -> None:
    if len(content) != snapshot["size"] or hashlib.sha256(content).hexdigest() != snapshot["sha256"]:
        raise ValueError("报告模板内容校验失败")
