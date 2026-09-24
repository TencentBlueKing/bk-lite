from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from django.core import signing
from django.core.files.base import ContentFile

from apps.workflow_orchestration.services.object_store import WorkflowObjectStore

AGENT_KNOWLEDGE_TOKEN_SALT = "workflow-orchestration.agent-knowledge.v1"
MAX_AGENT_KNOWLEDGE_FILE_BYTES = 10 * 1024 * 1024
MAX_AGENT_KNOWLEDGE_FILES = 10
MAX_AGENT_KNOWLEDGE_TOTAL_BYTES = 20 * 1024 * 1024


def store_uploaded_agent_knowledge(
    uploaded_file,
    *,
    workflow_id: int,
    team: int,
    store=None,
) -> dict[str, Any]:
    filename = Path(str(getattr(uploaded_file, "name", "") or "")).name
    if Path(filename).suffix.lower() != ".md":
        raise ValueError("文件类型不受支持，请上传 .md 文件")
    content = uploaded_file.read(MAX_AGENT_KNOWLEDGE_FILE_BYTES + 1)
    if len(content) > MAX_AGENT_KNOWLEDGE_FILE_BYTES:
        raise ValueError("文件超过 10 MiB 限额")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("知识文件必须使用 UTF-8 编码") from error
    if not content.strip():
        raise ValueError("知识文件不能为空")

    safe_stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", Path(filename).stem).strip("-")[:80] or "knowledge"
    object_key = f"workflow-orchestration/knowledge/uploads/{team}/{workflow_id}/{uuid.uuid4().hex}/{safe_stem}.md"
    (store or WorkflowObjectStore()).put(object_key, ContentFile(content, name=filename))
    payload = {
        "workflow_id": int(workflow_id),
        "team": int(team),
        "object_key": object_key,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "name": filename,
    }
    return {
        "kind": "workflow_agent_knowledge",
        "name": filename,
        "format": "md",
        "size": len(content),
        "token": signing.dumps(payload, salt=AGENT_KNOWLEDGE_TOKEN_SALT, compress=True),
    }


def resolve_uploaded_agent_knowledge(
    references: Any,
    *,
    workflow_id: Any,
    team: int,
    store=None,
) -> list[dict[str, str]]:
    if references in (None, []):
        return []
    if not isinstance(references, list) or not 1 <= len(references) <= MAX_AGENT_KNOWLEDGE_FILES:
        raise ValueError(f"知识文件必须是 1 到 {MAX_AGENT_KNOWLEDGE_FILES} 个受控上传引用")
    try:
        expected_workflow_id = int(workflow_id)
    except (TypeError, ValueError) as error:
        raise ValueError("流程标识非法") from error

    object_store = store or WorkflowObjectStore()
    resolved: list[dict[str, str]] = []
    total_bytes = 0
    for reference in references:
        if not isinstance(reference, dict) or reference.get("kind") != "workflow_agent_knowledge":
            raise ValueError("知识文件引用非法")
        token = reference.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("知识文件引用缺少凭证")
        try:
            payload = signing.loads(token, salt=AGENT_KNOWLEDGE_TOKEN_SALT)
        except signing.BadSignature as error:
            raise ValueError("知识文件引用无效") from error
        object_key = str(payload.get("object_key") or "") if isinstance(payload, dict) else ""
        size = payload.get("size") if isinstance(payload, dict) else None
        sha256 = str(payload.get("sha256") or "") if isinstance(payload, dict) else ""
        if (
            not isinstance(payload, dict)
            or payload.get("workflow_id") != expected_workflow_id
            or payload.get("team") != team
            or not object_key.startswith(f"workflow-orchestration/knowledge/uploads/{team}/{expected_workflow_id}/")
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 < size <= MAX_AGENT_KNOWLEDGE_FILE_BYTES
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        ):
            raise ValueError("知识文件引用内容非法")
        total_bytes += size
        if total_bytes > MAX_AGENT_KNOWLEDGE_TOTAL_BYTES:
            raise ValueError("知识文件总大小超过 20 MiB 限额")
        content, _, _ = object_store.get(object_key)
        if len(content) != size or hashlib.sha256(content).hexdigest() != sha256:
            raise ValueError("知识文件内容校验失败")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("知识文件内容不是 UTF-8 文本") from error
        resolved.append({"name": str(payload.get("name") or "knowledge.md")[:255], "content": text})
    return resolved
