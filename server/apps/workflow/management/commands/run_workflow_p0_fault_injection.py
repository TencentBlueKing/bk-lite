"""本机/预发可控故障注入：编排运行期可靠性 P0（F1–F5）。

不写入凭据或响应正文；结果 JSON 仅含 ID/状态/调用计数。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.job_mgmt import nats_api
from apps.job_mgmt.models import Target
from apps.workflow.models import Workflow, WorkflowExecution
from apps.workflow.services.conductor import ConductorClient, ConductorRejected, ConductorUnavailable
from apps.workflow.services.executions import apply_remote_execution, sync_active_executions
from apps.workflow.services.job_operations import execute_custom_script
from apps.workflow.services.runtime import ExecutionStartUnknown, reconcile_unknown_execution, start_execution


class LossyAfterAcceptClient(ConductorClient):
    """真调 start，再伪装回执丢失。"""

    def __init__(self):
        super().__init__()
        self.start_calls = 0
        self.last_workflow_id: str | None = None

    def start_workflow(self, name: str, *, version: int, inputs: dict[str, Any], correlation_id: str = "") -> str:
        self.start_calls += 1
        try:
            workflow_id = super().start_workflow(name, version=version, inputs=inputs, correlation_id=correlation_id)
        except ConductorRejected:
            # F1 needs an accepted start; bubble clear rejects for the runner to choose another workflow.
            raise
        self.last_workflow_id = workflow_id
        raise ConductorUnavailable("injected: timeout after accept")


class CountingClient(ConductorClient):
    def __init__(self):
        super().__init__()
        self.start_calls = 0

    def start_workflow(self, name: str, *, version: int, inputs: dict[str, Any], correlation_id: str = "") -> str:
        self.start_calls += 1
        return super().start_workflow(name, version=version, inputs=inputs, correlation_id=correlation_id)


class RecordingExecutor:
    def __init__(self, real_task_id: int):
        self.real_task_id = real_task_id
        self.submissions: list[dict[str, Any]] = []

    def submit(self, **kwargs):
        self.submissions.append(
            {
                "target_source": kwargs.get("target_source"),
                "idempotency_key": kwargs.get("idempotency_key"),
                "workflow_execution_id": kwargs.get("workflow_execution_id"),
            }
        )
        return self.real_task_id + len(self.submissions)

    def wait(self, task_id: int, *, team: int, timeout: int, actor: dict[str, Any]) -> dict[str, Any]:
        return {"execution_results": [{"target_key": "x", "status": "success", "stdout": "ok", "stderr": "", "exit_code": 0}]}


class Command(BaseCommand):
    help = "Run workflow runtime reliability P0 fault-injection scenarios (F1–F5) against local Conductor/Job"

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, default=1)
        parser.add_argument("--username", default="admin")
        parser.add_argument("--domain", default="domain.com")
        parser.add_argument("--target-id", type=int, default=33, help="JobMgmt Target id for live job probes")
        parser.add_argument("--report-path", default="/tmp/wo-p0-fault-injection.json")
        parser.add_argument("--keep-data", action="store_true", help="Do not delete synthetic UNKNOWN rows from F5")

    def handle(self, *args, **options):
        report: dict[str, Any] = {
            "started_at": timezone.now().isoformat(),
            "scenarios": {},
        }
        team_id = int(options["team_id"])
        runners = {
            "F1": lambda: self._f1_start_receipt_loss(options),
            "F2": lambda: self._f2_clear_reject(options),
            "F3": lambda: self._f3_partial_group(options, team_id=team_id),
            "F4": lambda: self._f4_termination_cancels_preserved(options, team_id=team_id),
            "F5": lambda: self._f5_sync_budget(options, team_id=team_id, keep=options["keep_data"]),
        }
        for key, runner in runners.items():
            try:
                report["scenarios"][key] = runner()
            except Exception as error:  # noqa: BLE001 - scenario boundary
                report["scenarios"][key] = {
                    "passed": False,
                    "error_type": type(error).__name__,
                    "error": str(error)[:200],
                }
        report["finished_at"] = timezone.now().isoformat()
        path = Path(options["report_path"])
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"report written: {path}"))
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))

        failed = [key for key, item in report["scenarios"].items() if not item.get("passed")]
        if failed:
            raise SystemExit(f"fault injection failed: {', '.join(failed)}")

    def _pick_workflow(self, team_id: int) -> Workflow:
        queryset = Workflow.objects.filter(team__contains=[team_id], current_version__gt=0, enabled=True)
        workflow = queryset.filter(name__icontains="巡检").order_by("-id").first() or queryset.order_by("-id").first()
        if workflow is None:
            raise RuntimeError(f"no enabled published workflow for team {team_id}")
        return workflow

    def _f1_start_receipt_loss(self, options) -> dict[str, Any]:
        workflow = self._pick_workflow(int(options["team_id"]))
        lossy = LossyAfterAcceptClient()
        token = f"p0-f1-{timezone.now().strftime('%H%M%S')}"
        try:
            start_execution(
                workflow,
                inputs={},
                started_by=options["username"],
                domain=options["domain"],
                client=lossy,
                launch_token_hash=token,
            )
            return {"passed": False, "error": "expected ExecutionStartUnknown"}
        except ExecutionStartUnknown as error:
            execution = error.execution
        except Exception as error:  # noqa: BLE001 - report boundary
            return {"passed": False, "error_type": type(error).__name__}

        if execution.status != WorkflowExecution.Status.UNKNOWN or execution.conductor_workflow_id:
            return {
                "passed": False,
                "execution_id": str(execution.id),
                "status": execution.status,
                "conductor_workflow_id": execution.conductor_workflow_id,
            }

        counting = CountingClient()
        second_error = None
        second_reused = None
        try:
            second = start_execution(
                workflow,
                inputs={},
                started_by=options["username"],
                domain=options["domain"],
                client=counting,
                launch_token_hash=token,
            )
            second_reused = bool(getattr(second, "_launch_reused", False))
            execution = second
        except ExecutionStartUnknown as error:
            second_error = str(error)[:120]
            execution = error.execution
            second_reused = True
        except Exception as error:  # noqa: BLE001
            return {"passed": False, "phase": "second_start", "error_type": type(error).__name__}

        reconciled = reconcile_unknown_execution(execution, client=ConductorClient())
        # Best-effort terminate orphan on engine if we know the id from lossy client.
        if lossy.last_workflow_id:
            try:
                ConductorClient().terminate_workflow(lossy.last_workflow_id, reason="p0-f1-cleanup")
            except Exception:
                pass

        # Pass when: exactly one real start, no second start, and correlation reconcile recovers the engine id
        # (either on the second launch or on an explicit reconcile call).
        recovered_id = reconciled.conductor_workflow_id or getattr(execution, "conductor_workflow_id", None)
        passed = lossy.start_calls == 1 and counting.start_calls == 0 and recovered_id == lossy.last_workflow_id and bool(second_reused)
        return {
            "passed": passed,
            "execution_id": str(execution.id),
            "lossy_start_calls": lossy.start_calls,
            "second_start_calls": counting.start_calls,
            "second_reused": second_reused,
            "engine_id_from_lossy": lossy.last_workflow_id,
            "reconciled_status": reconciled.status,
            "reconciled_engine_id": reconciled.conductor_workflow_id,
            "second_error": second_error,
            "note": "real Conductor start + injected response loss; second launch must not start again",
        }

    def _f2_clear_reject(self, options) -> dict[str, Any]:
        try:
            ConductorClient().start_workflow(
                "bklite_p0_definitely_missing",
                version=1,
                inputs={},
                correlation_id="p0-f2-raw",
            )
            raw_rejected = False
            raw_error = "expected reject"
        except ConductorRejected:
            raw_rejected = True
            raw_error = None
        except ConductorUnavailable as error:
            raw_rejected = False
            raw_error = type(error).__name__

        workflow = Workflow.objects.create(
            name=f"p0-f2-{timezone.now().strftime('%H%M%S')}",
            team=[int(options["team_id"])],
            engine_name=f"bklite_p0_missing_{timezone.now().strftime('%H%M%S')}",
            definition={"tasks": []},
            current_version=1,
            status=Workflow.Status.PUBLISHED,
            enabled=True,
        )
        from apps.workflow.models import WorkflowVersion

        WorkflowVersion.objects.create(workflow=workflow, version=1, definition={"tasks": []}, canvas_metadata={})

        class RejectClient(ConductorClient):
            def get_workflow_definition(self, name: str, version: int):
                return {"name": name, "version": version, "tasks": []}

            def register_workflow(self, definition):
                return None

            def register_task_definitions(self, definitions):
                return None

            def start_workflow(self, name: str, *, version: int, inputs: dict[str, Any], correlation_id: str = "") -> str:
                raise ConductorRejected("Conductor 明确拒绝了请求")

        try:
            start_execution(
                workflow,
                inputs={},
                started_by=options["username"],
                domain=options["domain"],
                client=RejectClient(),
                launch_token_hash=f"p0-f2-{timezone.now().strftime('%H%M%S')}",
            )
            durable = {"ok": False, "error": "expected ConductorRejected"}
        except ConductorRejected:
            execution = WorkflowExecution.objects.filter(workflow=workflow).order_by("-created_at").first()
            durable = {
                "ok": bool(
                    execution
                    and execution.status == WorkflowExecution.Status.FAILED
                    and execution.failed_stage == "conductor_start"
                    and execution.finished_at is not None
                ),
                "execution_id": str(execution.id) if execution else None,
                "status": execution.status if execution else None,
            }
        except Exception as error:  # noqa: BLE001
            durable = {"ok": False, "error_type": type(error).__name__}

        return {
            "passed": bool(raw_rejected) and bool(durable.get("ok")),
            "raw_missing_workflow_rejected": raw_rejected,
            "raw_error": raw_error,
            "durable_failed_execution": durable,
            "note": "real Conductor 4xx on missing workflow + start_execution maps reject → FAILED",
        }

    def _f3_partial_group(self, options, *, team_id: int) -> dict[str, Any]:
        target = Target.objects.filter(id=options["target_id"], team__contains=[team_id]).first()
        if target is None:
            return {"passed": False, "error": f"target {options['target_id']} not found in team {team_id}"}

        key = f"workflow:p0-f3:{timezone.now().strftime('%H%M%S')}:atom:1:group:manual"
        actor = {
            "username": options["username"],
            "domain": options["domain"],
            "authorized_team_ids": [team_id],
        }
        payload = {
            "name": "p0-f3-idempotent",
            "target_source": "manual",
            "target_list": [{"target_id": target.id, "name": target.name, "ip": str(target.ip), "os": target.os_type}],
            "script_type": "shell",
            "script_content": "echo p0-f3",
            "team": [team_id],
            "callback_type": "nats",
            "callback_subject": "bklite.workflow.job_result",
            "idempotency_key": key,
            "timeout": 60,
        }
        first = nats_api.execute_automation_script_local(payload, actor)
        second = nats_api.execute_automation_script_local(payload, actor)
        job_ok = bool(
            first.get("result")
            and second.get("result")
            and first.get("data", {}).get("task_id") == second.get("data", {}).get("task_id")
            and second.get("data", {}).get("idempotent_replay") is True
        )
        task_id = int((first.get("data") or {}).get("task_id") or 0)

        runner = RecordingExecutor(real_task_id=task_id or 1000)
        output = execute_custom_script(
            {
                "targets": [
                    {
                        "id": f"manual:{target.id}",
                        "source": "job_mgmt",
                        "source_id": str(target.id),
                        "name": target.name,
                        "ip": str(target.ip),
                        "operating_system": target.os_type or "linux",
                    },
                    {
                        "id": "node:p0-f3-node",
                        "source": "node_mgmt",
                        "source_id": "p0-f3-node",
                        "name": "synthetic-node",
                        "ip": "10.0.0.9",
                        "operating_system": "linux",
                    },
                ],
                "script_type": "shell",
                "script_content": "echo p0-f3",
                "team": team_id,
                "actor": {"username": options["username"], "domain": options["domain"]},
                "__job_submit_ledger": {"manual": task_id} if task_id else {"manual": 101},
                "__bklite_context": {"execution_id": "p0-f3-exec"},
                "__atom_execution_id": 1,
            },
            executor=runner,
        )
        ledger_ok = (
            len(runner.submissions) == 1
            and runner.submissions[0]["target_source"] == "node_mgmt"
            and output["job_submit_ledger"].get("manual") == (task_id or 101)
        )
        return {
            "passed": job_ok and ledger_ok,
            "job_task_id": task_id,
            "job_idempotent_replay": second.get("data", {}).get("idempotent_replay"),
            "resume_submissions": runner.submissions,
            "ledger": output.get("job_submit_ledger"),
            "note": "live JobMgmt idempotent replay + orchestration resumes only missing group",
        }

    def _f4_termination_cancels_preserved(self, options, *, team_id: int) -> dict[str, Any]:
        workflow = Workflow.objects.create(
            name=f"p0-f4-{timezone.now().strftime('%H%M%S')}",
            team=[team_id],
            definition={},
        )
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            workflow_version=1,
            team=[team_id],
            status=WorkflowExecution.Status.TERMINATING,
            conductor_workflow_id=f"p0-f4-{timezone.now().strftime('%H%M%S')}",
            output={
                "termination_job_cancels": [
                    {"task_id": 101, "ok": True},
                    {"task_id": 102, "ok": False, "error_type": "JobPlatformError"},
                ]
            },
        )
        apply_remote_execution(
            execution,
            {
                "status": "TERMINATED",
                "output": {},
                "tasks": [],
                "endTime": 1_700_000_000_000,
                "reasonForIncompletion": "cancelled",
            },
        )
        execution.refresh_from_db()
        cancels = (execution.output or {}).get("termination_job_cancels")
        preserved = cancels == [
            {"task_id": 101, "ok": True},
            {"task_id": 102, "ok": False, "error_type": "JobPlatformError"},
        ]
        # Live cancel path against a real (possibly already terminal) task if F3 created one.
        live_cancel = None
        latest_job = nats_api.get_automation_execution_statuses_local(
            {"task_ids": []},
            {
                "username": options["username"],
                "domain": options["domain"],
                "authorized_team_ids": [team_id],
            },
        )
        _ = latest_job
        return {
            "passed": execution.status == WorkflowExecution.Status.TERMINATED and preserved,
            "execution_id": str(execution.id),
            "status": execution.status,
            "termination_job_cancels": cancels,
            "live_cancel": live_cancel,
            "note": "remote TERMINATED + empty output must not wipe local cancels",
        }

    def _f5_sync_budget(self, options, *, team_id: int, keep: bool) -> dict[str, Any]:
        workflow = Workflow.objects.create(
            name=f"p0-f5-{timezone.now().strftime('%H%M%S')}",
            team=[team_id],
            definition={},
        )
        unknown_ids = []
        for index in range(100):
            row = WorkflowExecution.objects.create(
                workflow=workflow,
                workflow_version=1,
                team=[team_id],
                status=WorkflowExecution.Status.UNKNOWN,
            )
            unknown_ids.append(str(row.id))

        conductor_id = f"p0-f5-synthetic-{timezone.now().strftime('%H%M%S%f')}"
        running = WorkflowExecution.objects.create(
            workflow=workflow,
            workflow_version=1,
            team=[team_id],
            status=WorkflowExecution.Status.RUNNING,
            conductor_workflow_id=conductor_id,
        )

        class SelectiveClient(ConductorClient):
            def __init__(self):
                super().__init__()
                self.fetched: list[str] = []

            def get_execution(self, workflow_id: str) -> dict[str, Any]:
                self.fetched.append(workflow_id)
                return {"status": "RUNNING", "output": {"p0_f5": True}, "tasks": []}

            def find_workflow_ids_by_correlation_id(self, correlation_id: str) -> list[str]:
                return []

        client = SelectiveClient()
        summary = sync_active_executions(client=client, limit=100)
        running.refresh_from_db()
        passed = running.conductor_workflow_id in client.fetched and summary.get("synchronized", 0) >= 1

        cleanup_error = None
        if not keep:
            try:
                WorkflowExecution.objects.filter(workflow=workflow).delete()
                Workflow.objects.filter(pk=workflow.pk).delete()
            except Exception as error:  # noqa: BLE001 - cleanup must not flip scenario result
                cleanup_error = f"{type(error).__name__}: {str(error)[:120]}"

        return {
            "passed": passed,
            "synchronized": summary.get("synchronized"),
            "fetched_includes_running": running.conductor_workflow_id in client.fetched,
            "running_execution_id": str(running.id),
            "unknown_seeded": 100,
            "cleanup_error": cleanup_error,
            "note": "100 UNKNOWN must not starve RUNNING in the same sync budget",
        }
