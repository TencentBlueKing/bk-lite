import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils.timezone import now

from apps.cmdb.models.operation import (
    CmdbOperation,
    CmdbOperationOutbox,
    CmdbOperationOutboxStatus,
    CmdbOperationStatus,
)


class OperationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class OperationStart:
    operation: CmdbOperation
    reused: bool


class OperationService:
    GRAPH_WRITE_LEASE_SECONDS = 900
    OUTBOX_MAX_ATTEMPTS = 5

    @staticmethod
    def _request_hash(action: str, target: dict, request_payload: dict) -> str:
        raw = json.dumps(
            {"action": action, "target": target, "request": request_payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return f"{exc.__class__.__name__}: CMDB 图操作失败"

    @classmethod
    def start(
        cls,
        *,
        operator: str,
        idempotency_key: str,
        action: str,
        target: dict,
        request_payload: dict,
    ) -> OperationStart:
        request_hash = cls._request_hash(action, target, request_payload)
        try:
            with transaction.atomic():
                operation, created = CmdbOperation.objects.get_or_create(
                    operator=operator,
                    idempotency_key=idempotency_key,
                    defaults={
                        "request_hash": request_hash,
                        "action": action,
                        "target": target,
                        "request_snapshot": request_payload,
                    },
                )
        except IntegrityError:
            operation = CmdbOperation.objects.get(operator=operator, idempotency_key=idempotency_key)
            created = False
        if operation.request_hash != request_hash:
            raise OperationConflict("Idempotency-Key 已用于不同请求")
        return OperationStart(operation=operation, reused=not created)

    @classmethod
    def claim_graph_write(cls, operation_id, *, owner_token: str) -> bool:
        current_time = now()
        return bool(
            CmdbOperation.objects.filter(
                operation_id=operation_id,
                status=CmdbOperationStatus.PENDING,
            ).update(
                status=CmdbOperationStatus.GRAPH_WRITING,
                owner_token=owner_token,
                lease_expires_at=current_time + timedelta(seconds=cls.GRAPH_WRITE_LEASE_SECONDS),
                updated_at=current_time,
            )
        )

    @classmethod
    def _commit_graph_result(
        cls,
        operation: CmdbOperation,
        result: dict,
        events: list[tuple[str, dict]],
        *,
        owner_token: str | None = None,
    ) -> dict:
        current_time = now()
        with transaction.atomic():
            filters = dict(
                id=operation.id,
                status__in=[CmdbOperationStatus.PENDING, CmdbOperationStatus.GRAPH_WRITING],
            )
            if owner_token is not None:
                filters.update(status=CmdbOperationStatus.GRAPH_WRITING, owner_token=owner_token)
                filters.pop("status__in", None)
            updated = CmdbOperation.objects.filter(**filters).update(
                status=CmdbOperationStatus.GRAPH_COMMITTED,
                result_snapshot=result,
                target={**operation.target, "instance_id": result.get("_id")},
                last_error="",
                owner_token="",
                lease_expires_at=None,
                updated_at=current_time,
            )
            if updated:
                CmdbOperationOutbox.objects.bulk_create(
                    [
                        CmdbOperationOutbox(operation_id=operation.id, event_type=event_type, payload=payload)
                        for event_type, payload in events
                    ],
                    ignore_conflicts=True,
                )
        operation.refresh_from_db()
        return operation.result_snapshot

    @classmethod
    def execute_graph(
        cls,
        operation: CmdbOperation,
        *,
        graph_write,
        events: list[tuple[str, dict]],
    ) -> dict:
        operation.refresh_from_db()
        if operation.status in (CmdbOperationStatus.GRAPH_COMMITTED, CmdbOperationStatus.COMPLETED):
            return operation.result_snapshot
        if operation.status == CmdbOperationStatus.ERROR:
            raise OperationConflict("该幂等请求已失败，不会盲目重放图写")
        owner_token = uuid.uuid4().hex
        if not cls.claim_graph_write(operation.operation_id, owner_token=owner_token):
            operation.refresh_from_db()
            if operation.status in (CmdbOperationStatus.GRAPH_COMMITTED, CmdbOperationStatus.COMPLETED):
                return operation.result_snapshot
            raise OperationConflict("该幂等请求正在执行")
        try:
            result = graph_write(str(operation.operation_id))
        except Exception as exc:
            CmdbOperation.objects.filter(
                id=operation.id,
                status=CmdbOperationStatus.GRAPH_WRITING,
                owner_token=owner_token,
            ).update(
                status=CmdbOperationStatus.ERROR,
                last_error=cls._safe_error(exc),
                owner_token="",
                lease_expires_at=None,
                updated_at=now(),
            )
            raise
        return cls._commit_graph_result(operation, result, events, owner_token=owner_token)

    @classmethod
    def recover_pending(
        cls,
        operation: CmdbOperation,
        *,
        fact_finder,
        events: list[tuple[str, dict]],
    ) -> dict | None:
        operation.refresh_from_db()
        if operation.status not in (CmdbOperationStatus.PENDING, CmdbOperationStatus.GRAPH_WRITING):
            return operation.result_snapshot or None
        result = fact_finder(str(operation.operation_id))
        if not result:
            return None
        return cls._commit_graph_result(operation, result, events)

    @classmethod
    def claim_outbox(cls, event_id, *, owner_token: str, lease_seconds: int = 300) -> bool:
        current_time = now()
        event = CmdbOperationOutbox.objects.filter(event_id=event_id).first()
        if not event:
            return False
        filters = {"id": event.id}
        if event.status == CmdbOperationOutboxStatus.PENDING:
            filters["status"] = CmdbOperationOutboxStatus.PENDING
        elif event.status == CmdbOperationOutboxStatus.RETRY and event.next_attempt_at <= current_time:
            filters.update(status=CmdbOperationOutboxStatus.RETRY, next_attempt_at=event.next_attempt_at)
        elif (
            event.status == CmdbOperationOutboxStatus.SENDING
            and event.lease_expires_at is not None
            and event.lease_expires_at <= current_time
        ):
            filters.update(
                status=CmdbOperationOutboxStatus.SENDING,
                owner_token=event.owner_token,
                lease_expires_at=event.lease_expires_at,
            )
        else:
            return False
        return bool(
            CmdbOperationOutbox.objects.filter(**filters).update(
                status=CmdbOperationOutboxStatus.SENDING,
                owner_token=owner_token,
                lease_expires_at=current_time + timedelta(seconds=max(1, lease_seconds)),
                attempt_count=F("attempt_count") + 1,
                updated_at=current_time,
            )
        )

    @staticmethod
    def finish_outbox_success(event_id, *, owner_token: str) -> bool:
        current_time = now()
        with transaction.atomic():
            event = CmdbOperationOutbox.objects.filter(event_id=event_id).first()
            if not event:
                return False
            updated = CmdbOperationOutbox.objects.filter(
                id=event.id,
                status=CmdbOperationOutboxStatus.SENDING,
                owner_token=owner_token,
            ).update(
                status=CmdbOperationOutboxStatus.SUCCESS,
                owner_token="",
                lease_expires_at=None,
                last_error="",
                updated_at=current_time,
            )
            if not updated:
                return False
            unfinished = CmdbOperationOutbox.objects.filter(operation_id=event.operation_id).exclude(
                status=CmdbOperationOutboxStatus.SUCCESS
            ).exists()
            if not unfinished:
                CmdbOperation.objects.filter(
                    id=event.operation_id,
                    status=CmdbOperationStatus.GRAPH_COMMITTED,
                ).update(status=CmdbOperationStatus.COMPLETED, updated_at=current_time)
        return True

    @classmethod
    def _dispatch_outbox(cls, event: CmdbOperationOutbox) -> None:
        operation = event.operation
        result = operation.result_snapshot
        if event.event_type == "change_record":
            from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
            from apps.cmdb.models.change_record import CREATE_INST, ORDINARY_ATTRIBUTE_CHANGE, UPDATE_INST
            from apps.cmdb.utils.change_record import create_change_record

            is_create = operation.action == "instance.create"
            scenario = event.payload.get("scenario") or ORDINARY_ATTRIBUTE_CHANGE
            create_change_record(
                inst_id=result["_id"],
                model_id=result["model_id"],
                label=INSTANCE,
                _type=CREATE_INST if is_create else UPDATE_INST,
                before_data=event.payload.get("before_data"),
                after_data=result,
                operator=operation.operator,
                model_object=OPERATOR_INSTANCE,
                message=f"{'创建' if is_create else '修改'}模型实例. 模型:{result['model_id']} 实例:{result.get('inst_name', '')}",
                scenario=scenario,
                operation_event_id=event.event_id,
            )
            return
        if event.event_type == "auto_relation":
            from apps.cmdb.tasks.celery_tasks import reconcile_instance_auto_association_task

            reconcile_instance_auto_association_task.delay(result["_id"])
            return
        raise ValueError(f"未知 CMDB operation outbox 事件: {event.event_type}")

    @classmethod
    def _finish_outbox_failure(cls, event_id, *, owner_token: str, exc: Exception) -> bool:
        current_time = now()
        event = CmdbOperationOutbox.objects.filter(event_id=event_id).first()
        if not event:
            return False
        terminal = event.attempt_count >= cls.OUTBOX_MAX_ATTEMPTS
        delay_seconds = min(60 * (2 ** max(0, event.attempt_count - 1)), 3600)
        return bool(
            CmdbOperationOutbox.objects.filter(
                id=event.id,
                status=CmdbOperationOutboxStatus.SENDING,
                owner_token=owner_token,
            ).update(
                status=CmdbOperationOutboxStatus.FAILED if terminal else CmdbOperationOutboxStatus.RETRY,
                owner_token="",
                lease_expires_at=None,
                next_attempt_at=current_time + timedelta(seconds=delay_seconds),
                last_error=cls._safe_error(exc),
                updated_at=current_time,
            )
        )

    @classmethod
    def consume_outbox(cls, event_id, *, owner_token: str | None = None) -> bool:
        token = owner_token or uuid.uuid4().hex
        if not cls.claim_outbox(event_id, owner_token=token):
            event = CmdbOperationOutbox.objects.filter(event_id=event_id).first()
            return bool(event and event.status == CmdbOperationOutboxStatus.SUCCESS)
        event = CmdbOperationOutbox.objects.select_related("operation").get(event_id=event_id)
        try:
            cls._dispatch_outbox(event)
        except Exception as exc:
            cls._finish_outbox_failure(event_id, owner_token=token, exc=exc)
            return False
        return cls.finish_outbox_success(event_id, owner_token=token)

    @staticmethod
    def _events_for_operation(operation: CmdbOperation) -> list[tuple[str, dict]]:
        payload = {}
        if operation.action == "instance.update":
            payload["scenario"] = operation.request_snapshot.get("scenario")
        return [("change_record", payload), ("auto_relation", {})]

    @staticmethod
    def _find_graph_fact(operation: CmdbOperation) -> dict | None:
        from apps.cmdb.constants.constants import INSTANCE
        from apps.cmdb.graph.drivers.graph_client import GraphClient

        with GraphClient() as graph:
            rows, _ = graph.query_entity(
                INSTANCE,
                [
                    {
                        "field": "_cmdb_operation_id",
                        "type": "str=",
                        "value": str(operation.operation_id),
                    }
                ],
                page={"skip": 0, "limit": 1},
                include_count=False,
            )
        if not rows:
            return None
        result = dict(rows[0])
        result.pop("_cmdb_operation_id", None)
        return result

    @classmethod
    def recover_stale_graph_writes(cls, *, batch_size: int = 100, lease_seconds: int = 900) -> dict:
        current_time = now()
        cutoff = current_time - timedelta(seconds=max(1, lease_seconds))
        limit = max(1, min(int(batch_size), 1000))
        operations = list(
            CmdbOperation.objects.filter(
                Q(status=CmdbOperationStatus.PENDING, updated_at__lt=cutoff)
                | Q(
                    status=CmdbOperationStatus.GRAPH_WRITING,
                    lease_expires_at__lte=current_time,
                )
            )
            .order_by("updated_at", "id")[:limit]
        )
        stats = {"scanned": len(operations), "recovered": 0, "unresolved": 0}
        for operation in operations:
            fact = cls._find_graph_fact(operation)
            if not fact:
                stats["unresolved"] += 1
                continue
            cls.recover_pending(
                operation,
                fact_finder=lambda operation_id, result=fact: result,
                events=cls._events_for_operation(operation),
            )
            stats["recovered"] += 1
        return stats

    @classmethod
    def process_outbox_batch(cls, *, batch_size: int = 100) -> dict:
        current_time = now()
        limit = max(1, min(int(batch_size), 1000))
        event_ids = list(
            CmdbOperationOutbox.objects.filter(
                Q(status=CmdbOperationOutboxStatus.PENDING, next_attempt_at__lte=current_time)
                | Q(status=CmdbOperationOutboxStatus.RETRY, next_attempt_at__lte=current_time)
                | Q(status=CmdbOperationOutboxStatus.SENDING, lease_expires_at__lte=current_time)
            )
            .order_by("next_attempt_at", "id")
            .values_list("event_id", flat=True)[:limit]
        )
        stats = {"scanned": len(event_ids), "succeeded": 0, "failed": 0}
        for event_id in event_ids:
            succeeded = cls.consume_outbox(event_id)
            stats["succeeded" if succeeded else "failed"] += 1
        return stats
