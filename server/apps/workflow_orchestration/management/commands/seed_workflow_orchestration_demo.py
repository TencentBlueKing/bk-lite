from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.workflow_orchestration.models import TriggerInvocation, Workflow, WorkflowExecution, WorkflowInteraction, WorkflowVersion
from apps.workflow_orchestration.services.atom_registry import ensure_platform_atom
from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS, atom_catalog_payload
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.definitions import prepare_definition_for_publish
from apps.workflow_orchestration.services.demo_showcase import (
    SHOWCASE_ATOM_KEYS,
    build_additional_showcase_workflows,
    build_health_inspection_showcase_workflow,
)
from apps.workflow_orchestration.services.demo_templates import seed_builtin_health_template_snapshot
from apps.workflow_orchestration.services.orchestration_contract import validate_orchestration_metadata
from apps.workflow_orchestration.services.triggers import sync_published_triggers

DEMO_PREFIX = "[TDD/BDD]"

WINDOWS_HEALTH_SCRIPT = r"""
$cpu = [math]::Round((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average, 2)
$os = Get-CimInstance Win32_OperatingSystem
$memory = [math]::Round((1 - ($os.FreePhysicalMemory / $os.TotalVisibleMemorySize)) * 100, 2)
$collectedAt = (Get-Date).ToUniversalTime().ToString("o")
function Get-HealthStatus([double]$value, [double]$warning, [double]$critical) {
  if ($value -ge $critical) { return "CRITICAL" }
  if ($value -ge $warning) { return "WARNING" }
  return "NORMAL"
}
$metrics = @(
  @{
    category = "CPU"; object_type = "processor"; object_name = "CPU Total"; dimensions = "core=all"
    metric_name = "usage_percent"; value = $cpu; unit = "%"; warning_threshold = 80; critical_threshold = 90
    health_status = (Get-HealthStatus $cpu 80 90); collected_at = $collectedAt; detail = "CPU 总使用率"
  },
  @{
    category = "内存"; object_type = "physical_memory"; object_name = "Memory Total"; dimensions = "scope=system"
    metric_name = "usage_percent"; value = $memory; unit = "%"; warning_threshold = 80; critical_threshold = 90
    health_status = (Get-HealthStatus $memory 80 90); collected_at = $collectedAt; detail = "物理内存使用率"
  }
)
$diskMetrics = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
  $usage = if ($_.Size -gt 0) { [math]::Round((($_.Size - $_.FreeSpace) / $_.Size) * 100, 2) } else { 0 }
  @{
    category = "磁盘"; object_type = "logical_disk"; object_name = $_.DeviceID; dimensions = ("mount=" + $_.DeviceID)
    metric_name = "usage_percent"; value = $usage; unit = "%"; warning_threshold = 80; critical_threshold = 90
    health_status = (Get-HealthStatus $usage 80 90); collected_at = $collectedAt
    detail = ("total_gb=" + [math]::Round($_.Size / 1GB, 2) + ",used_gb=" + [math]::Round(($_.Size - $_.FreeSpace) / 1GB, 2))
  }
})
$networkMetrics = @(Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface -ErrorAction SilentlyContinue | ForEach-Object {
  $mbps = [math]::Round(($_.BytesTotalPersec * 8) / 1MB, 2)
  @{
    category = "网络"; object_type = "network_adapter"; object_name = $_.Name; dimensions = ("adapter=" + $_.Name)
    metric_name = "throughput_mbps"; value = $mbps; unit = "Mbps"; warning_threshold = 800; critical_threshold = 950
    health_status = (Get-HealthStatus $mbps 800 950); collected_at = $collectedAt; detail = "网卡总吞吐率"
  }
})
$metrics += $diskMetrics
$metrics += $networkMetrics
$critical = @($metrics | Where-Object { $_.health_status -eq "CRITICAL" })
$warning = @($metrics | Where-Object { $_.health_status -eq "WARNING" })
$normal = @($metrics | Where-Object { $_.health_status -eq "NORMAL" })
$result = @{
  collected_at = $collectedAt; metrics = $metrics; metric_count = $metrics.Count
  critical = $critical; warning = $warning; normal = $normal
  critical_count = $critical.Count; warning_count = $warning.Count; normal_count = $normal.Count
  conclusion = $(if (($critical.Count + $warning.Count) -gt 0) { "需关注" } else { "健康" })
}
Write-Output ("BK_LITE_RESULT=" + ($result | ConvertTo-Json -Depth 8 -Compress))
""".strip()

# 注意：勿在脚本正文使用 `${var}`。Conductor 会把 `${...}` 解析成工作流引用，
# 导致 registerWorkflowDef 校验失败；bash 下用 `$var` 即可。
LINUX_HEALTH_SCRIPT = r"""
#!/bin/bash
set -euo pipefail
collected_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cores=$(nproc 2>/dev/null || echo 1)
load=$(awk '{print $1}' /proc/loadavg)
cpu=$(awk -v l="$load" -v c="$cores" 'BEGIN{v=(c>0? (l/c)*100 : 0); if(v>100)v=100; printf "%.2f", v}')
mem_total=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)
mem_avail=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
memory=$(awk -v t="$mem_total" -v a="$mem_avail" 'BEGIN{ if(t<=0){print 0}else{printf "%.2f", (1-a/t)*100} }')
disk=$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')
health() { awk -v v="$1" -v w="$2" -v c="$3" 'BEGIN{ if(v+0>=c) print "CRITICAL"; else if(v+0>=w) print "WARNING"; else print "NORMAL" }'; }
cpu_s=$(health "$cpu" 80 90)
mem_s=$(health "$memory" 80 90)
disk_s=$(health "$disk" 80 90)
python3 - <<PY
import json
collected_at = "$collected_at"
metrics = [
  {
    "category":"CPU","object_type":"processor","object_name":"CPU Total","dimensions":"core=all",
    "metric_name":"usage_percent","value":float("$cpu"),"unit":"%",
    "warning_threshold":80,"critical_threshold":90,"health_status":"$cpu_s",
    "collected_at":collected_at,"detail":"CPU 负载折算使用率",
  },
  {
    "category":"内存","object_type":"physical_memory","object_name":"Memory Total","dimensions":"scope=system",
    "metric_name":"usage_percent","value":float("$memory"),"unit":"%",
    "warning_threshold":80,"critical_threshold":90,"health_status":"$mem_s",
    "collected_at":collected_at,"detail":"物理内存使用率",
  },
  {
    "category":"磁盘","object_type":"logical_disk","object_name":"/","dimensions":"mount=/",
    "metric_name":"usage_percent","value":float("$disk"),"unit":"%",
    "warning_threshold":80,"critical_threshold":90,"health_status":"$disk_s",
    "collected_at":collected_at,"detail":"根分区使用率",
  },
  {
    "category":"网络","object_type":"network_adapter","object_name":"lo","dimensions":"adapter=lo",
    "metric_name":"throughput_mbps","value":0.0,"unit":"Mbps",
    "warning_threshold":800,"critical_threshold":950,"health_status":"NORMAL",
    "collected_at":collected_at,"detail":"环回接口占位吞吐",
  },
]
critical=[m for m in metrics if m["health_status"]=="CRITICAL"]
warning=[m for m in metrics if m["health_status"]=="WARNING"]
normal=[m for m in metrics if m["health_status"]=="NORMAL"]
result={
  "collected_at": collected_at,
  "metrics": metrics,
  "metric_count": len(metrics),
  "critical": critical,
  "warning": warning,
  "normal": normal,
  "critical_count": len(critical),
  "warning_count": len(warning),
  "normal_count": len(normal),
  "conclusion": "需关注" if (critical or warning) else "健康",
}
print("BK_LITE_RESULT=" + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
PY
""".strip()


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


def _health_job_output(*, collected_at: str, warning: bool) -> dict:
    disk_d_value = 87.6 if warning else 64
    disk_d_status = "WARNING" if warning else "NORMAL"
    metrics = [
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
        },
        {
            "category": "内存",
            "object_type": "physical_memory",
            "object_name": "Memory Total",
            "dimensions": "scope=system",
            "metric_name": "usage_percent",
            "value": 68,
            "unit": "%",
            "warning_threshold": 80,
            "critical_threshold": 90,
            "health_status": "NORMAL",
            "collected_at": collected_at,
            "detail": "物理内存使用率",
        },
        {
            "category": "磁盘",
            "object_type": "logical_disk",
            "object_name": "C:",
            "dimensions": "mount=C:",
            "metric_name": "usage_percent",
            "value": 73,
            "unit": "%",
            "warning_threshold": 80,
            "critical_threshold": 90,
            "health_status": "NORMAL",
            "collected_at": collected_at,
            "detail": "total_gb=200,used_gb=146",
        },
        {
            "category": "磁盘",
            "object_type": "logical_disk",
            "object_name": "D:",
            "dimensions": "mount=D:",
            "metric_name": "usage_percent",
            "value": disk_d_value,
            "unit": "%",
            "warning_threshold": 80,
            "critical_threshold": 90,
            "health_status": disk_d_status,
            "collected_at": collected_at,
            "detail": "total_gb=500,used_gb=438",
        },
        {
            "category": "网络",
            "object_type": "network_adapter",
            "object_name": "Ethernet0",
            "dimensions": "adapter=Ethernet0,direction=receive",
            "metric_name": "throughput_mbps",
            "value": 18.6,
            "unit": "Mbps",
            "warning_threshold": 800,
            "critical_threshold": 950,
            "health_status": "NORMAL",
            "collected_at": collected_at,
            "detail": "网卡总吞吐率",
        },
    ]
    warning_metrics = [metric for metric in metrics if metric["health_status"] == "WARNING"]
    normal_metrics = [metric for metric in metrics if metric["health_status"] == "NORMAL"]
    target = {
        "id": "manual:demo-windows-120",
        "source": "job_mgmt",
        "source_id": 1,
        "name": "Windows 巡检主机",
        "ip": "10.10.90.120",
        "operating_system": "windows",
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
                    "metrics": metrics,
                    "metric_count": len(metrics),
                    "critical": [],
                    "warning": warning_metrics,
                    "normal": normal_metrics,
                    "critical_count": 0,
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
            docx_snapshot = seed_builtin_health_template_snapshot("docx", team_id=team_id)
            xlsx_snapshot = seed_builtin_health_template_snapshot("xlsx", team_id=team_id)
        except Exception as error:
            raise CommandError(f"无法写入健康巡检演示模板: {error}") from error

        workflow_items = [
            build_health_inspection_showcase_workflow(
                team_id=team_id,
                channel_id=channel_id,
                username=username,
                fmt="docx",
                template_snapshot=docx_snapshot,
                script_type="powershell",
                script_content=WINDOWS_HEALTH_SCRIPT,
            ),
            build_health_inspection_showcase_workflow(
                team_id=team_id,
                channel_id=channel_id,
                username=username,
                fmt="xlsx",
                template_snapshot=xlsx_snapshot,
                script_type="powershell",
                script_content=WINDOWS_HEALTH_SCRIPT,
            ),
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
            old_executions = WorkflowExecution.objects.filter(workflow__in=old_workflows)
            TriggerInvocation.objects.filter(execution__in=old_executions).delete()
            WorkflowExecution.objects.filter(parent_execution__in=old_executions).update(parent_execution=None)
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

            execution_specs = [
                (
                    "health-word-success",
                    "health_docx",
                    WorkflowExecution.Status.SUCCEEDED,
                    "10.10.90.120 Word 巡检闭环样例",
                    None,
                    False,
                ),
                (
                    "health-excel-success",
                    "health_xlsx",
                    WorkflowExecution.Status.SUCCEEDED,
                    "10.10.90.120 Excel 巡检闭环样例",
                    None,
                    False,
                ),
                (
                    "health-warning",
                    "health_docx",
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
                if workflow_key in {"health_docx", "health_xlsx"}:
                    output["job"] = _health_job_output(collected_at=now.isoformat(), warning=warning)
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

        self.stdout.write(self.style.SUCCESS(f"已清理旧演示数据，并为团队 {team_id} 生成 7 条流程、11 条执行记录（含 Word/Excel 巡检与 1 条待审批）。"))
