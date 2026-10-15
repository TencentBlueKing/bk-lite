from __future__ import annotations

import hashlib
from pathlib import Path

from django.core.files.base import ContentFile

from apps.workflow_orchestration.services.object_store import WorkflowObjectStore
from apps.workflow_orchestration.services.reports import parse_report_template

# 与 Server 镜像同包发布，禁止再依赖仓库根下的 web/public。
BUILTIN_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "assets" / "templates"
SAMPLE_TEMPLATE_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def builtin_sample_template_api_path(fmt: str) -> str:
    normalized = _normalize_template_format(fmt)
    return f"/workflow_orchestration/api/workflows/sample-templates/{normalized}/"


def builtin_health_template_path(fmt: str) -> Path:
    normalized = _normalize_template_format(fmt)
    path = BUILTIN_TEMPLATE_DIR / f"health-inspection-example.{normalized}"
    if not path.is_file():
        raise FileNotFoundError(f"缺少内置健康巡检模板: {path.name}")
    return path


def seed_builtin_health_template_snapshot(
    fmt: str,
    *,
    team_id: int,
    store: WorkflowObjectStore | None = None,
) -> dict:
    """把仓库内置模板写入对象存储，供演示流程发布快照使用。"""
    path = builtin_health_template_path(fmt)
    content = path.read_bytes()
    parsed = parse_report_template(content, fmt)
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"workflow-orchestration/templates/demo/team-{int(team_id)}/" f"health-inspection-example-{digest[:16]}.{parsed.format}"
    object_store = store or WorkflowObjectStore()
    object_store.put(object_key, ContentFile(content, name=path.name))
    return {
        "object_key": object_key,
        "format": parsed.format,
        "sha256": digest,
        "size": len(content),
        "filename_prefix": f"health-inspection-{parsed.format}",
    }


def _normalize_template_format(fmt: str) -> str:
    normalized = str(fmt or "").lower()
    if normalized not in {"docx", "xlsx"}:
        raise ValueError("演示模板格式只能是 docx 或 xlsx")
    return normalized
