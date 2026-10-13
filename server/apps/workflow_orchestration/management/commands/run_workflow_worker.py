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


def _conductor_task_update(*, workflow_id, task_id, worker_id, status, output_data=None, callback_after_seconds=None, reason=None):
    payload = {
        "workflowInstanceId": workflow_id,
        "taskId": task_id,
        "workerId": worker_id,
        "status": status,
        "outputData": {} if output_data is None else output_data,
    }
    if callback_after_seconds is not None:
        payload["callbackAfterSeconds"] = callback_after_seconds
    if reason is not None:
        payload["reasonForIncompletion"] = reason
    return payload


def _assert_client_execution_matches(execution, client_execution_id):
    if execution is None or client_execution_id in (None, ""):
        return
    if str(execution.id) != str(client_execution_id):
        raise ValueError("节点输入的 execution_id 与引擎执行实例不一致")


def _build_runtime_inputs(*, inputs, atom_execution, task_type, execution):
    runtime_inputs = dict(inputs)
    if atom_execution is not None:
        runtime_inputs["__atom_execution_id"] = atom_execution.pk
        prior_job_ids = (atom_execution.output or {}).get("job_task_ids")
        if isinstance(prior_job_ids, list) and prior_job_ids:
            runtime_inputs["__job_task_ids"] = prior_job_ids
    if not atom_requires_trusted_context(task_type):
        return runtime_inputs
    if execution is None or not execution.team:
        raise ValueError("原子缺少可信的流程执行上下文")
    return {
        **runtime_inputs,
        "__bklite_context": {
            "execution_id": str(execution.id),
            "workflow_id": str(execution.workflow_id),
            "workflow_version": execution.workflow_version,
            "organization_id": execution.team[0],
            "actor": {"username": execution.started_by, "domain": execution.domain},
            "trigger_type": execution.trigger_type,
        },
    }


def _renew_atom_lease(atom_execution, claim_token, lease_duration) -> bool:
    return bool(
        AtomExecution.objects.filter(
            pk=atom_execution.pk,
            claim_token=claim_token,
            status=AtomExecution.Status.RUNNING,
        ).update(lease_expires_at=timezone.now() + lease_duration, updated_at=timezone.now())
    )


def _run_atom_with_heartbeat(
    *,
    client,
    execute,
    runtime_inputs,
    interval,
    atom_execution,
    claim_token,
    lease_duration,
    workflow_id,
    task_id,
    worker_id,
    task_type,
):
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="workflow-atom") as executor:
        future = executor.submit(execute, runtime_inputs)
        while True:
            try:
                return future.result(timeout=interval)
            except FutureTimeout:
                if atom_execution is not None:
                    if not _renew_atom_lease(atom_execution, claim_token, lease_duration):
                        logger.warning(
                            "event=workflow_atom_lease_lost task_type=%s task_id=%s",
                            task_type,
                            task_id,
                        )
                        return None
                try:
                    client.update_task(
                        _conductor_task_update(
                            workflow_id=workflow_id,
                            task_id=task_id,
                            worker_id=worker_id,
                            status="IN_PROGRESS",
                            callback_after_seconds=max(1, int(interval * 3)),
                        )
                    )
                except ConductorUnavailable:
                    logger.warning(
                        "event=workflow_atom_heartbeat_failed task_type=%s task_id=%s",
                        task_type,
                        task_id,
                    )


def _finalize_atom_success(*, atom_execution, claim_token, output, task_type, task_id) -> bool:
    if atom_execution is None:
        return True
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
        return False
    atom_execution.status = terminal_status
    atom_execution.output = output
    artifact_id = (output.get("artifact") or {}).get("id")
    if artifact_id:
        ExecutionArtifact.objects.filter(pk=artifact_id, execution=atom_execution.execution).update(atom_execution=atom_execution)
    return True


def _finalize_atom_failure(*, atom_execution, claim_token, error, task_type, task_id) -> bool:
    if atom_execution is None or claim_token is None:
        return True
    still_owner = AtomExecution.objects.filter(
        pk=atom_execution.pk,
        claim_token=claim_token,
        status=AtomExecution.Status.RUNNING,
    ).update(
        status=AtomExecution.Status.FAILED,
        error_type=type(error).__name__[:100],
        error_message=str(error)[:500],
        finished_at=timezone.now(),
        claim_token=None,
        lease_expires_at=None,
        updated_at=timezone.now(),
    )
    if not still_owner:
        logger.warning(
            "event=workflow_atom_result_fenced task_type=%s task_id=%s failed_stage=failure_report",
            task_type,
            task_id,
        )
        return False
    return True


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
    def _claim_atom_execution(
        *,
        client,
        worker_id,
        task_type,
        task,
        execution,
        sealed_inputs,
        retry_count,
        interval,
        lease_duration,
        claim_token,
    ):
        """占用或复用原子执行租约；返回 (atom_execution, early_exit)。"""
        if execution is None:
            return None, False
        task_id = task.get("taskId")
        workflow_id = task.get("workflowInstanceId")
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
                    _conductor_task_update(
                        workflow_id=workflow_id,
                        task_id=task_id,
                        worker_id=worker_id,
                        status="COMPLETED",
                        output_data=atom_execution.output,
                    )
                )
                return atom_execution, True
            if (
                atom_execution is not None
                and atom_execution.status == AtomExecution.Status.RUNNING
                and atom_execution.lease_expires_at
                and atom_execution.lease_expires_at > now
            ):
                client.update_task(
                    _conductor_task_update(
                        workflow_id=workflow_id,
                        task_id=task_id,
                        worker_id=worker_id,
                        status="IN_PROGRESS",
                        callback_after_seconds=max(1, int(interval * 3)),
                    )
                )
                return atom_execution, True
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
        return atom_execution, False

    @staticmethod
    def _execute_task(client, worker_id, task_type, task, handler=None, heartbeat_interval=None):
        task_id = task.get("taskId")
        workflow_id = task.get("workflowInstanceId")
        if not task_id or not workflow_id:
            logger.warning("Ignore malformed Conductor task task_type=%s", task_type)
            return
        atom_execution = None
        claim_token = None
        try:
            sealed_inputs = task.get("inputData", {}) or {}
            inputs = resolve_secret_envelopes(sealed_inputs)
            retry_count = task.get("retryCount", 0)
            # Trust only the engine instance binding; never select identity by client execution_id alone.
            execution = WorkflowExecution.objects.filter(conductor_workflow_id=workflow_id).first()
            _assert_client_execution_matches(execution, inputs.get("execution_id"))
            interval = heartbeat_interval or max(1.0, float(os.getenv("WORKFLOW_WORKER_HEARTBEAT_SECONDS", "15")))
            lease_duration = timedelta(seconds=max(60, int(interval * 4)))
            claim_token = uuid.uuid4()
            atom_execution, early_exit = Command._claim_atom_execution(
                client=client,
                worker_id=worker_id,
                task_type=task_type,
                task=task,
                execution=execution,
                sealed_inputs=sealed_inputs,
                retry_count=retry_count,
                interval=interval,
                lease_duration=lease_duration,
                claim_token=claim_token,
            )
            if early_exit:
                return
            execute = handler or (
                lambda payload: execute_atom(
                    task_type,
                    payload,
                    retry_count=retry_count if isinstance(retry_count, int) else 0,
                )
            )
            runtime_inputs = _build_runtime_inputs(
                inputs=inputs,
                atom_execution=atom_execution,
                task_type=task_type,
                execution=execution,
            )
            output = _run_atom_with_heartbeat(
                client=client,
                execute=execute,
                runtime_inputs=runtime_inputs,
                interval=interval,
                atom_execution=atom_execution,
                claim_token=claim_token,
                lease_duration=lease_duration,
                workflow_id=workflow_id,
                task_id=task_id,
                worker_id=worker_id,
                task_type=task_type,
            )
            if output is None:
                return
            if not _finalize_atom_success(
                atom_execution=atom_execution,
                claim_token=claim_token,
                output=output,
                task_type=task_type,
                task_id=task_id,
            ):
                return
            result = _conductor_task_update(
                workflow_id=workflow_id,
                task_id=task_id,
                worker_id=worker_id,
                status="COMPLETED",
                output_data=output,
            )
        except Exception as error:
            if not _finalize_atom_failure(
                atom_execution=atom_execution,
                claim_token=claim_token,
                error=error,
                task_type=task_type,
                task_id=task_id,
            ):
                return
            safe_error = RuntimeError("atom execution failed")
            logger.error(
                "event=workflow_atom_failed task_type=%s task_id=%s failed_stage=execute error_type=%s",
                task_type,
                task_id,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
            result = _conductor_task_update(
                workflow_id=workflow_id,
                task_id=task_id,
                worker_id=worker_id,
                status="FAILED",
                reason=f"{type(error).__name__}: atom execution failed",
            )
        client.update_task(result)
