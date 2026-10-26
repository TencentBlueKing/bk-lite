"""按团队幂等写入产品内置巡检流程（无 [TDD/BDD] 前缀）。"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.workflow.models import Workflow, WorkflowExecution, WorkflowVersion
from apps.workflow.services.atom_registry import ensure_platform_atom
from apps.workflow.services.atoms import TASK_DEFINITIONS, atom_catalog_payload
from apps.workflow.services.conductor import ConductorClient, ConductorUnavailable, _comparable_workflow_definition, workflow_definition_digest
from apps.workflow.services.definitions import _walk_tasks, prepare_definition_for_publish
from apps.workflow.services.demo_showcase import SHOWCASE_ATOM_KEYS, build_health_inspection_showcase_workflow
from apps.workflow.services.demo_templates import seed_builtin_health_template_snapshot
from apps.workflow.services.health_inspection_scripts import LINUX_HEALTH_SCRIPT, WINDOWS_HEALTH_SCRIPT
from apps.workflow.services.orchestration_contract import validate_orchestration_metadata
from apps.workflow.services.triggers import sync_published_triggers

logger = logging.getLogger(__name__)

BUILTIN_WINDOWS_KEY = "windows_health_docx"
BUILTIN_LINUX_KEY = "linux_health_xlsx"
# 与运行时 __system.actor_name（= started_by 用户名）对齐；通知原子会把用户名解析成收件人。
BUILTIN_EXECUTOR_RECIPIENT = "${workflow.input.__system.actor_name}"


def builtin_engine_name(team_id: int, key: str) -> str:
    return f"bklite_builtin_{key}_team_{team_id}"


def resolve_team_email_channel_id(team_id: int, preferred_channel_id: int | None = None) -> int | None:
    """按与前端下拉相同的 name,id 排序取第一项 email 渠道；没有则返回 None。"""
    from apps.system_mgmt.models import Channel, ChannelChoices

    if preferred_channel_id is not None:
        preferred = Channel.objects.filter(id=preferred_channel_id).first()
        if preferred is not None and preferred.channel_type == ChannelChoices.EMAIL and team_id in list(preferred.team or []):
            return int(preferred.id)
    for channel in Channel.objects.filter(channel_type=ChannelChoices.EMAIL).order_by("name", "id"):
        if team_id in list(channel.team or []):
            return int(channel.id)
    return None


def _build_builtin_items(*, team_id: int, channel_id: int | None, username: str) -> list[dict[str, Any]]:
    docx_snapshot = seed_builtin_health_template_snapshot("docx", team_id=team_id)
    xlsx_snapshot = seed_builtin_health_template_snapshot("xlsx", team_id=team_id)
    recipients = [BUILTIN_EXECUTOR_RECIPIENT]
    windows = build_health_inspection_showcase_workflow(
        team_id=team_id,
        channel_id=channel_id,
        username=username,
        fmt="docx",
        template_snapshot=docx_snapshot,
        script_type="powershell",
        script_content=WINDOWS_HEALTH_SCRIPT,
        operating_system="windows",
        recipients=recipients,
    )
    linux = build_health_inspection_showcase_workflow(
        team_id=team_id,
        channel_id=channel_id,
        username=username,
        fmt="xlsx",
        template_snapshot=xlsx_snapshot,
        script_type="python",
        script_content=LINUX_HEALTH_SCRIPT,
        operating_system="linux",
        recipients=recipients,
    )
    windows["key"] = BUILTIN_WINDOWS_KEY
    linux["key"] = BUILTIN_LINUX_KEY
    windows["engine_name"] = builtin_engine_name(team_id, BUILTIN_WINDOWS_KEY)
    linux["engine_name"] = builtin_engine_name(team_id, BUILTIN_LINUX_KEY)
    windows["name"] = "Windows 主机巡检（Word）"
    linux["name"] = "Linux 主机巡检（Excel）"
    windows["description"] = "选择 Windows 主机采集后生成 Word 巡检报告并通知。"
    linux["description"] = "选择 Linux 主机采集后生成 Excel 巡检报告并通知。"
    return [windows, linux]


def _same_published_body(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return workflow_definition_digest(_comparable_workflow_definition(left)) == workflow_definition_digest(_comparable_workflow_definition(right))


def _publish_builtin_definition(raw_definition: dict[str, Any], *, engine_name: str) -> dict[str, Any]:
    """内容不变时复用当前版本；脚本或模板变了就登记下一个不可变版本。"""
    existing = Workflow.all_objects.filter(engine_name=engine_name).only("current_version", "definition").first()
    version = existing.current_version if existing is not None and existing.current_version else 1
    definition = prepare_definition_for_publish(raw_definition, engine_name=engine_name, version=version)
    if existing is None or not existing.current_version or _same_published_body(definition, existing.definition or {}):
        return definition
    return prepare_definition_for_publish(raw_definition, engine_name=engine_name, version=version + 1)


def collapse_builtin_workflow_versions(
    workflow_model=Workflow,
    version_model=WorkflowVersion,
    execution_model=WorkflowExecution,
) -> int:
    """把已发布的内置流程收成一条 v1，保留当前定义，删掉更高版本。"""
    collapsed = 0
    published = workflow_model.objects.filter(is_builtin=True).exclude(current_version=0)
    for workflow in published:
        definition = dict(workflow.definition or {})
        definition["version"] = 1
        current_snapshot = version_model.objects.filter(workflow_id=workflow.pk, version=workflow.current_version).first()
        version_model.objects.filter(workflow_id=workflow.pk).exclude(version=1).delete()
        version_model.objects.update_or_create(
            workflow_id=workflow.pk,
            version=1,
            defaults={
                "definition": definition,
                "canvas_metadata": workflow.canvas_metadata or {},
                "resource_snapshot": getattr(current_snapshot, "resource_snapshot", None) or {"builtin": True},
                "change_summary": getattr(current_snapshot, "change_summary", None) or {"summary": "平台内置巡检"},
                "created_by": workflow.created_by or "",
                "domain": workflow.domain or "domain.com",
            },
        )
        workflow_model.objects.filter(pk=workflow.pk).update(
            definition=definition,
            current_version=1,
            draft_base_version=1,
        )
        execution_model.objects.filter(workflow_id=workflow.pk).exclude(workflow_version=1).update(workflow_version=1)
        collapsed += 1
    return collapsed


def ensure_builtin_health_workflows(
    *,
    team_id: int,
    username: str,
    domain: str = "domain.com",
    channel_id: int | None = None,
    register_conductor: bool = True,
) -> list[Workflow]:
    """为单个团队幂等确保两条内置巡检流程已发布且启用。"""
    if team_id <= 0:
        raise ValueError("team_id 非法")
    platform_catalog = {item["key"]: item for item in atom_catalog_payload()}
    missing = set(SHOWCASE_ATOM_KEYS).difference(platform_catalog)
    if missing:
        raise RuntimeError(f"缺少平台原子: {', '.join(sorted(missing))}")

    resolved_channel_id = resolve_team_email_channel_id(team_id, channel_id)
    if resolved_channel_id is None:
        logger.warning("团队 %s 下没有可用的邮件通知渠道，内置巡检通知方式将留空", team_id)

    prepared: list[dict[str, Any]] = []
    for item in _build_builtin_items(
        team_id=team_id,
        channel_id=resolved_channel_id,
        username=username,
    ):
        task_references = {
            task["taskReferenceName"] for task in _walk_tasks(item["definition"].get("tasks") or []) if isinstance(task.get("taskReferenceName"), str)
        }
        metadata = validate_orchestration_metadata(item["metadata"], task_references=task_references)
        definition = _publish_builtin_definition(item["definition"], engine_name=item["engine_name"])
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
                    "current_version": item["definition"]["version"],
                    "enabled": True,
                    "is_builtin": True,
                    "has_draft": False,
                    "draft_revision": 1,
                    "draft_base_version": item["definition"]["version"],
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
                version=item["definition"]["version"],
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
