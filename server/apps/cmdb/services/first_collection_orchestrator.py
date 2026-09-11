import uuid
from datetime import timedelta

from celery import current_app
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.cmdb.constants import constants as cmdb_constants
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.first_collection_run import FirstCollectionRun
from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info
from apps.rpc.node_mgmt import NodeMgmt

ACCEPTED_CHANNEL_STATUSES = frozenset({"accepted", "duplicate_active"})


class FirstCollectionOrchestrator:
    CELERY_TASK = "apps.cmdb.tasks.celery_tasks.execute_first_collection_run"
    MAX_ATTEMPTS = 3
    MAX_CONFIG_RECOVERY_ATTEMPTS = 3
    MAX_DISPATCH_ATTEMPTS = 3
    MAX_LOCK_RETRIES = 8
    LOCK_RETRY_AFTER_SECONDS = 10
    LEASE_SECONDS = 90
    RECOVERY_STALE_AFTER = timedelta(minutes=1)
    RECOVERY_LIMIT = 100

    @staticmethod
    def expected_config_ids(task) -> list[str]:
        return [f"cmdb_{task.id}{'_topology' if channel == 'topology' else ''}" for channel in FirstCollectionPolicy.eligible_channels(task)]

    @classmethod
    def schedule(cls, task, *, old_task=None, reason="create"):
        with transaction.atomic():
            if not cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED or not FirstCollectionPolicy.is_eligible(task):
                return None
            if old_task is not None:
                changed_fields = FirstCollectionPolicy.changed_fields(old_task, task)
                if not changed_fields:
                    return None
                reason = f"update:{','.join(changed_fields)}"
            fingerprint = FirstCollectionPolicy.fingerprint(task)
            initial_channels = {
                config_id: {
                    "status": "pending",
                    "task_id": "",
                    "retryable": True,
                }
                for config_id in cls.expected_config_ids(task)
            }
            run, _created = FirstCollectionRun.objects.get_or_create(
                collect_task=task,
                fingerprint=fingerprint,
                task_revision=task.updated_at,
                defaults={
                    "reason": reason,
                    "status": FirstCollectionRun.STATUS_WAITING_CONFIG,
                    "channel_results": initial_channels,
                },
            )
            return run

    @classmethod
    def mark_config_ready_and_dispatch(cls, run_id: int):
        with transaction.atomic():
            run = FirstCollectionRun.objects.select_for_update().get(id=run_id)
            if run.status == FirstCollectionRun.STATUS_WAITING_CONFIG:
                run.status = FirstCollectionRun.STATUS_PENDING
                run.failed_stage = ""
                run.error_type = ""
                run.save(update_fields=["status", "failed_stage", "error_type", "updated_at"])
            should_dispatch = run.status in {
                FirstCollectionRun.STATUS_PENDING,
                FirstCollectionRun.STATUS_RETRY_WAIT,
            }
        if should_dispatch:
            cls._dispatch(run)
        return run

    @classmethod
    def _dispatch(cls, run: FirstCollectionRun) -> bool:
        try:
            current_app.send_task(cls.CELERY_TASK, args=[run.id])
        except Exception as exc:  # noqa: BLE001 - Celery transport is an external boundary.
            cls._record_dispatch_failure(run.id, exc)
            logger.error(
                "event=first_collection_dispatch_failed run_id=%s task_id=%s failed_stage=dispatch error_type=%s",
                run.id,
                run.collect_task_id,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return False
        return True

    @classmethod
    def _record_dispatch_failure(cls, run_id: int, exc: Exception) -> None:
        with transaction.atomic():
            run = (
                FirstCollectionRun.objects.select_for_update()
                .filter(
                    id=run_id,
                    status__in=(
                        FirstCollectionRun.STATUS_PENDING,
                        FirstCollectionRun.STATUS_RETRY_WAIT,
                    ),
                )
                .first()
            )
            if run is None:
                return
            run.dispatch_attempt += 1
            run.failed_stage = "dispatch"
            run.error_type = type(exc).__name__[:128]
            update_fields = [
                "dispatch_attempt",
                "failed_stage",
                "error_type",
                "updated_at",
            ]
            if run.dispatch_attempt >= cls.MAX_DISPATCH_ATTEMPTS:
                accepted_count = sum(item.get("status") in ACCEPTED_CHANNEL_STATUSES for item in (run.channel_results or {}).values())
                run.status = FirstCollectionRun.STATUS_PARTIAL if accepted_count else FirstCollectionRun.STATUS_FAILED
                run.finished_at = timezone.now()
                update_fields.extend(["status", "finished_at"])
            # updated_at rotates a retryable failure behind older stale work.
            run.save(update_fields=update_fields)

    @classmethod
    def recover(cls) -> dict[str, int]:
        now = timezone.now()
        stale_before = now - cls.RECOVERY_STALE_AFTER
        recoverable = Q(
            status__in=(
                FirstCollectionRun.STATUS_WAITING_CONFIG,
                FirstCollectionRun.STATUS_PENDING,
                FirstCollectionRun.STATUS_RETRY_WAIT,
            ),
            updated_at__lte=stale_before,
        ) | Q(
            status=FirstCollectionRun.STATUS_RUNNING,
            lease_expires_at__lte=now,
        )
        run_ids = list(FirstCollectionRun.objects.filter(recoverable).order_by("updated_at", "id").values_list("id", flat=True)[: cls.RECOVERY_LIMIT])
        dispatched = 0
        failed = 0
        for run_id in run_ids:
            try:
                run = FirstCollectionRun.objects.select_related("collect_task").get(id=run_id)
                if run.status == FirstCollectionRun.STATUS_WAITING_CONFIG:
                    from apps.cmdb.services.collect_service import CollectModelService

                    with transaction.atomic():
                        locked = FirstCollectionRun.objects.select_for_update().get(id=run.id)
                        if locked.status != FirstCollectionRun.STATUS_WAITING_CONFIG:
                            continue
                        task = CollectModels.objects.select_for_update().filter(id=locked.collect_task_id).first()
                        skip_reason = cls._skip_reason(task, locked)
                        if skip_reason:
                            run = locked
                        else:
                            # The previous create may have committed in NodeMgmt even
                            # when its RPC acknowledgement was lost. Replace the
                            # expected IDs so recovery converges from either state.
                            CollectModelService.delete_butch_node_params(task)
                            CollectModelService.push_butch_node_params(task)
                            locked.status = FirstCollectionRun.STATUS_PENDING
                            locked.failed_stage = ""
                            locked.error_type = ""
                            locked.save(update_fields=["status", "failed_stage", "error_type", "updated_at"])
                            run = locked
                    if skip_reason:
                        cls.execute(run.id)
                        continue
                if cls._dispatch(run):
                    dispatched += 1
                else:
                    failed += 1
            except Exception as exc:  # noqa: BLE001 - Recovery isolates failures per bounded run.
                failed += 1
                cls._record_recovery_failure(run_id, exc)
                logger.error(
                    "event=first_collection_recovery_failed run_id=%s failed_stage=recovery error_type=%s",
                    run_id,
                    type(exc).__name__,
                    exc_info=safe_exception_info(exc),
                )
        return {"scanned": len(run_ids), "dispatched": dispatched, "failed": failed}

    @classmethod
    def _record_recovery_failure(cls, run_id: int, exc: Exception) -> None:
        with transaction.atomic():
            run = FirstCollectionRun.objects.select_for_update().filter(id=run_id).first()
            if run is None:
                return
            update_fields = ["failed_stage", "error_type", "updated_at"]
            run.error_type = type(exc).__name__[:128]
            if run.status == FirstCollectionRun.STATUS_WAITING_CONFIG:
                run.config_attempt += 1
                run.failed_stage = "config_sync"
                update_fields.append("config_attempt")
                if run.config_attempt >= cls.MAX_CONFIG_RECOVERY_ATTEMPTS:
                    run.status = FirstCollectionRun.STATUS_FAILED
                    run.finished_at = timezone.now()
                    update_fields.extend(["status", "finished_at"])
            elif run.status in {
                FirstCollectionRun.STATUS_PENDING,
                FirstCollectionRun.STATUS_RETRY_WAIT,
            }:
                run.failed_stage = "recovery"
            else:
                return
            # Saving updated_at moves a non-terminal failure behind older stale
            # work so a bounded scan cannot starve later runs.
            run.save(update_fields=update_fields)

    @classmethod
    def execute(cls, run_id: int) -> dict:
        claimed = cls._claim(run_id)
        if isinstance(claimed, dict):
            return claimed
        run, claim_token, config_ids = claimed
        task = run.collect_task
        node_id = cls._node_id(task)
        try:
            result = NodeMgmt().run_telegraf_child_configs_once(
                request_id=f"first-collection-{run.id}",
                config_ids=config_ids,
                expected_node_id=node_id,
                organization_ids=list(task.team or []),
            )
        except Exception as exc:  # noqa: BLE001 - NodeMgmt RPC is an external boundary.
            logger.error(
                "event=first_collection_rpc_failed run_id=%s task_id=%s failed_stage=node_mgmt_rpc error_type=%s",
                run.id,
                run.collect_task_id,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            result = {
                "status": "failed",
                "failed_stage": "node_mgmt_rpc",
                "channels": {
                    config_id: {
                        "status": "failed",
                        "task_id": "",
                        "retryable": True,
                        "error_type": type(exc).__name__,
                    }
                    for config_id in config_ids
                },
            }
        return cls._complete(run.id, claim_token, result)

    @classmethod
    def _claim(cls, run_id: int):
        with transaction.atomic():
            # Lock only the run row. Joining the nullable collect_task relation makes
            # PostgreSQL reject FOR UPDATE on the nullable side of the outer join.
            run = FirstCollectionRun.objects.select_for_update().filter(id=run_id).first()
            if run is None:
                return {"run_id": run_id, "status": "missing"}
            if run.status in {
                FirstCollectionRun.STATUS_ACCEPTED,
                FirstCollectionRun.STATUS_PARTIAL,
                FirstCollectionRun.STATUS_FAILED,
                FirstCollectionRun.STATUS_SKIPPED,
            }:
                return {"run_id": run.id, "status": run.status}
            task = run.collect_task
            skip_reason = cls._skip_reason(task, run)
            if skip_reason:
                run.status = FirstCollectionRun.STATUS_SKIPPED
                run.failed_stage = skip_reason
                run.claim_token = ""
                run.lease_expires_at = None
                run.finished_at = timezone.now()
                run.save(
                    update_fields=[
                        "status",
                        "failed_stage",
                        "claim_token",
                        "lease_expires_at",
                        "finished_at",
                        "updated_at",
                    ]
                )
                logger.warning(
                    "event=first_collection_skipped run_id=%s task_id=%s failed_stage=%s error_type=%s",
                    run.id,
                    run.collect_task_id,
                    skip_reason,
                    "PolicySkip",
                )
                return {"run_id": run.id, "status": skip_reason}
            if run.status == FirstCollectionRun.STATUS_WAITING_CONFIG:
                return {"run_id": run.id, "status": run.status}
            if run.status == FirstCollectionRun.STATUS_RUNNING and run.lease_expires_at and run.lease_expires_at > timezone.now():
                return {"run_id": run.id, "status": run.status}
            if run.attempt >= cls.MAX_ATTEMPTS:
                channels = run.channel_results or {}
                accepted_count = sum(item.get("status") in ACCEPTED_CHANNEL_STATUSES for item in channels.values())
                run.status = FirstCollectionRun.STATUS_PARTIAL if accepted_count else FirstCollectionRun.STATUS_FAILED
                run.failed_stage = run.failed_stage or "one_shot"
                run.error_type = run.error_type or "LeaseExpired"
                run.claim_token = ""
                run.lease_expires_at = None
                run.finished_at = timezone.now()
                run.save(
                    update_fields=[
                        "status",
                        "failed_stage",
                        "error_type",
                        "claim_token",
                        "lease_expires_at",
                        "finished_at",
                        "updated_at",
                    ]
                )
                return {"run_id": run.id, "status": run.status}

            config_ids = [config_id for config_id, item in (run.channel_results or {}).items() if item.get("status") not in ACCEPTED_CHANNEL_STATUSES]
            if not config_ids:
                run.status = FirstCollectionRun.STATUS_ACCEPTED
                run.finished_at = timezone.now()
                run.save(update_fields=["status", "finished_at", "updated_at"])
                return {"run_id": run.id, "status": run.status}

            claim_token = uuid.uuid4().hex
            run.status = FirstCollectionRun.STATUS_RUNNING
            run.claim_token = claim_token
            run.lease_expires_at = timezone.now() + timedelta(seconds=cls.LEASE_SECONDS)
            run.attempt += 1
            if run.started_at is None:
                run.started_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "claim_token",
                    "lease_expires_at",
                    "attempt",
                    "started_at",
                    "updated_at",
                ]
            )
            return run, claim_token, config_ids

    @staticmethod
    def _node_id(task) -> str:
        access_point = getattr(task, "access_point", None) or []
        item = access_point[0] if access_point and isinstance(access_point[0], dict) else {}
        return str(item.get("id") or "")

    @staticmethod
    def _skip_reason(task, run: FirstCollectionRun) -> str:
        if task is None:
            return "missing"
        if not cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED:
            return "disabled"
        if not FirstCollectionPolicy.is_eligible(task):
            return "ineligible"
        if FirstCollectionPolicy.fingerprint(task) != run.fingerprint:
            return "stale"
        # A newer collection intent supersedes this revision even after A -> B -> A.
        # Governance-only edits create no intent and must not cancel pending collection.
        if FirstCollectionRun.objects.filter(collect_task_id=task.id, task_revision__gt=run.task_revision).exists():
            return "stale"
        return ""

    @classmethod
    def _complete(cls, run_id: int, claim_token: str, result: dict) -> dict:
        with transaction.atomic():
            run = FirstCollectionRun.objects.select_for_update().filter(id=run_id, claim_token=claim_token).first()
            if run is None:
                return {"run_id": run_id, "status": "stale_worker"}

            channels = dict(run.channel_results or {})
            for config_id, item in (result.get("channels") or {}).items():
                if config_id not in channels:
                    continue
                if channels[config_id].get("status") in ACCEPTED_CHANNEL_STATUSES:
                    continue
                channels[config_id] = cls._bounded_channel_result(item)

            accepted_count = sum(item.get("status") in ACCEPTED_CHANNEL_STATUSES for item in channels.values())
            retryable = any(item.get("status") not in ACCEPTED_CHANNEL_STATUSES and bool(item.get("retryable")) for item in channels.values())
            failed_channels = [item for item in channels.values() if item.get("status") not in ACCEPTED_CHANNEL_STATUSES]
            node_busy = bool(failed_channels) and all(item.get("error_type") == "NodeBusy" for item in failed_channels)
            retry_after = None
            if accepted_count == len(channels):
                status = FirstCollectionRun.STATUS_ACCEPTED
            elif node_busy:
                # Persist the lock budget across recovery messages, whose Celery
                # retry counters start over. Contention does not spend a business attempt.
                run.attempt = max(0, run.attempt - 1)
                if run.lock_retries < cls.MAX_LOCK_RETRIES:
                    run.lock_retries += 1
                    status = FirstCollectionRun.STATUS_RETRY_WAIT
                    retry_after = cls.LOCK_RETRY_AFTER_SECONDS
                else:
                    status = FirstCollectionRun.STATUS_PARTIAL if accepted_count else FirstCollectionRun.STATUS_FAILED
            elif retryable and run.attempt < cls.MAX_ATTEMPTS:
                status = FirstCollectionRun.STATUS_RETRY_WAIT
                retry_after = 10 if run.attempt == 1 else 20
            elif accepted_count:
                status = FirstCollectionRun.STATUS_PARTIAL
            else:
                status = FirstCollectionRun.STATUS_FAILED

            run.status = status
            run.channel_results = channels
            run.failed_stage = str(result.get("failed_stage") or "one_shot")[:64] if failed_channels else ""
            run.error_type = next(
                (str(item.get("error_type"))[:128] for item in failed_channels if item.get("error_type")),
                "",
            )
            run.claim_token = ""
            run.lease_expires_at = None
            run.finished_at = (
                timezone.now()
                if status
                in {
                    FirstCollectionRun.STATUS_ACCEPTED,
                    FirstCollectionRun.STATUS_PARTIAL,
                    FirstCollectionRun.STATUS_FAILED,
                }
                else None
            )
            run.save(
                update_fields=[
                    "status",
                    "attempt",
                    "lock_retries",
                    "channel_results",
                    "failed_stage",
                    "error_type",
                    "claim_token",
                    "lease_expires_at",
                    "finished_at",
                    "updated_at",
                ]
            )
        if status == FirstCollectionRun.STATUS_RETRY_WAIT:
            log = logger.debug
        elif status in {FirstCollectionRun.STATUS_PARTIAL, FirstCollectionRun.STATUS_FAILED}:
            log = logger.warning
        else:
            log = logger.info
        log(
            "event=first_collection_attempt_finished run_id=%s task_id=%s attempt=%s result=%s failed_stage=%s error_type=%s",
            run.id,
            run.collect_task_id,
            run.attempt,
            status,
            run.failed_stage or "none",
            run.error_type or "none",
        )
        response = {"run_id": run.id, "status": status}
        if retry_after is not None:
            response["retry_after"] = retry_after
        return response

    @staticmethod
    def _bounded_channel_result(item) -> dict:
        status = str((item or {}).get("status") or "failed")
        if status not in {"accepted", "duplicate_active", "failed"}:
            status = "failed"
        result = {
            "status": status,
            "task_id": str((item or {}).get("task_id") or "")[:128],
            "retryable": bool((item or {}).get("retryable")),
        }
        error_type = str((item or {}).get("error_type") or "")[:128]
        if error_type:
            result["error_type"] = error_type
        return result
