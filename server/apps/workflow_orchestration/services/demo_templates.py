from __future__ import annotations

import hashlib
from pathlib import Path

from django.core.files.base import ContentFile

from apps.workflow_orchestration.services.object_store import WorkflowObjectStore
from apps.workflow_orchestration.services.reports import parse_report_template

BUILTIN_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "web/public/workflow-orchestration/templates"


def builtin_health_template_path(fmt: str) -> Path:
    normalized = str(fmt or "").lower()
    if normalized not in {"docx", "xlsx"}:
        raise ValueError("演示模板格式只能是 docx 或 xlsx")
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
