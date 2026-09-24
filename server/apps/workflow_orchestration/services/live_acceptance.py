from __future__ import annotations

import copy
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.rpc.job_mgmt import JobMgmt
from apps.rpc.node_mgmt import NodeMgmt
from apps.workflow_orchestration.models import AtomExecution, Workflow, WorkflowExecution, WorkflowVersion
from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.definitions import prepare_definition_for_publish
from apps.workflow_orchestration.services.demo_templates import seed_builtin_health_template_snapshot
from apps.workflow_orchestration.services.executions import apply_remote_execution
from apps.workflow_orchestration.services.runtime import start_execution

LIVE_PREFIX = "[LIVE]"
SERVER_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ScenarioResult:
    key: str
    title: str
    status: str
    detail: str = ""
    workflow_id: int | None = None
    execution_id: str | None = None
    conductor_workflow_id: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pump_worker_once(*, timeout_seconds: int = 25) -> None:
    """推进一轮 Worker 轮询，避免依赖外部常驻进程是否在线。

    作业原子会同步阻塞等待平台终态；子进程超时必须覆盖该等待窗口，
    否则中途杀进程会留下带租约的 RUNNING AtomExecution，后续 --once
    只续约不重跑，流程会卡在 SCHEDULED/RUNNING。
    """
    env = dict(os.environ)
    env.setdefault("CONDUCTOR_BASE_URL", "http://127.0.0.1:8091/api")
    env["PYTHONUNBUFFERED"] = "1"
    try:
        subprocess.run(
            [sys.executable, "manage.py", "run_workflow_worker", "--once"],
            cwd=str(SERVER_ROOT),
            env=env,
            timeout=max(10, timeout_seconds),
            check=False,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        return


def _wait_execution(
    execution: WorkflowExecution,
    *,
    client: ConductorClient,
    timeout_seconds: int,
    pump_worker: bool = True,
) -> WorkflowExecution:
    deadline = time.monotonic() + max(5, timeout_seconds)
    remote = None
    # 已有常驻 worker 时不要再起 --once，避免抢租约导致重复提交作业。
    external_worker = os.getenv("WORKFLOW_WORKER_EXTERNAL", "").strip() in {"1", "true", "TRUE"}
    while time.monotonic() < deadline:
        if pump_worker and not external_worker:
            # 剩余窗口 + 缓冲，覆盖 job wait(timeout+60) 的同步阻塞。
            remaining = max(15, int(deadline - time.monotonic()) + 90)
            _pump_worker_once(timeout_seconds=remaining)
        if not execution.conductor_workflow_id:
            break
        remote = client.get_execution(execution.conductor_workflow_id)
        status = str(remote.get("status") or "")
        if status in {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "TIMED_OUT", "TERMINATED"}:
            apply_remote_execution(execution, remote)
            execution.refresh_from_db()
            return execution
        time.sleep(0.2)
    if remote is not None:
        apply_remote_execution(execution, remote)
        execution.refresh_from_db()
    return execution


def _register_live_workflow(
    *,
    team_id: int,
    username: str,
    domain: str,
    key: str,
    name: str,
    description: str,
    definition: dict[str, Any],
    metadata: dict[str, Any],
    client: ConductorClient,
) -> Workflow:
    suffix = uuid4().hex[:8]
    engine_name = f"bklite_live_{key}_{team_id}_{suffix}"[:100]
    published = prepare_definition_for_publish(definition, engine_name=engine_name, version=1)
    client.register_workflow(published)
    workflow = Workflow.all_objects.create(
        engine_name=engine_name,
        name=f"{LIVE_PREFIX} {name} {suffix}",
        description=description,
        team=[team_id],
        status=Workflow.Status.PUBLISHED,
        definition=published,
        canvas_metadata=metadata,
        trigger_types=["FORM"],
        current_version=1,
        enabled=True,
        has_draft=False,
        draft_revision=1,
        draft_base_version=1,
        created_by=username,
        updated_by=username,
        domain=domain,
        updated_by_domain=domain,
    )
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=published,
        canvas_metadata=metadata,
        resource_snapshot={"live": True, "source": "live-acceptance"},
        change_summary={"summary": "本地真实闭环验收"},
        created_by=username,
        domain=domain,
    )
    return workflow


def _base_metadata(title: str) -> dict[str, Any]:
    return {
        "control_flow_mode": "EDGES",
        "trigger_nodes": [
            {
                "id": "trigger_form",
                "name": "验收表单",
                "trigger_type": "FORM",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                },
                "config": {},
            }
        ],
        "return_nodes": [],
        "positions": {"trigger_form": {"x": 20, "y": 200}},
        "node_titles": {},
        "edges": [],
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": True},
        "data_contract": {
            "version": 1,
            "systemContextVersion": 1,
            "inputs": [],
            "constants": [],
            "outputs": [],
        },
        "risk_summary": {"level": "low", "description": title},
    }


def _sample_job_envelope() -> dict[str, Any]:
    collected_at = timezone.now().isoformat()
    return {
        "results": [
            {
                "target": {
                    "id": "manual:1",
                    "source": "job_mgmt",
                    "source_id": 1,
                    "name": "Windows 巡检主机",
                    "ip": "10.10.90.120",
                    "operating_system": "windows",
                },
                "status": "SUCCESS",
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "data": {
                    "collected_at": collected_at,
                    "metrics": [
                        {
                            "category": "CPU",
                            "object_type": "processor",
                            "object_name": "CPU Total",
                            "dimensions": "core=all",
                            "metric_name": "usage_percent",
                            "value": 42,
                            "unit": "%",
                            "warning_threshold": 80,
                            "critical_threshold": 90,
                            "health_status": "NORMAL",
                            "collected_at": collected_at,
                            "detail": "CPU 总使用率",
                        }
                    ],
                    "metric_count": 1,
                    "critical": [],
                    "warning": [],
                    "normal": [],
                    "critical_count": 0,
                    "warning_count": 0,
                    "normal_count": 1,
                    "conclusion": "健康",
                },
                "error": None,
            }
        ],
        "summary": {"total": 1, "succeeded": 1, "failed": 0},
    }


def run_document_render_scenario(
    *,
    fmt: str,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
) -> ScenarioResult:
    key = f"document_{fmt}"
    title = f"文档生成 {fmt.upper()}"
    try:
        snapshot = seed_builtin_health_template_snapshot(fmt, team_id=team_id)
        definition = {
            "name": "live_document_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["team", "actor", "execution_id", "data"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "bklite_document_render",
                    "taskReferenceName": "report",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "data": "${workflow.input.data}",
                        "template_snapshot": snapshot,
                        "execution_id": "${workflow.input.execution_id}",
                        "team": "${workflow.input.team}",
                    },
                }
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [{"id": "trigger-report", "source": "trigger_form", "target": "report"}]
        metadata["positions"]["report"] = {"x": 280, "y": 200}
        metadata["node_titles"]["report"] = title
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description=f"真实渲染内置 {fmt} 模板（数据由验收命令显式传入，不冒充作业结果）",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={"data": _sample_job_envelope()},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        execution = _wait_execution(execution, client=client, timeout_seconds=timeout_seconds)
        ok = execution.status == WorkflowExecution.Status.SUCCEEDED
        artifact = (execution.output or {}).get("report") or (execution.output or {}).get("artifact")
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok else "FAILED",
            detail="" if ok else (execution.error_message or execution.status),
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={
                "execution_status": execution.status,
                "output_keys": sorted((execution.output or {}).keys()),
                "artifact": artifact,
                "note": "使用显式 JSON 验收文档原子；不代表作业执行已成功",
            },
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_http_request_scenario(
    *,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
    url: str = "https://example.com/",
) -> ScenarioResult:
    key = "http_request"
    title = "HTTP 请求"
    try:
        definition = {
            "name": "live_http_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["team", "actor", "execution_id"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "bklite_http_request",
                    "taskReferenceName": "lookup",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "method": "GET",
                        "url": url,
                        "timeout": 15,
                        "response_format": "TEXT",
                        "success_status_codes": [],
                        "team": "${workflow.input.team}",
                    },
                }
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [{"id": "trigger-http", "source": "trigger_form", "target": "lookup"}]
        metadata["positions"]["lookup"] = {"x": 280, "y": 200}
        metadata["node_titles"]["lookup"] = title
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description=f"真实 GET {url}",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        execution = _wait_execution(execution, client=client, timeout_seconds=timeout_seconds)
        ok = execution.status == WorkflowExecution.Status.SUCCEEDED
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok else "FAILED",
            detail="" if ok else (execution.error_message or execution.status),
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={"execution_status": execution.status, "url": url, "output": execution.output},
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_notification_scenario(
    *,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
    channel_id: int,
) -> ScenarioResult:
    key = "notification"
    title = "对外通知"
    try:
        definition = {
            "name": "live_notification_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["team", "actor", "execution_id"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "bklite_notification",
                    "taskReferenceName": "notify",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "notification_type": "EMAIL",
                        "channel_id": channel_id,
                        "recipients": [username],
                        "title": "编排中心本地真实闭环通知验收",
                        "body": "这是一次真实投递验收，失败会如实记录。",
                        "team": "${workflow.input.team}",
                        "execution_id": "${workflow.input.execution_id}",
                        "task_reference": "notify",
                    },
                }
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [{"id": "trigger-notify", "source": "trigger_form", "target": "notify"}]
        metadata["positions"]["notify"] = {"x": 280, "y": 200}
        metadata["node_titles"]["notify"] = title
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description="真实调用系统通知渠道投递",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        execution = _wait_execution(execution, client=client, timeout_seconds=timeout_seconds)
        ok = execution.status == WorkflowExecution.Status.SUCCEEDED
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok else "FAILED",
            detail="" if ok else (execution.error_message or execution.status),
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={"execution_status": execution.status, "channel_id": channel_id, "output": execution.output},
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_approval_scenario(
    *,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
) -> ScenarioResult:
    key = "approval"
    title = "人工审批"
    try:
        definition = {
            "name": "live_approval_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["team", "actor", "execution_id", "change_title"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "manual_approval",
                    "taskReferenceName": "approve_change",
                    "type": "HUMAN",
                    "inputParameters": {
                        "interactionType": "APPROVAL",
                        "title": "本地真实闭环审批",
                        "description": "请在页面确认或拒绝。",
                        "candidates": [username],
                        "publicContext": {"change_title": "${workflow.input.change_title}"},
                    },
                },
                {
                    "name": "approval_decision",
                    "taskReferenceName": "approval_decision",
                    "type": "SWITCH",
                    "inputParameters": {"decision": "${approve_change.output.approved}"},
                    "evaluatorType": "value-param",
                    "expression": "decision",
                    "decisionCases": {"true": [], "false": []},
                    "defaultCase": [],
                },
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [
            {"id": "trigger-approval", "source": "trigger_form", "target": "approve_change"},
            {"id": "approval-decision", "source": "approve_change", "target": "approval_decision"},
        ]
        metadata["positions"]["approve_change"] = {"x": 280, "y": 200}
        metadata["positions"]["approval_decision"] = {"x": 520, "y": 200}
        metadata["node_titles"]["approve_change"] = title
        metadata["node_titles"]["approval_decision"] = "审批结果"
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description="真实 Conductor HUMAN 审批挂起",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={"change_title": "本地闭环审批验收"},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        deadline = time.monotonic() + max(5, timeout_seconds)
        while time.monotonic() < deadline:
            if execution.conductor_workflow_id:
                remote = client.get_execution(execution.conductor_workflow_id)
                apply_remote_execution(execution, remote)
                execution.refresh_from_db()
                if execution.status == WorkflowExecution.Status.WAITING_APPROVAL:
                    break
                if execution.status in {
                    WorkflowExecution.Status.FAILED,
                    WorkflowExecution.Status.SUCCEEDED,
                    WorkflowExecution.Status.TERMINATED,
                    WorkflowExecution.Status.TIMED_OUT,
                }:
                    break
            time.sleep(0.5)
        ok = execution.status == WorkflowExecution.Status.WAITING_APPROVAL
        pending = execution.interactions.filter(status="PENDING").count()
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok and pending else "FAILED",
            detail="" if ok and pending else (execution.error_message or execution.status),
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={
                "execution_status": execution.status,
                "pending_interactions": pending,
                "note": "验收点是真实进入等待审批；不自动伪造通过/驳回",
            },
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_job_execute_probe(
    *,
    team_id: int,
    username: str,
    domain: str,
    target_ip: str = "10.10.90.120",
) -> ScenarioResult:
    """只探测作业目标授权解析，不伪造作业成功结果。"""
    key = "job_execute_probe"
    title = f"作业执行目标探测 {target_ip}"
    permission_data = {
        "username": username,
        "domain": domain,
        "current_team": team_id,
        "include_children": False,
        "is_superuser": True,
    }
    actor_context = {
        "username": username,
        "domain": domain,
        "authorized_team_ids": [team_id],
    }
    errors: list[str] = []
    try:
        nodes = (
            NodeMgmt(is_local_client=True).get_authorized_execution_targets_by_ips(
                [target_ip],
                permission_data,
            )
            or []
        )
        matched_nodes = [item for item in nodes if str(item.get("ip") or "") == target_ip]
        if matched_nodes:
            node = matched_nodes[0]
            return ScenarioResult(
                key=key,
                title=title,
                status="PASSED",
                detail="已从节点管理解析到授权主机；完整作业闭环仍依赖执行器",
                evidence={
                    "source": "node_mgmt",
                    "target": {
                        "id": f"node:{node['id']}",
                        "source": "node_mgmt",
                        "source_id": str(node["id"]),
                        "name": node.get("name", ""),
                        "ip": node.get("ip", ""),
                        "operating_system": node.get("operating_system", ""),
                    },
                },
            )
    except Exception as error:
        errors.append(f"node_mgmt:{type(error).__name__}:{error}")
    try:
        response = (
            JobMgmt(is_local_client=True).list_automation_targets(
                {"ips": [target_ip], "page": 1, "page_size": 20},
                actor_context,
            )
            or {}
        )
        if not response.get("result"):
            errors.append(f"job_mgmt:{response.get('message') or '无法校验作业平台目标'}")
        else:
            items = (response.get("data") or {}).get("items") or []
            matched = [item for item in items if str(item.get("ip") or "") == target_ip]
            if matched:
                target = matched[0]
                return ScenarioResult(
                    key=key,
                    title=title,
                    status="PASSED",
                    detail="已从作业平台解析到授权主机；完整作业闭环仍依赖执行器",
                    evidence={
                        "source": "job_mgmt",
                        "target": {
                            "id": f"manual:{target['target_id']}",
                            "source": "job_mgmt",
                            "source_id": str(target["target_id"]),
                            "name": target.get("name", ""),
                            "ip": target.get("ip", ""),
                            "operating_system": target.get("os_type", ""),
                        },
                    },
                )
            errors.append("job_mgmt:empty")
    except Exception as error:
        errors.append(f"job_mgmt:{type(error).__name__}:{error}")
    return ScenarioResult(
        key=key,
        title=title,
        status="FAILED",
        detail=f"组织 {team_id} 未解析到授权主机 {target_ip}",
        evidence={"errors": errors},
    )


def run_health_job_chain_scenario(
    *,
    fmt: str,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
    channel_id: int,
    script_content: str,
    target_reference: str | None = None,
    target_references: list[str] | None = None,
    script_type: str = "powershell",
    key_suffix: str = "",
) -> ScenarioResult:
    suffix = f"_{key_suffix}" if key_suffix else ""
    key = f"health_{fmt}_chain{suffix}"
    title = f"健康巡检闭环 {fmt.upper()}{(' / ' + key_suffix) if key_suffix else ''}"
    references = [str(item).strip() for item in (target_references or []) if str(item).strip()]
    if not references and target_reference:
        references = [str(target_reference).strip()]
    references = [item for item in references if item]
    if not references:
        return ScenarioResult(
            key=key,
            title=title,
            status="FAILED",
            detail="缺少已授权目标引用，跳过作业闭环（不伪造成功）",
            evidence={"required": "manual:<id> 或 node:<id>"},
        )
    if script_type not in {"shell", "python", "bat", "powershell"}:
        return ScenarioResult(
            key=key,
            title=title,
            status="FAILED",
            detail=f"脚本类型非法: {script_type}",
            evidence={"script_type": script_type},
        )
    try:
        snapshot = seed_builtin_health_template_snapshot(fmt, team_id=team_id)
        definition = {
            "name": "live_health_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["targets", "team", "actor", "execution_id"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "bklite_job_execute",
                    "taskReferenceName": "scan",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "targets": "${workflow.input.targets}",
                        "script_type": script_type,
                        "script_content": script_content,
                        "execution_params": "",
                        "timeout_seconds": min(timeout_seconds, 600),
                        "team": "${workflow.input.team}",
                        "actor": "${workflow.input.actor}",
                        "execution_id": "${workflow.input.execution_id}",
                    },
                },
                {
                    "name": "bklite_document_render",
                    "taskReferenceName": "report",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "data": "${scan.output}",
                        "template_snapshot": snapshot,
                        "execution_id": "${workflow.input.execution_id}",
                        "team": "${workflow.input.team}",
                    },
                },
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [
            {"id": "trigger-scan", "source": "trigger_form", "target": "scan"},
            {"id": "scan-report", "source": "scan", "target": "report"},
        ]
        metadata["positions"].update({"scan": {"x": 240, "y": 200}, "report": {"x": 460, "y": 200}})
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description=f"真实作业→{fmt} 文档→通知闭环",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={"targets": references},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        execution = _wait_execution(execution, client=client, timeout_seconds=timeout_seconds)
        scan_atom = AtomExecution.objects.filter(execution_id=execution.id, task_reference="scan").order_by("-id").first()
        scan_output = scan_atom.output if scan_atom and isinstance(scan_atom.output, dict) else {}
        summary = scan_output.get("summary") if isinstance(scan_output.get("summary"), dict) else {}
        host_ok = int(summary.get("succeeded") or 0) > 0 and int(summary.get("failed") or 0) == 0
        ok = execution.status == WorkflowExecution.Status.SUCCEEDED and host_ok
        detail = ""
        if not ok:
            if execution.status != WorkflowExecution.Status.SUCCEEDED:
                detail = execution.error_message or execution.status
            else:
                detail = f"作业主机未全部成功: {summary or 'missing summary'}"
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok else "FAILED",
            detail=detail,
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={
                "execution_status": execution.status,
                "target_references": references,
                "script_type": script_type,
                "job_summary": summary,
                "output": copy.deepcopy(execution.output or {}),
                "scan_output": copy.deepcopy(scan_output),
            },
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_mixed_host_health_chain_scenario(
    *,
    fmt: str,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
    channel_id: int,
    windows_target: str,
    linux_target: str,
    windows_script: str,
    linux_script: str,
    key_suffix: str = "",
) -> ScenarioResult:
    """混主机健康巡检：Windows + Linux 各跑一作业，合并后出报告并通知。不伪造。"""
    suffix = f"_{key_suffix}" if key_suffix else ""
    key = f"health_mixed_{fmt}{suffix}"
    title = f"混主机健康巡检 {fmt.upper()}{(' / ' + key_suffix) if key_suffix else ''}"
    if not windows_target or not linux_target:
        return ScenarioResult(
            key=key,
            title=title,
            status="FAILED",
            detail="缺少 Windows/Linux 目标引用",
            evidence={"windows_target": windows_target, "linux_target": linux_target},
        )
    try:
        snapshot = seed_builtin_health_template_snapshot(fmt, team_id=team_id)
        job_timeout = min(timeout_seconds, 600)
        definition = {
            "name": "live_mixed_health_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["team", "actor", "execution_id"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "bklite_job_execute",
                    "taskReferenceName": "scan_win",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "targets": [windows_target],
                        "script_type": "powershell",
                        "script_content": windows_script,
                        "execution_params": "",
                        "timeout_seconds": job_timeout,
                        "team": "${workflow.input.team}",
                        "actor": "${workflow.input.actor}",
                        "execution_id": "${workflow.input.execution_id}",
                    },
                },
                {
                    "name": "bklite_job_execute",
                    "taskReferenceName": "scan_linux",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "targets": [linux_target],
                        "script_type": "shell",
                        "script_content": linux_script,
                        "execution_params": "",
                        "timeout_seconds": job_timeout,
                        "team": "${workflow.input.team}",
                        "actor": "${workflow.input.actor}",
                        "execution_id": "${workflow.input.execution_id}",
                    },
                },
                {
                    "name": "bklite_document_render",
                    "taskReferenceName": "report",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "data": "${scan_win.output}",
                        "additional_data": "${scan_linux.output}",
                        "template_snapshot": snapshot,
                        "execution_id": "${workflow.input.execution_id}",
                        "team": "${workflow.input.team}",
                    },
                },
                {
                    "name": "bklite_notification",
                    "taskReferenceName": "notify",
                    "type": "SIMPLE",
                    "inputParameters": {
                        "notification_type": "EMAIL",
                        "channel_id": channel_id,
                        "recipients": [username],
                        "title": f"混主机健康巡检（{fmt}/{windows_target}+{linux_target}）",
                        "body": "混主机真实闭环验收通知（Windows + Linux）。",
                        "report_artifact": "${report.output.artifact}",
                        "team": "${workflow.input.team}",
                        "execution_id": "${workflow.input.execution_id}",
                        "task_reference": "notify",
                    },
                },
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [
            {"id": "trigger-scan_win", "source": "trigger_form", "target": "scan_win"},
            {"id": "scan_win-scan_linux", "source": "scan_win", "target": "scan_linux"},
            {"id": "scan_linux-report", "source": "scan_linux", "target": "report"},
            {"id": "report-notify", "source": "report", "target": "notify"},
        ]
        metadata["positions"].update(
            {
                "scan_win": {"x": 240, "y": 160},
                "scan_linux": {"x": 460, "y": 160},
                "report": {"x": 680, "y": 160},
                "notify": {"x": 900, "y": 160},
            }
        )
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description=f"混主机作业→{fmt} 文档→通知闭环",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        execution = _wait_execution(execution, client=client, timeout_seconds=timeout_seconds)
        ok = execution.status == WorkflowExecution.Status.SUCCEEDED
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok else "FAILED",
            detail="" if ok else (execution.error_message or execution.status),
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={
                "execution_status": execution.status,
                "windows_target": windows_target,
                "linux_target": linux_target,
                "format": fmt,
                "output": copy.deepcopy(execution.output or {}),
            },
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_engine_switch_scenario(
    *,
    team_id: int,
    username: str,
    domain: str,
    client: ConductorClient,
    timeout_seconds: int,
) -> ScenarioResult:
    key = "engine_switch"
    title = "Conductor SWITCH 引擎"
    try:
        definition = {
            "name": "live_switch_draft",
            "description": title,
            "version": 1,
            "schemaVersion": 2,
            "ownerEmail": "bklite@weops.com",
            "inputParameters": ["value", "team", "actor", "execution_id"],
            "outputParameters": {},
            "tasks": [
                {
                    "name": "condition",
                    "taskReferenceName": "condition",
                    "type": "SWITCH",
                    "inputParameters": {"left_0": "${workflow.input.value}", "right_0": "ok"},
                    "evaluatorType": "javascript",
                    "expression": "($.left_0 == $.right_0) ? 'true' : 'false'",
                    "decisionCases": {"true": [], "false": []},
                    "defaultCase": [],
                }
            ],
            "restartable": True,
            "workflowStatusListenerEnabled": False,
        }
        metadata = _base_metadata(title)
        metadata["edges"] = [{"id": "trigger-condition", "source": "trigger_form", "target": "condition"}]
        metadata["positions"]["condition"] = {"x": 280, "y": 200}
        client.register_task_definitions(TASK_DEFINITIONS)
        workflow = _register_live_workflow(
            team_id=team_id,
            username=username,
            domain=domain,
            key=key,
            name=title,
            description="真实 Conductor SWITCH 烟雾",
            definition=definition,
            metadata=metadata,
            client=client,
        )
        execution = start_execution(
            workflow,
            inputs={"value": "ok"},
            started_by=username,
            domain=domain,
            client=client,
            mode=WorkflowExecution.Mode.DEBUG,
            trigger_type="FORM",
            trigger_id=f"live-{key}",
        )
        execution = _wait_execution(execution, client=client, timeout_seconds=timeout_seconds)
        ok = execution.status == WorkflowExecution.Status.SUCCEEDED
        return ScenarioResult(
            key=key,
            title=title,
            status="PASSED" if ok else "FAILED",
            detail="" if ok else (execution.error_message or execution.status),
            workflow_id=workflow.id,
            execution_id=str(execution.id),
            conductor_workflow_id=execution.conductor_workflow_id or "",
            evidence={"execution_status": execution.status},
        )
    except Exception as error:
        return ScenarioResult(key=key, title=title, status="FAILED", detail=f"{type(error).__name__}: {error}")


def run_live_acceptance(
    *,
    team_id: int,
    username: str,
    domain: str = "domain.com",
    channel_id: int = 1,
    timeout_seconds: int = 90,
    target_ip: str = "10.10.90.120",
    health_script: str = "",
) -> dict[str, Any]:
    viewer = get_user_model().objects.filter(username=username, domain=domain).first()
    if viewer is None:
        raise ValueError(f"找不到页面查看用户: {username}@{domain}")
    authorized = {int(item["id"]) for item in (viewer.group_list or []) if isinstance(item, dict) and str(item.get("id", "")).isdigit()}
    if team_id <= 0 or team_id not in authorized:
        raise ValueError(f"页面查看用户无权访问团队: {team_id}")

    client = ConductorClient()
    health = client.health()
    if not health.get("healthy"):
        raise ConductorUnavailable("Conductor 不健康，拒绝开始真实闭环验收")

    # 清理历史 [LIVE] 未终态执行，避免积压的 job_execute 占住 Worker 轮询。
    for execution in WorkflowExecution.objects.filter(
        workflow__name__startswith=LIVE_PREFIX,
        workflow__team=[team_id],
        status__in={
            WorkflowExecution.Status.QUEUED,
            WorkflowExecution.Status.RUNNING,
            WorkflowExecution.Status.WAITING_APPROVAL,
            WorkflowExecution.Status.TERMINATING,
        },
    ):
        if execution.conductor_workflow_id:
            try:
                client.terminate_workflow(execution.conductor_workflow_id, reason="live-acceptance-reset")
            except Exception:
                pass
        execution.status = WorkflowExecution.Status.TERMINATED
        execution.error_message = "被后续真实闭环验收重置"
        execution.finished_at = timezone.now()
        execution.save(update_fields=("status", "error_message", "finished_at", "updated_at"))

    # 额外抽干可能残留在队列里的作业任务，避免阻塞文档/HTTP/通知。
    for _ in range(20):
        task = client.poll_task("bklite_job_execute", "live-acceptance-drain")
        if not task:
            break
        try:
            client.update_task(
                {
                    "workflowInstanceId": task.get("workflowInstanceId"),
                    "taskId": task.get("taskId"),
                    "workerId": "live-acceptance-drain",
                    "status": "FAILED",
                    "reasonForIncompletion": "drained before live acceptance",
                    "outputData": {},
                }
            )
        except Exception:
            break

    job_probe = run_job_execute_probe(
        team_id=team_id,
        username=username,
        domain=domain,
        target_ip=target_ip,
    )
    target_reference = None
    if job_probe.status == "PASSED":
        target = job_probe.evidence.get("target") or {}
        source = str(target.get("source") or "")
        source_id = str(target.get("source_id") or target.get("id") or "")
        if source == "node_mgmt" and source_id:
            target_reference = f"node:{source_id}"
        elif source_id.isdigit():
            target_reference = f"manual:{source_id}"
        elif str(target.get("id") or "").startswith(("node:", "manual:")):
            target_reference = str(target["id"])

    # 先跑不依赖作业平台的场景，避免 job_execute 卡住 Worker 后拖死文档/HTTP/通知。
    results = [
        run_engine_switch_scenario(
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
        ),
        run_document_render_scenario(
            fmt="docx",
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
        ),
        run_document_render_scenario(
            fmt="xlsx",
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
        ),
        run_http_request_scenario(
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
        ),
        run_notification_scenario(
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
            channel_id=channel_id,
        ),
        run_approval_scenario(
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
        ),
        job_probe,
        run_health_job_chain_scenario(
            fmt="docx",
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
            channel_id=channel_id,
            script_content=health_script,
            target_reference=target_reference,
        ),
        run_health_job_chain_scenario(
            fmt="xlsx",
            team_id=team_id,
            username=username,
            domain=domain,
            client=client,
            timeout_seconds=timeout_seconds,
            channel_id=channel_id,
            script_content=health_script,
            target_reference=target_reference,
        ),
    ]
    passed = sum(1 for item in results if item.status == "PASSED")
    failed = sum(1 for item in results if item.status == "FAILED")
    return {
        "generated_at": timezone.now().isoformat(),
        "team_id": team_id,
        "username": username,
        "domain": domain,
        "conductor_healthy": True,
        "summary": {"total": len(results), "passed": passed, "failed": failed},
        "scenarios": [item.to_dict() for item in results],
        "policy": "不伪造成功；依赖缺失时标记 FAILED 并保留原始错误",
    }
