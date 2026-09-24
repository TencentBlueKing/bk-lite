from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.workflow_orchestration.atom_packages.runtime import trusted_execution_scope
from apps.workflow_orchestration.models import ExecutionArtifact, WorkflowExecution
from apps.workflow_orchestration.services.object_store import WorkflowObjectStore
from apps.workflow_orchestration.services.report_template_inputs import resolve_uploaded_report_template, verify_template_content
from apps.workflow_orchestration.services.reports import missing_template_fields, parse_report_template, render_report


def _template_content(inputs: dict[str, Any], execution: WorkflowExecution, store) -> tuple[bytes, str, str]:
    runtime_template = inputs.get("template")
    if isinstance(runtime_template, dict) and runtime_template.get("kind") == "uploaded":
        snapshot = resolve_uploaded_report_template(runtime_template, execution)
        content = store.get(snapshot["object_key"])[0]
        verify_template_content(content, snapshot)
        return content, snapshot["format"], snapshot["filename_prefix"]
    snapshot = inputs.get("template_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict):
            raise ValueError("报告模板快照非法")
        object_key = str(snapshot.get("object_key") or "")
        fmt = str(snapshot.get("format") or "").lower()
        if not object_key.startswith("workflow-orchestration/templates/") or fmt not in {"docx", "xlsx"}:
            raise ValueError("报告模板快照非法")
        content = store.get(object_key)[0]
        verify_template_content(content, snapshot)
        filename_prefix = str(snapshot.get("filename_prefix") or "report")
        return content, fmt, filename_prefix
    raise ValueError("请上传 Word 或 Excel 报告模板")


def _merge_report_data(primary: dict[str, Any], additional: Any) -> dict[str, Any]:
    """合并多份作业输出，供多主机 / 多操作系统巡检共用同一份报告模板。"""
    if additional in (None, ""):
        return primary
    if not isinstance(additional, dict):
        raise ValueError("追加文档数据必须是 JSON 对象")
    results = list(primary.get("results") or []) + list(additional.get("results") or [])
    succeeded = sum(1 for item in results if str(item.get("status") or "").upper() == "SUCCESS")
    job_task_ids = list(primary.get("job_task_ids") or []) + list(additional.get("job_task_ids") or [])
    return {
        **primary,
        "results": results,
        "summary": {"total": len(results), "succeeded": succeeded, "failed": len(results) - succeeded},
        "job_task_ids": job_task_ids,
    }


def render_document_atom(inputs: dict[str, Any], *, store=None) -> dict[str, Any]:
    execution_id, team = trusted_execution_scope(inputs)
    execution = WorkflowExecution.objects.get(pk=UUID(str(execution_id)))
    if execution.team != [team]:
        raise ValueError("执行组织与文档组织不一致")
    object_store = store or WorkflowObjectStore()
    content, fmt, filename_prefix = _template_content(inputs, execution, object_store)
    if fmt not in {"docx", "xlsx"}:
        raise ValueError("文档格式只能是 docx 或 xlsx")
    data = inputs.get("data")
    if not isinstance(data, dict):
        raise ValueError("文档数据必须是 JSON 对象")
    data = _merge_report_data(data, inputs.get("additional_data"))
    document = render_report(content, fmt, data)
    parsed = parse_report_template(content, fmt)
    warnings = missing_template_fields(parsed, data)
    digest = hashlib.sha256(document).hexdigest()
    filename = f"{filename_prefix}-{timezone.localtime():%Y%m%d-%H%M%S}.{fmt}"
    object_key = f"workflow-orchestration/executions/{execution.id}/{digest[:16]}/{filename}"
    object_store.put(object_key, ContentFile(document, name=filename))
    artifact = ExecutionArtifact.objects.create(
        execution=execution,
        team=[team],
        format=fmt,
        object_key=object_key,
        filename=filename,
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if fmt == "docx"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        sha256=digest,
        size=len(document),
        summary=data.get("summary", {}),
        expires_at=timezone.now() + timedelta(hours=24 if execution.mode == WorkflowExecution.Mode.DEBUG else 30 * 24),
        created_by="system",
        updated_by="system",
    )
    return {
        "artifact": {"id": str(artifact.id), "filename": filename, "format": fmt, "size": len(document)},
        "field_warnings": warnings,
    }


def execute(inputs: dict[str, Any]) -> dict[str, Any]:
    return render_document_atom(inputs)
