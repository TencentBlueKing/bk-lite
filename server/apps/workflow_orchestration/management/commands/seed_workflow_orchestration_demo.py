from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.workflow_orchestration.models import TriggerInvocation, Workflow, WorkflowExecution, WorkflowInteraction, WorkflowVersion
from apps.workflow_orchestration.services.atom_registry import ensure_platform_atom
from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS, atom_catalog_payload
from apps.workflow_orchestration.services.builtin_workflows import BUILTIN_LINUX_KEY, BUILTIN_WINDOWS_KEY, ensure_builtin_health_workflows
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.definitions import prepare_definition_for_publish
from apps.workflow_orchestration.services.demo_showcase import SHOWCASE_ATOM_KEYS, build_additional_showcase_workflows
from apps.workflow_orchestration.services.health_inspection_scripts import LINUX_HEALTH_SCRIPT, WINDOWS_HEALTH_SCRIPT
from apps.workflow_orchestration.services.orchestration_contract import validate_orchestration_metadata
from apps.workflow_orchestration.services.triggers import sync_published_triggers

__all__ = ("LINUX_HEALTH_SCRIPT", "WINDOWS_HEALTH_SCRIPT")

DEMO_PREFIX = "[TDD/BDD]"


def _walk_tasks(tasks):
    for task in tasks:
        yield task
        for branch in (task.get("decisionCases") or {}).values():
            if isinstance(branch, list):
                yield from _walk_tasks(branch)
        for key in ("defaultCase", "loopOver"):
            if isinstance(task.get(key), list):
                yield from _walk_tasks(task[key])
        for branch in task.get("forkTasks") or []:
            if isinstance(branch, list):
                yield from _walk_tasks(branch)


def _execution_id(team_id: int, scenario: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"bklite://workflow-orchestration/demo/{team_id}/{scenario}")


def _metric(
    *,
    category: str,
    object_type: str,
    object_name: str,
    dimensions: str,
    metric_name: str,
    display_name: str,
    value: float,
    unit: str,
    health_status: str,
    detail: str,
    collected_at: str,
    warning_threshold: float = 80,
    critical_threshold: float = 90,
) -> dict:
    return {
        "category": category,
        "object_type": object_type,
        "object_name": object_name,
        "dimensions": dimensions,
        "metric_name": metric_name,
        "display_name": display_name,
        "value": value,
        "unit": unit,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "health_status": health_status,
        "collected_at": collected_at,
        "detail": detail,
    }


def _health_job_output(*, collected_at: str, warning: bool, operating_system: str = "windows") -> dict:
    os_key = str(operating_system or "windows").lower()
    disk_name = "D:" if os_key == "windows" else "/data"
    disk_value = 87.6 if warning else 64
    disk_status = "WARNING" if warning else "NORMAL"
    host = {
        "hostname": "win-demo-01" if os_key == "windows" else "linux-demo-01",
        "os_version": "Windows Server 2022" if os_key == "windows" else "Ubuntu 22.04.5 LTS",
        "architecture": "x86_64",
        "uptime_hours": 240.5,
        "cpu_cores": 4,
        "memory_total_gb": 16.0,
        "top_cpu": "python=12.0s; system=4.0s" if os_key == "windows" else "python=12.0%; systemd=3.0%",
        "top_memory": "Memory Compression=800MB" if os_key == "windows" else "postgres=18.0%",
    }
    metrics = [
        _metric(
            category="计算",
            object_type="processor",
            object_name="CPU Total",
            dimensions="core=all",
            metric_name="usage_percent",
            display_name="CPU 使用率",
            value=42,
            unit="%",
            health_status="NORMAL",
            detail="处理器使用率",
            collected_at=collected_at,
        ),
        _metric(
            category="内存",
            object_type="physical_memory",
            object_name="Memory Total",
            dimensions="scope=system",
            metric_name="usage_percent",
            display_name="物理内存使用率",
            value=68,
            unit="%",
            health_status="NORMAL",
            detail="total_gb=16,available_mb=5120",
            collected_at=collected_at,
        ),
        _metric(
            category="磁盘",
            object_type="logical_disk",
            object_name="C:" if os_key == "windows" else "/",
            dimensions="mount=%s" % ("C:" if os_key == "windows" else "/"),
            metric_name="usage_percent",
            display_name="磁盘使用率",
            value=73,
            unit="%",
            health_status="NORMAL",
            detail="total_gb=200,used_gb=146",
            collected_at=collected_at,
        ),
        _metric(
            category="磁盘",
            object_type="logical_disk",
            object_name=disk_name,
            dimensions="mount=%s" % disk_name,
            metric_name="usage_percent",
            display_name="磁盘使用率",
            value=disk_value,
            unit="%",
            health_status=disk_status,
            detail="total_gb=500,used_gb=438",
            collected_at=collected_at,
        ),
        _metric(
            category="网络",
            object_type="network_adapter",
            object_name="Ethernet0" if os_key == "windows" else "eth0",
            dimensions="adapter=%s" % ("Ethernet0" if os_key == "windows" else "eth0"),
            metric_name="link_up",
            display_name="网卡链路",
            value=1,
            unit="bool",
            health_status="NORMAL",
            detail="ip=10.10.90.120,status=up" if os_key == "windows" else "ip=192.168.64.5,status=up",
            collected_at=collected_at,
            warning_threshold=1,
            critical_threshold=1,
        ),
        _metric(
            category="系统健康",
            object_type="service",
            object_name="W32Time" if os_key == "windows" else "time_sync",
            dimensions="scope=system",
            metric_name="running",
            display_name="时间同步服务",
            value=1,
            unit="bool",
            health_status="NORMAL",
            detail="时间服务运行中",
            collected_at=collected_at,
            warning_threshold=1,
            critical_threshold=1,
        ),
        _metric(
            category="基础服务",
            object_type="service",
            object_name="WinRM" if os_key == "windows" else "sshd",
            dimensions="service=%s" % ("WinRM" if os_key == "windows" else "sshd"),
            metric_name="running",
            display_name="远程管理服务",
            value=1,
            unit="bool",
            health_status="NORMAL",
            detail="服务运行中",
            collected_at=collected_at,
            warning_threshold=1,
            critical_threshold=1,
        ),
        _metric(
            category="安全浅检",
            object_type="service",
            object_name="firewall",
            dimensions="scope=system",
            metric_name="running",
            display_name="防火墙服务",
            value=1,
            unit="bool",
            health_status="NORMAL",
            detail="防火墙服务运行中",
            collected_at=collected_at,
            warning_threshold=1,
            critical_threshold=1,
        ),
        _metric(
            category="更新账龄",
            object_type="patch",
            object_name="Updates",
            dimensions="scope=system",
            metric_name="days_since_update",
            display_name="距上次更新天数",
            value=30,
            unit="days",
            health_status="NORMAL",
            detail="days_since_update=30",
            collected_at=collected_at,
            warning_threshold=90,
            critical_threshold=180,
        ),
        _metric(
            category="进程热点",
            object_type="process",
            object_name="python",
            dimensions="rank=1",
            metric_name="cpu_percent",
            display_name="CPU Top1",
            value=12.5,
            unit="%",
            health_status="NORMAL",
            detail="pid=1234",
            collected_at=collected_at,
            warning_threshold=0,
            critical_threshold=0,
        ),
    ]
    critical_metrics = [metric for metric in metrics if metric["health_status"] == "CRITICAL"]
    warning_metrics = [metric for metric in metrics if metric["health_status"] == "WARNING"]
    normal_metrics = [metric for metric in metrics if metric["health_status"] == "NORMAL"]
    if os_key == "windows":
        target = {
            "id": "manual:demo-windows-120",
            "source": "job_mgmt",
            "source_id": 1,
            "name": "Windows 巡检主机",
            "ip": "10.10.90.120",
            "operating_system": "windows",
        }
    else:
        target = {
            "id": "manual:demo-linux-5",
            "source": "job_mgmt",
            "source_id": 2,
            "name": "Linux 巡检主机",
            "ip": "192.168.64.5",
            "operating_system": "linux",
        }
    return {
        "results": [
            {
                "target": target,
                "status": "SUCCESS",
                "exit_code": 0,
                "stdout": "BK_LITE_RESULT={...}",
                "stderr": "",
                "data": {
                    "collected_at": collected_at,
                    "host": host,
                    "metrics": metrics,
                    "metric_count": len(metrics),
                    "critical": critical_metrics,
                    "warning": warning_metrics,
                    "normal": normal_metrics,
                    "critical_count": len(critical_metrics),
                    "warning_count": len(warning_metrics),
                    "normal_count": len(normal_metrics),
                    "conclusion": "需关注" if warning else "健康",
                },
                "error": None,
            }
        ],
        "summary": {"total": 1, "succeeded": 1, "failed": 0},
    }


class Command(BaseCommand):
    help = "清理旧编排演示数据，并生成七个 MVP 验收流程及执行记录（含 Word/Excel 巡检）"

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--domain", default="domain.com")
        parser.add_argument("--confirm", action="store_true", help="确认重建当前组织的 [TDD/BDD] 演示数据")
        parser.add_argument("--channel-id", type=int, default=1, help="演示通知渠道 ID")

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("该命令会重建 [TDD/BDD] 演示数据，请显式传入 --confirm")
        team_id = int(options["team_id"])
        username = str(options["username"]).strip()
        domain = str(options["domain"]).strip()
        channel_id = int(options["channel_id"])
        viewer = get_user_model().objects.filter(username=username, domain=domain).first()
        if viewer is None:
            raise CommandError(f"找不到页面查看用户: {username}@{domain}")
        authorized = {int(item["id"]) for item in (viewer.group_list or []) if isinstance(item, dict) and str(item.get("id", "")).isdigit()}
        if team_id <= 0 or team_id not in authorized:
            raise CommandError(f"页面查看用户无权访问团队: {team_id}")

        platform_catalog = {item["key"]: item for item in atom_catalog_payload()}
        missing = set(SHOWCASE_ATOM_KEYS).difference(platform_catalog)
        if missing:
            raise CommandError(f"缺少 MVP 原子: {', '.join(sorted(missing))}")
        now = timezone.now()

        try:
            builtin_workflows = ensure_builtin_health_workflows(
                team_id=team_id,
                username=username,
                domain=domain,
                channel_id=channel_id,
                register_conductor=True,
            )
        except Exception as error:
            raise CommandError(f"无法写入内置巡检流程: {error}") from error
        created_builtins = {BUILTIN_WINDOWS_KEY: builtin_workflows[0], BUILTIN_LINUX_KEY: builtin_workflows[1]}

        workflow_items = [
            *build_additional_showcase_workflows(
                team_id=team_id,
                channel_id=channel_id,
                username=username,
            ),
        ]

        prepared_items = []
        for item in workflow_items:
            task_references = {
                task["taskReferenceName"]
                for task in _walk_tasks(item["definition"].get("tasks") or [])
                if isinstance(task.get("taskReferenceName"), str)
            }
            metadata = validate_orchestration_metadata(item["metadata"], task_references=task_references)
            definition = prepare_definition_for_publish(
                item["definition"],
                engine_name=item["engine_name"],
                version=1,
            )
            atom_keys = sorted({task["name"] for task in _walk_tasks(definition.get("tasks") or []) if task.get("type") == "SIMPLE"})
            prepared_items.append(
                {
                    **item,
                    "definition": definition,
                    "metadata": metadata,
                    "atom_keys": atom_keys,
                }
            )

        try:
            conductor = ConductorClient()
            conductor.register_task_definitions(TASK_DEFINITIONS)
            for item in prepared_items:
                conductor.register_workflow(item["definition"])
        except ConductorUnavailable as error:
            raise CommandError(f"无法刷新 Conductor 演示流程定义: {error}") from error

        with transaction.atomic():
            old_workflows = Workflow.all_objects.filter(name__startswith=DEMO_PREFIX, team=[team_id])
            builtin_workflows = Workflow.all_objects.filter(is_builtin=True, team=[team_id])
            # 演示重建会重写内置巡检样例执行；一并清掉其子执行，避免残留抬高列表计数。
            old_executions = WorkflowExecution.objects.filter(Q(workflow__in=old_workflows) | Q(workflow__in=builtin_workflows))
            child_executions = WorkflowExecution.objects.filter(parent_execution__in=old_executions)
            TriggerInvocation.objects.filter(Q(execution__in=old_executions) | Q(execution__in=child_executions)).delete()
            child_executions.delete()
            old_executions.delete()
            old_workflows.delete()

            for atom_key in SHOWCASE_ATOM_KEYS:
                ensure_platform_atom(platform_catalog[atom_key], username=username, domain=domain)

            created: dict[str, Workflow] = {}
            for item in prepared_items:
                metadata = item["metadata"]
                definition = item["definition"]
                atom_keys = item["atom_keys"]
                workflow = Workflow.all_objects.create(
                    engine_name=item["engine_name"],
                    name=item["name"],
                    description=item["description"],
                    team=[team_id],
                    status=Workflow.Status.PUBLISHED,
                    definition=definition,
                    canvas_metadata=metadata,
                    trigger_types=[trigger["trigger_type"] for trigger in metadata["trigger_nodes"]],
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
                snapshot = {"demo": True, "source": "tdd-bdd", "atoms": [{"key": key} for key in atom_keys]}
                WorkflowVersion.objects.create(
                    workflow=workflow,
                    version=1,
                    definition=definition,
                    canvas_metadata=metadata,
                    resource_snapshot=snapshot,
                    change_summary={"summary": "MVP 验收版本"},
                    created_by=username,
                    domain=domain,
                )
                sync_published_triggers(workflow, metadata, username=username, domain=domain)
                created[item["key"]] = workflow
            created.update(created_builtins)

            execution_specs = [
                (
                    "health-word-success",
                    BUILTIN_WINDOWS_KEY,
                    WorkflowExecution.Status.SUCCEEDED,
                    "10.10.90.120 Word 巡检闭环样例",
                    None,
                    False,
                ),
                (
                    "health-excel-success",
                    BUILTIN_LINUX_KEY,
                    WorkflowExecution.Status.SUCCEEDED,
                    "192.168.64.5 Linux Excel 巡检闭环样例",
                    None,
                    False,
                ),
                (
                    "health-warning",
                    BUILTIN_WINDOWS_KEY,
                    WorkflowExecution.Status.SUCCEEDED,
                    "多磁盘阈值触发告警样例",
                    None,
                    True,
                ),
                (
                    "approval-pending",
                    "approval",
                    WorkflowExecution.Status.WAITING_APPROVAL,
                    "生产变更等待审批",
                    None,
                    False,
                ),
                (
                    "webhook-success",
                    "webhook",
                    WorkflowExecution.Status.SUCCEEDED,
                    "Webhook 同步响应成功",
                    None,
                    False,
                ),
                (
                    "scheduled-http-success",
                    "scheduled_http",
                    WorkflowExecution.Status.SUCCEEDED,
                    "定时 HTTP 检查成功",
                    None,
                    False,
                ),
                (
                    "nats-success",
                    "nats",
                    WorkflowExecution.Status.SUCCEEDED,
                    "NATS 标准信封事件处理成功",
                    None,
                    False,
                ),
                (
                    "http-failure",
                    "scheduled_http",
                    WorkflowExecution.Status.FAILED,
                    "HTTP 端点返回非成功状态码",
                    None,
                    False,
                ),
                (
                    "multi-form-success",
                    "multi_trigger",
                    WorkflowExecution.Status.SUCCEEDED,
                    "表单入口执行成功",
                    "trigger_form",
                    False,
                ),
                (
                    "multi-webhook-success",
                    "multi_trigger",
                    WorkflowExecution.Status.SUCCEEDED,
                    "Webhook 入口执行成功",
                    "trigger_webhook",
                    False,
                ),
                (
                    "multi-schedule-success",
                    "multi_trigger",
                    WorkflowExecution.Status.SUCCEEDED,
                    "定时入口执行成功",
                    "trigger_schedule",
                    False,
                ),
            ]
            for index, (
                scenario,
                workflow_key,
                execution_status,
                summary,
                trigger_node_key,
                warning,
            ) in enumerate(execution_specs):
                workflow = created[workflow_key]
                runtime_trigger = workflow.triggers.get(node_key=trigger_node_key) if trigger_node_key is not None else None
                finished = execution_status in {
                    WorkflowExecution.Status.SUCCEEDED,
                    WorkflowExecution.Status.FAILED,
                }
                output = {"summary": summary, "scenario": scenario, "demo": True}
                target_snapshot = {}
                if workflow_key in {BUILTIN_WINDOWS_KEY, BUILTIN_LINUX_KEY}:
                    output["job"] = _health_job_output(
                        collected_at=now.isoformat(),
                        warning=warning,
                        operating_system="windows" if workflow_key == BUILTIN_WINDOWS_KEY else "linux",
                    )
                    target_snapshot = {
                        "fields": {
                            "targets": {
                                "items": [output["job"]["results"][0]["target"]],
                                "count": 1,
                                "offline_count": 0,
                            }
                        },
                        "unique_total": 1,
                        "offline_count": 0,
                        "offline_confirmed": False,
                    }
                execution = WorkflowExecution.objects.create(
                    id=_execution_id(team_id, scenario),
                    workflow=workflow,
                    workflow_version=1,
                    conductor_workflow_id=f"demo-bdd-{team_id}-{scenario}",
                    status=execution_status,
                    team=[team_id],
                    input={"scenario": scenario},
                    output=output,
                    has_warnings=warning,
                    warning_count=1 if warning else 0,
                    tasks=[],
                    definition_snapshot=workflow.definition,
                    resource_snapshot={"demo": True, "source": "tdd-bdd"},
                    target_snapshot=target_snapshot,
                    error_message=summary if execution_status == WorkflowExecution.Status.FAILED else "",
                    failed_stage="atom" if execution_status == WorkflowExecution.Status.FAILED else "",
                    trigger_type=(runtime_trigger.trigger_type if runtime_trigger else workflow.trigger_types[0]),
                    trigger_id=str(runtime_trigger.id) if runtime_trigger else scenario,
                    mode=WorkflowExecution.Mode.PRODUCTION,
                    started_by=username,
                    domain=domain,
                    finished_at=now - timedelta(minutes=index * 5) if finished else None,
                )
                if execution_status == WorkflowExecution.Status.WAITING_APPROVAL:
                    WorkflowInteraction.objects.create(
                        execution=execution,
                        interaction_type=WorkflowInteraction.Type.APPROVAL,
                        task_reference="approve_change",
                        conductor_task_id=f"demo-approval-{team_id}",
                        title="生产变更审批",
                        description="请确认变更范围、风险和回退方案。",
                        candidate_users=[username],
                        public_context={
                            "change_title": "Windows 业务服务滚动更新",
                            "change_detail": "先巡检 10.10.90.120，再进入变更窗口。",
                        },
                        team=[team_id],
                        status=WorkflowInteraction.Status.PENDING,
                        due_at=now + timedelta(days=1),
                    )

        self.stdout.write(self.style.SUCCESS(f"已清理旧 [TDD/BDD] 演示数据，并为团队 {team_id} 确保 2 条内置巡检、生成 5 条演示流程与 11 条执行记录。"))
