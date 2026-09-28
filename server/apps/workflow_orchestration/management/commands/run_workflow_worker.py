import os
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.logger import workflow_orchestration_logger as logger
from apps.workflow_orchestration.models import AtomExecution, ExecutionArtifact, WorkflowExecution
from apps.workflow_orchestration.services.atom_packages import atom_requires_trusted_context, register_atom_packages
from apps.workflow_orchestration.services.atoms import ATOM_HANDLERS, TASK_DEFINITIONS, execute_atom, package_atom_task_definitions
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.data_contracts import mask_secret_envelopes, resolve_secret_envelopes


class Command(BaseCommand):
    help = "运行编排中心 Conductor 原子 Worker（独立运行，不属于启动依赖）"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="每种原子只轮询一次后退出")

    def handle(self, *args, **options):
        client = ConductorClient()
        worker_id = os.getenv("WORKFLOW_WORKER_ID", f"bklite-{socket.gethostname()}")[:100]
        try:
            package_summary = register_atom_packages()
            logger.info(
                "event=workflow_atom_packages_registered packages=%s created_atoms=%s updated_atoms=%s",
                package_summary["packages"],
                package_summary["created_atoms"],
                package_summary["updated_atoms"],
            )
        except Exception as error:
            logger.warning(
                "event=workflow_atom_packages_registration_failed failed_stage=runtime_registry error_type=%s",
                type(error).__name__,
            )
        package_definitions = package_atom_task_definitions()
        task_types = [*ATOM_HANDLERS, *(item["name"] for item in package_definitions)]
        try:
            client.register_task_definitions([*TASK_DEFINITIONS, *package_definitions])
        except ConductorUnavailable as error:
            raise RuntimeError("Conductor 不可用，Worker 未启动") from error

        self.stdout.write(self.style.SUCCESS(f"编排中心 Worker 已启动: {worker_id}"))
        last_registry_refresh = time.monotonic()
        while True:
            if time.monotonic() - last_registry_refresh >= 30:
                try:
                    register_atom_packages()
                    refreshed = package_atom_task_definitions()
                    refreshed_types = [*ATOM_HANDLERS, *(item["name"] for item in refreshed)]
                    if refreshed_types != task_types:
                        client.register_task_definitions([*TASK_DEFINITIONS, *refreshed])
                        task_types = refreshed_types
                except Exception as error:
                    logger.warning(
                        "event=workflow_atom_registry_refresh_failed failed_stage=registry_refresh error_type=%s",
                        type(error).__name__,
                    )
                last_registry_refresh = time.monotonic()
            handled = False
            for task_type in task_types:
                try:
                    task = client.poll_task(task_type, worker_id)
                    if not task:
                        continue
                    handled = True
                    self._execute_task(client, worker_id, task_type, task)
                except ConductorUnavailable:
                    logger.warning("Conductor poll unavailable task_type=%s", task_type)
            if options["once"]:
                return
            time.sleep(0.25 if handled else 1.0)

    @staticmethod
    def _execute_task(client, worker_id, task_type, task, handler=None, heartbeat_interval=None):
        task_id = task.get("taskId")
        workflow_id = task.get("workflowInstanceId")
        if not task_id or not workflow_id:
            logger.warning("Ignore malformed Conductor task task_type=%s", task_type)
            return
        try:
            sealed_inputs = task.get("inputData", {}) or {}
            inputs = resolve_secret_envelopes(sealed_inputs)
            retry_count = task.get("retryCount", 0)
            execution_id = inputs.get("execution_id")
            atom_execution = None
            execution = WorkflowExecution.objects.filter(pk=execution_id).first() if execution_id else None
            if execution is None:
                execution = WorkflowExecution.objects.filter(conductor_workflow_id=workflow_id).first()
            interval = heartbeat_interval or max(1.0, float(os.getenv("WORKFLOW_WORKER_HEARTBEAT_SECONDS", "15")))
            lease_duration = timedelta(seconds=max(60, int(interval * 4)))
            claim_token = uuid.uuid4()
            if execution is not None:
                task_reference = str(task.get("referenceTaskName") or task_type)[:100]
                attempt = max(1, int(retry_count) + 1) if isinstance(retry_count, int) else 1
                with transaction.atomic():
                    atom_execution = (
                        AtomExecution.objects.select_for_update()
                        .filter(
                            execution=execution,
                            task_reference=task_reference,
                            attempt=attempt,
                        )
                        .first()
                    )
                    now = timezone.now()
                    if atom_execution is not None and atom_execution.status in {
                        AtomExecution.Status.COMPLETED,
                        AtomExecution.Status.SKIPPED,
                    }:
                        client.update_task(
                            {
                                "workflowInstanceId": workflow_id,
                                "taskId": task_id,
                                "workerId": worker_id,
                                "status": "COMPLETED",
                                "outputData": atom_execution.output,
                            }
                        )
                        return
                    if (
                        atom_execution is not None
                        and atom_execution.status == AtomExecution.Status.RUNNING
                        and atom_execution.lease_expires_at
                        and atom_execution.lease_expires_at > now
                    ):
                        client.update_task(
                            {
                                "workflowInstanceId": workflow_id,
                                "taskId": task_id,
                                "workerId": worker_id,
                                "status": "IN_PROGRESS",
                                "callbackAfterSeconds": max(1, int(interval * 3)),
                                "outputData": {},
                            }
                        )
                        return
                    if atom_execution is None:
                        atom_execution = AtomExecution.objects.create(
                            execution=execution,
                            task_reference=task_reference,
                            attempt=attempt,
                        )
                    atom_execution.conductor_task_id = str(task_id)[:100]
                    atom_execution.atom_key = task_type
                    atom_execution.status = AtomExecution.Status.RUNNING
                    atom_execution.input = mask_secret_envelopes(sealed_inputs)
                    atom_execution.started_at = atom_execution.started_at or now
                    atom_execution.finished_at = None
                    atom_execution.claim_token = claim_token
                    atom_execution.lease_expires_at = now + lease_duration
                    atom_execution.save(
                        update_fields=(
                            "conductor_task_id",
                            "atom_key",
                            "status",
                            "input",
                            "started_at",
                            "finished_at",
                            "claim_token",
                            "lease_expires_at",
                            "updated_at",
                        )
                    )
            execute = handler or (
                lambda payload: execute_atom(
                    task_type,
                    payload,
                    retry_count=retry_count if isinstance(retry_count, int) else 0,
                )
            )
            runtime_inputs = inputs
            if atom_requires_trusted_context(task_type):
                if execution is None or not execution.team:
                    raise ValueError("原子缺少可信的流程执行上下文")
                runtime_inputs = {
                    **inputs,
                    "__bklite_context": {
                        "execution_id": str(execution.id),
                        "workflow_id": str(execution.workflow_id),
                        "workflow_version": execution.workflow_version,
                        "organization_id": execution.team[0],
                        "actor": {"username": execution.started_by, "domain": execution.domain},
                        "trigger_type": execution.trigger_type,
                    },
                }
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="workflow-atom") as executor:
                future = executor.submit(execute, runtime_inputs)
                while True:
                    try:
                        output = future.result(timeout=interval)
                        break
                    except FutureTimeout:
                        if atom_execution is not None:
                            still_owner = AtomExecution.objects.filter(
                                pk=atom_execution.pk,
                                claim_token=claim_token,
                                status=AtomExecution.Status.RUNNING,
                            ).update(lease_expires_at=timezone.now() + lease_duration, updated_at=timezone.now())
                            if not still_owner:
                                logger.warning(
                                    "event=workflow_atom_lease_lost task_type=%s task_id=%s",
                                    task_type,
                                    task_id,
                                )
                                return
                        try:
                            client.update_task(
                                {
                                    "workflowInstanceId": workflow_id,
                                    "taskId": task_id,
                                    "workerId": worker_id,
                                    "status": "IN_PROGRESS",
                                    "callbackAfterSeconds": max(1, int(interval * 3)),
                                    "outputData": {},
                                }
                            )
                        except ConductorUnavailable:
                            logger.warning(
                                "event=workflow_atom_heartbeat_failed task_type=%s task_id=%s",
                                task_type,
                                task_id,
                            )
            if atom_execution is not None:
                terminal_status = AtomExecution.Status.SKIPPED if output.get("skipped") else AtomExecution.Status.COMPLETED
                still_owner = AtomExecution.objects.filter(
                    pk=atom_execution.pk,
                    claim_token=claim_token,
                    status=AtomExecution.Status.RUNNING,
                ).update(
                    status=terminal_status,
                    output=output,
                    job_task_id=output.get("job_task_id"),
                    finished_at=timezone.now(),
                    claim_token=None,
                    lease_expires_at=None,
                    updated_at=timezone.now(),
                )
                if not still_owner:
                    logger.warning("event=workflow_atom_result_fenced task_type=%s task_id=%s", task_type, task_id)
                    return
                atom_execution.status = terminal_status
                atom_execution.output = output
                artifact_id = (output.get("artifact") or {}).get("id")
                if artifact_id:
                    ExecutionArtifact.objects.filter(pk=artifact_id, execution=atom_execution.execution).update(atom_execution=atom_execution)
            result = {
                "workflowInstanceId": workflow_id,
                "taskId": task_id,
                "workerId": worker_id,
                "status": "COMPLETED",
                "outputData": output,
            }
        except Exception as error:
            if "atom_execution" in locals() and atom_execution is not None:
                AtomExecution.objects.filter(pk=atom_execution.pk, claim_token=claim_token).update(
                    status=AtomExecution.Status.FAILED,
                    error_type=type(error).__name__[:100],
                    error_message=str(error)[:500],
                    finished_at=timezone.now(),
                    claim_token=None,
                    lease_expires_at=None,
                    updated_at=timezone.now(),
                )
            safe_error = RuntimeError("atom execution failed")
            logger.error(
                "event=workflow_atom_failed task_type=%s task_id=%s failed_stage=execute error_type=%s",
                task_type,
                task_id,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
            result = {
                "workflowInstanceId": workflow_id,
                "taskId": task_id,
                "workerId": worker_id,
                "status": "FAILED",
                "reasonForIncompletion": f"{type(error).__name__}: atom execution failed",
                "outputData": {},
            }
        client.update_task(result)
