import hashlib
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.mlops.models.external_resource_cleanup import ExternalResourceCleanupIntent
from apps.mlops.utils import mlflow_service

CLAIM_LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 10


def _cleanup_key(resource_type: str, payload: dict) -> str:
    canonical_target = "\x00".join([resource_type, payload["experiment_name"], payload["model_name"]])
    return hashlib.sha256(canonical_target.encode("utf-8")).hexdigest()


def create_mlflow_cleanup_intent(
    experiment_name: str,
    model_name: str,
    *,
    using: str = "default",
) -> ExternalResourceCleanupIntent:
    if not experiment_name or not model_name:
        raise ValueError("MLflow cleanup target must be non-empty")
    payload = {"experiment_name": experiment_name, "model_name": model_name}
    resource_type = ExternalResourceCleanupIntent.ResourceType.MLFLOW_EXPERIMENT_MODEL
    intent, _ = ExternalResourceCleanupIntent.objects.using(using).get_or_create(
        idempotency_key=_cleanup_key(resource_type, payload),
        defaults={"resource_type": resource_type, "payload": payload},
    )
    if intent.resource_type != resource_type or intent.payload != payload:
        raise ValueError("cleanup idempotency key is bound to another target")
    return intent


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


def _mlflow_target(intent: ExternalResourceCleanupIntent) -> tuple[str, str]:
    if intent.resource_type != ExternalResourceCleanupIntent.ResourceType.MLFLOW_EXPERIMENT_MODEL:
        raise ValueError("unsupported external cleanup resource type")
    experiment_name = intent.payload.get("experiment_name")
    model_name = intent.payload.get("model_name")
    if not isinstance(experiment_name, str) or not experiment_name:
        raise ValueError("invalid MLflow experiment cleanup target")
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("invalid MLflow model cleanup target")
    return experiment_name, model_name


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
        experiment_name, model_name = _mlflow_target(intent)
        mlflow_service.delete_experiment_and_model(
            experiment_name=experiment_name,
            model_name=model_name,
        )
    except Exception as error:
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
                    ExternalResourceCleanupIntent.Status.FAILED if current.attempts >= MAX_ATTEMPTS else ExternalResourceCleanupIntent.Status.PENDING
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
