import json
import time

from django.core.management.base import BaseCommand, CommandError

from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowVersion
from apps.workflow_orchestration.services.conductor import ConductorClient
from apps.workflow_orchestration.services.definitions import prepare_definition_for_publish
from apps.workflow_orchestration.services.executions import apply_remote_execution
from apps.workflow_orchestration.services.runtime import start_execution


class Command(BaseCommand):
    help = "使用真实 Conductor API 执行不依赖外部业务系统的引擎烟雾验收"

    def add_arguments(self, parser):
        parser.add_argument("--team", type=int, default=1)
        parser.add_argument("--timeout", type=int, default=30)

    def handle(self, *args, **options):
        team = max(1, int(options["team"]))
        timeout = max(5, min(int(options["timeout"]), 120))
        client = ConductorClient()
        draft = {
            "name": "engine_acceptance_draft",
            "version": 1,
            "schemaVersion": 2,
            "inputParameters": ["value", "execution_id", "team"],
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
        }
        workflow = Workflow.objects.create(
            name="MVP验收-真实Conductor",
            description="由 verify_workflow_orchestration_engine 生成",
            team=[team],
            definition=draft,
            created_by="mvp-verifier",
            updated_by="mvp-verifier",
        )
        published = prepare_definition_for_publish(draft, engine_name=workflow.engine_name, version=1)
        client.register_workflow(published)
        WorkflowVersion.objects.create(
            workflow=workflow,
            version=1,
            definition=published,
            resource_snapshot={"atoms": []},
            created_by="mvp-verifier",
        )
        workflow.current_version = 1
        workflow.status = Workflow.Status.PUBLISHED
        workflow.enabled = True
        workflow.save(update_fields=("current_version", "status", "enabled", "updated_at"))
        execution = start_execution(
            workflow,
            inputs={"value": "ok"},
            started_by="mvp-verifier",
            domain="local",
            client=client,
        )

        deadline = time.monotonic() + timeout
        remote = None
        while time.monotonic() < deadline:
            remote = client.get_execution(execution.conductor_workflow_id)
            if remote.get("status") in {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "TIMED_OUT", "TERMINATED"}:
                break
            time.sleep(0.2)
        if remote is None or remote.get("status") != "COMPLETED":
            raise CommandError(f"Conductor 验收未成功终止: {(remote or {}).get('status')}")
        apply_remote_execution(execution, remote)
        execution.refresh_from_db()
        if execution.status != WorkflowExecution.Status.SUCCEEDED:
            raise CommandError(f"BK-Lite 状态对账失败: {execution.status}")

        self.stdout.write(
            json.dumps(
                {
                    "workflow_id": workflow.id,
                    "workflow_version": 1,
                    "execution_id": str(execution.id),
                    "conductor_workflow_id": execution.conductor_workflow_id,
                    "status": execution.status,
                    "engine_task": "SWITCH",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
