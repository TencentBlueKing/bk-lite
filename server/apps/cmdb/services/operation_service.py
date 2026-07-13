import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils.timezone import now

from apps.cmdb.models.operation import CmdbOperation, CmdbOperationOutbox, CmdbOperationStatus


class OperationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class OperationStart:
    operation: CmdbOperation
    reused: bool


class OperationService:
    GRAPH_WRITE_LEASE_SECONDS = 900

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
