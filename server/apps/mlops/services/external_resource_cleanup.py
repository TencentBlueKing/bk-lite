import hashlib
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django_minio_backend import MinioBackend

from apps.mlops.models.external_resource_cleanup import ExternalResourceCleanupIntent
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.webhook_client import WebhookClient

CLAIM_LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 10
ABSENT_RESOURCE_CODES = {"RESOURCE_DOES_NOT_EXIST", "NoSuchKey", "NoSuchObject", "NoSuchBucket"}


def _cleanup_key(resource_type: str, *targets: str) -> str:
    canonical_target = "\x00".join([resource_type, *targets])
    return hashlib.sha256(canonical_target.encode("utf-8")).hexdigest()


def _create_cleanup_intent(
    resource_type: str,
    payload: dict,
    *targets: str,
    using: str = "default",
) -> ExternalResourceCleanupIntent:
    if any(not target for target in targets):
        raise ValueError("cleanup target must be non-empty")
    intent, _ = ExternalResourceCleanupIntent.objects.using(using).get_or_create(
        idempotency_key=_cleanup_key(resource_type, *targets),
        defaults={"resource_type": resource_type, "payload": payload},
    )
    if intent.resource_type != resource_type or intent.payload != payload:
        raise ValueError("cleanup idempotency key is bound to another target")
    return intent


def create_mlflow_cleanup_intent(
    experiment_name: str,
    model_name: str,
    *,
    using: str = "default",
) -> ExternalResourceCleanupIntent:
    if not experiment_name or not model_name:
        raise ValueError("MLflow cleanup target must be non-empty")
    return _create_cleanup_intent(
        ExternalResourceCleanupIntent.ResourceType.MLFLOW_EXPERIMENT_MODEL,
        {"experiment_name": experiment_name, "model_name": model_name},
        experiment_name,
        model_name,
        using=using,
    )


def create_minio_cleanup_intent(
    bucket: str,
    path: str,
    *,
    using: str = "default",
) -> ExternalResourceCleanupIntent:
    if not bucket or not path:
        raise ValueError("MinIO cleanup target must be non-empty")
    return _create_cleanup_intent(
        ExternalResourceCleanupIntent.ResourceType.MINIO_OBJECT,
        {"bucket": bucket, "path": path},
        bucket,
        path,
        using=using,
    )


def create_container_cleanup_intent(
    container_id: str,
    *,
    using: str = "default",
) -> ExternalResourceCleanupIntent:
    if not container_id:
        raise ValueError("container cleanup target must be non-empty")
    return _create_cleanup_intent(
        ExternalResourceCleanupIntent.ResourceType.WEBHOOK_CONTAINER,
        {"container_id": container_id},
        container_id,
        using=using,
    )


def _due_filter(now):
    pending_due = Q(status=ExternalResourceCleanupIntent.Status.PENDING) & (Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
    abandoned_claim = Q(
        status=ExternalResourceCleanupIntent.Status.PROCESSING,
        claim_expires_at__lte=now,
    )
    return pending_due | abandoned_claim


def _assign_claim(intent: ExternalResourceCleanupIntent, now) -> str:
    claim_token = uuid.uuid4().hex
    intent.status = ExternalResourceCleanupIntent.Status.PROCESSING
    intent.claim_token = claim_token
    intent.claim_expires_at = now + CLAIM_LEASE
    intent.next_retry_at = None
    intent.save(
        update_fields=[
            "status",
            "claim_token",
            "claim_expires_at",
            "next_retry_at",
            "updated_at",
        ]
    )
    return claim_token


def claim_cleanup_intent(intent_id: int, *, using: str = "default") -> str | None:
    now = timezone.now()
    with transaction.atomic(using=using):
        intent = ExternalResourceCleanupIntent.objects.using(using).select_for_update().filter(pk=intent_id).filter(_due_filter(now)).first()
        if intent is None:
            return None
        return _assign_claim(intent, now)


def claim_due_cleanup_intents(
    limit: int = 100,
    *,
    using: str = "default",
) -> list[tuple[int, str]]:
    if limit < 1 or limit > 100:
        raise ValueError("cleanup claim limit must be between 1 and 100")
    now = timezone.now()
    with transaction.atomic(using=using):
        intents = list(ExternalResourceCleanupIntent.objects.using(using).select_for_update().filter(_due_filter(now)).order_by("pk")[:limit])
        return [(intent.pk, _assign_claim(intent, now)) for intent in intents]


def release_cleanup_claim(
    intent_id: int,
    claim_token: str,
    *,
    using: str = "default",
) -> bool:
    updated = (
        ExternalResourceCleanupIntent.objects.using(using)
        .filter(
            pk=intent_id,
            status=ExternalResourceCleanupIntent.Status.PROCESSING,
            claim_token=claim_token,
        )
        .update(
            status=ExternalResourceCleanupIntent.Status.PENDING,
            claim_token="",
            claim_expires_at=None,
            next_retry_at=timezone.now(),
        )
    )
    return updated == 1


def _required_payload_str(intent: ExternalResourceCleanupIntent, field: str) -> str:
    value = intent.payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {intent.resource_type} cleanup target")
    return value


def _mlflow_target(intent: ExternalResourceCleanupIntent) -> tuple[str, str]:
    if intent.resource_type != ExternalResourceCleanupIntent.ResourceType.MLFLOW_EXPERIMENT_MODEL:
        raise ValueError("unsupported external cleanup resource type")
    return _required_payload_str(intent, "experiment_name"), _required_payload_str(intent, "model_name")


def _is_absent_resource(error: Exception) -> bool:
    code = getattr(error, "code", None)
    if code in ABSENT_RESOURCE_CODES:
        return True
    message = str(error).lower()
    return "not found" in message or "does not exist" in message or "nosuchkey" in message


def _execute_cleanup(intent: ExternalResourceCleanupIntent) -> None:
    resource_type = intent.resource_type
    if resource_type == ExternalResourceCleanupIntent.ResourceType.MLFLOW_EXPERIMENT_MODEL:
        experiment_name, model_name = _mlflow_target(intent)
        mlflow_service.delete_experiment_and_model(
            experiment_name=experiment_name,
            model_name=model_name,
        )
        return
    if resource_type == ExternalResourceCleanupIntent.ResourceType.MINIO_OBJECT:
        bucket = _required_payload_str(intent, "bucket")
        path = _required_payload_str(intent, "path")
        MinioBackend(bucket_name=bucket).delete(path)
        return
    if resource_type == ExternalResourceCleanupIntent.ResourceType.WEBHOOK_CONTAINER:
        WebhookClient.remove(_required_payload_str(intent, "container_id"))
        return
    raise ValueError("unsupported external cleanup resource type")


def process_cleanup_intent(
    intent_id: int,
    claim_token: str,
    *,
    using: str = "default",
) -> dict:
    now = timezone.now()
    intent = (
        ExternalResourceCleanupIntent.objects.using(using)
        .filter(
            pk=intent_id,
            status=ExternalResourceCleanupIntent.Status.PROCESSING,
            claim_token=claim_token,
            claim_expires_at__gt=now,
        )
        .first()
    )
    if intent is None:
        return {"result": False, "reason": "stale cleanup claim"}

    try:
        _execute_cleanup(intent)
    except Exception as error:
        if not _is_absent_resource(error):
            with transaction.atomic(using=using):
                current = (
                    ExternalResourceCleanupIntent.objects.using(using)
                    .select_for_update()
                    .filter(
                        pk=intent_id,
                        status=ExternalResourceCleanupIntent.Status.PROCESSING,
                        claim_token=claim_token,
                        claim_expires_at__gt=timezone.now(),
                    )
                    .first()
                )
                if current is not None:
                    current.attempts += 1
                    current.status = (
                        ExternalResourceCleanupIntent.Status.FAILED
                        if current.attempts >= MAX_ATTEMPTS
                        else ExternalResourceCleanupIntent.Status.PENDING
                    )
                    current.next_retry_at = (
                        None
                        if current.status == ExternalResourceCleanupIntent.Status.FAILED
                        else timezone.now() + timedelta(seconds=min(3600, 30 * (2 ** min(current.attempts - 1, 7))))
                    )
                    current.claim_token = ""
                    current.claim_expires_at = None
                    current.last_error = type(error).__name__
                    current.save(
                        update_fields=[
                            "attempts",
                            "status",
                            "next_retry_at",
                            "claim_token",
                            "claim_expires_at",
                            "last_error",
                            "updated_at",
                        ]
                    )
            raise

    updated = (
        ExternalResourceCleanupIntent.objects.using(using)
        .filter(
            pk=intent_id,
            status=ExternalResourceCleanupIntent.Status.PROCESSING,
            claim_token=claim_token,
            claim_expires_at__gt=timezone.now(),
        )
        .update(
            status=ExternalResourceCleanupIntent.Status.COMPLETED,
            completed_at=timezone.now(),
            next_retry_at=None,
            claim_token="",
            claim_expires_at=None,
            last_error="",
        )
    )
    if updated != 1:
        return {"result": False, "reason": "stale cleanup claim"}
    return {"result": True, "state": "completed"}
