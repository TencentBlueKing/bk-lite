"""按团队幂等写入产品内置巡检流程（无 [TDD/BDD] 前缀）。"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.workflow_orchestration.models import Workflow, WorkflowVersion
from apps.workflow_orchestration.services.atom_registry import ensure_platform_atom
from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS, atom_catalog_payload
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.definitions import _walk_tasks, prepare_definition_for_publish
from apps.workflow_orchestration.services.demo_showcase import SHOWCASE_ATOM_KEYS, build_health_inspection_showcase_workflow
from apps.workflow_orchestration.services.demo_templates import seed_builtin_health_template_snapshot
from apps.workflow_orchestration.services.health_inspection_scripts import LINUX_HEALTH_SCRIPT, WINDOWS_HEALTH_SCRIPT
from apps.workflow_orchestration.services.orchestration_contract import validate_orchestration_metadata
from apps.workflow_orchestration.services.triggers import sync_published_triggers

logger = logging.getLogger(__name__)

BUILTIN_WINDOWS_KEY = "windows_health_docx"
BUILTIN_LINUX_KEY = "linux_health_xlsx"


def builtin_engine_name(team_id: int, key: str) -> str:
    return f"bklite_builtin_{key}_team_{team_id}"


def _build_builtin_items(*, team_id: int, channel_id: int, username: str) -> list[dict[str, Any]]:
    docx_snapshot = seed_builtin_health_template_snapshot("docx", team_id=team_id)
    xlsx_snapshot = seed_builtin_health_template_snapshot("xlsx", team_id=team_id)
    windows = build_health_inspection_showcase_workflow(
        team_id=team_id,
        channel_id=channel_id,
        username=username,
        fmt="docx",
        template_snapshot=docx_snapshot,
        script_type="powershell",
        script_content=WINDOWS_HEALTH_SCRIPT,
        operating_system="windows",
    )
    linux = build_health_inspection_showcase_workflow(
        team_id=team_id,
        channel_id=channel_id,
        username=username,
        fmt="xlsx",
        template_snapshot=xlsx_snapshot,
        script_type="shell",
        script_content=LINUX_HEALTH_SCRIPT,
        operating_system="linux",
    )
    windows["key"] = BUILTIN_WINDOWS_KEY
    linux["key"] = BUILTIN_LINUX_KEY
    windows["engine_name"] = builtin_engine_name(team_id, BUILTIN_WINDOWS_KEY)
    linux["engine_name"] = builtin_engine_name(team_id, BUILTIN_LINUX_KEY)
    windows["name"] = "Windows 主机巡检（Word）"
    linux["name"] = "Linux 主机巡检（Excel）"
    windows["description"] = "平台内置：选择 Windows 主机采集后生成 Word 巡检报告并通知。"
    linux["description"] = "平台内置：选择 Linux 主机采集后生成 Excel 巡检报告并通知。"
    return [windows, linux]


def ensure_builtin_health_workflows(
    *,
    team_id: int,
    username: str,
    domain: str = "domain.com",
    channel_id: int = 1,
    register_conductor: bool = True,
) -> list[Workflow]:
    """为单个团队幂等确保两条内置巡检流程已发布且启用。"""
    if team_id <= 0:
        raise ValueError("team_id 非法")
    platform_catalog = {item["key"]: item for item in atom_catalog_payload()}
    missing = set(SHOWCASE_ATOM_KEYS).difference(platform_catalog)
    if missing:
        raise RuntimeError(f"缺少平台原子: {', '.join(sorted(missing))}")

    prepared: list[dict[str, Any]] = []
    for item in _build_builtin_items(team_id=team_id, channel_id=channel_id, username=username):
        task_references = {
            task["taskReferenceName"] for task in _walk_tasks(item["definition"].get("tasks") or []) if isinstance(task.get("taskReferenceName"), str)
        }
        metadata = validate_orchestration_metadata(item["metadata"], task_references=task_references)
        definition = prepare_definition_for_publish(
            item["definition"],
            engine_name=item["engine_name"],
            version=1,
        )
        atom_keys = sorted({task["name"] for task in _walk_tasks(definition.get("tasks") or []) if task.get("type") == "SIMPLE"})
        prepared.append({**item, "definition": definition, "metadata": metadata, "atom_keys": atom_keys})

    if register_conductor:
        try:
            conductor = ConductorClient()
            conductor.register_task_definitions(TASK_DEFINITIONS)
            for item in prepared:
                conductor.register_workflow(item["definition"])
        except ConductorUnavailable as error:
            logger.warning("内置巡检流程 Conductor 注册跳过: %s", error)

    created: list[Workflow] = []
    with transaction.atomic():
        for atom_key in SHOWCASE_ATOM_KEYS:
            ensure_platform_atom(platform_catalog[atom_key], username=username, domain=domain)
        for item in prepared:
            workflow, _ = Workflow.all_objects.update_or_create(
                engine_name=item["engine_name"],
                defaults={
                    "name": item["name"],
                    "description": item["description"],
                    "team": [team_id],
                    "status": Workflow.Status.PUBLISHED,
                    "definition": item["definition"],
                    "canvas_metadata": item["metadata"],
                    "trigger_types": [trigger["trigger_type"] for trigger in item["metadata"]["trigger_nodes"]],
                    "current_version": 1,
                    "enabled": True,
                    "is_builtin": True,
                    "has_draft": False,
                    "draft_revision": 1,
                    "draft_base_version": 1,
                    "deleted_at": None,
                    "deleted_by": "",
                    "deleted_by_domain": "",
                    "created_by": username,
                    "updated_by": username,
                    "domain": domain,
                    "updated_by_domain": domain,
                },
            )
            WorkflowVersion.objects.update_or_create(
                workflow=workflow,
                version=1,
                defaults={
                    "definition": item["definition"],
                    "canvas_metadata": item["metadata"],
                    "resource_snapshot": {
                        "builtin": True,
                        "atoms": [{"key": key} for key in item["atom_keys"]],
                    },
                    "change_summary": {"summary": "平台内置巡检"},
                    "created_by": username,
                    "domain": domain,
                },
            )
            sync_published_triggers(workflow, item["metadata"], username=username, domain=domain)
            created.append(workflow)
    return created
