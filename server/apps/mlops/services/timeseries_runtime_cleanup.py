from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictServing,
    TimeSeriesRuntimeCleanupIntent,
    TimeSeriesRuntimeGuard,
)
from apps.mlops.utils.webhook_client import WebhookClient


def _expected_container_id(serving_id: int) -> str:
    return f"TimeseriesPredict_Serving_{serving_id}"


def lock_timeseries_runtime_id(serving_id: int) -> None:
    """锁定永久 guard；唯一键也覆盖 guard 尚未提交的并发 create。"""
    TimeSeriesRuntimeGuard.objects.get_or_create(serving_id=serving_id)
    TimeSeriesRuntimeGuard.objects.select_for_update().get(serving_id=serving_id)


def create_runtime_cleanup_intent(
    container_id: str,
    serving_id: int,
    cleanup_token: str,
) -> TimeSeriesRuntimeCleanupIntent:
    if container_id != _expected_container_id(serving_id):
        raise ValueError("container_id does not belong to serving_id")
    intent, _ = TimeSeriesRuntimeCleanupIntent.objects.get_or_create(
        cleanup_token=cleanup_token,
        defaults={
            "container_id": container_id,
            "serving_id": serving_id,
        },
    )
    if intent.container_id != container_id or intent.serving_id != serving_id:
        raise ValueError("cleanup_token is already bound to another runtime")
    return intent


def reconcile_orphan_timeseries_runtime(container_id: str, serving_id: int) -> dict:
    """串行化 create/cleanup，幂等删除 orphan 并确认目标资源已经不存在。"""
    if container_id != _expected_container_id(serving_id):
        raise ValueError("container_id does not belong to serving_id")

    # 外部 remove/status 必须位于 guard 锁域内；新 create 在调用 serve 前也会
    # 获取同一永久锁行，因此不存在业务行时仍不会发生检查后误删新 runtime。
    with transaction.atomic():
        lock_timeseries_runtime_id(serving_id)
        if TimeSeriesPredictServing.objects.filter(pk=serving_id).exists():
            return {
                "result": False,
                "reason": "serving id is owned by a database record",
                "container_id": container_id,
            }

        remove_error = None
        try:
            WebhookClient.remove(container_id)
        except Exception as error:
            # remove 响应丢失时副作用可能已成功，仍需继续查询实际状态。
            remove_error = error

        try:
            runtime_statuses = WebhookClient.get_status([container_id])
        except Exception as status_error:
            raise RuntimeError(
                f"orphan runtime cleanup is unconfirmed: "
                f"remove={type(remove_error).__name__ if remove_error else 'accepted'}, "
                f"status={type(status_error).__name__}"
            ) from status_error

        matching_status = next(
            (
                item
                for item in runtime_statuses
                if isinstance(item, dict)
                and item.get("id") == container_id
                and item.get("state")
            ),
            None,
        )
        if matching_status and matching_status["state"] == "not_found":
            return {
                "result": True,
                "state": "not_found",
                "container_id": container_id,
            }

        observed_state = matching_status.get("state") if matching_status else "unknown"
        raise RuntimeError(
            f"orphan runtime cleanup is unconfirmed: state={observed_state}, "
            f"remove={type(remove_error).__name__ if remove_error else 'accepted'}"
        )


def process_runtime_cleanup_intent(intent_id: int) -> dict:
    intent = TimeSeriesRuntimeCleanupIntent.objects.filter(pk=intent_id).first()
    if intent is None:
        return {"result": False, "reason": "cleanup intent does not exist"}
    if intent.status != TimeSeriesRuntimeCleanupIntent.Status.PENDING:
        return {"result": False, "reason": f"cleanup intent is {intent.status}"}

    try:
        result = reconcile_orphan_timeseries_runtime(
            intent.container_id,
            intent.serving_id,
        )
    except Exception as error:
        with transaction.atomic():
            current = TimeSeriesRuntimeCleanupIntent.objects.select_for_update().get(pk=intent_id)
            if current.status == TimeSeriesRuntimeCleanupIntent.Status.PENDING:
                current.attempts += 1
                current.next_retry_at = timezone.now() + timedelta(
                    seconds=min(3600, 30 * (2 ** min(current.attempts - 1, 7)))
                )
                current.last_error = f"{type(error).__name__}: {error}"[:2000]
                current.save(
                    update_fields=[
                        "attempts",
                        "next_retry_at",
                        "last_error",
                        "updated_at",
                    ]
                )
        raise

    terminal_status = (
        TimeSeriesRuntimeCleanupIntent.Status.COMPLETED
        if result["result"]
        else TimeSeriesRuntimeCleanupIntent.Status.OWNED
    )
    TimeSeriesRuntimeCleanupIntent.objects.filter(
        pk=intent_id,
        status=TimeSeriesRuntimeCleanupIntent.Status.PENDING,
    ).update(
        status=terminal_status,
        completed_at=timezone.now(),
        next_retry_at=None,
        last_error="",
    )
    return result


def claim_pending_runtime_cleanup_intents(limit: int = 200) -> list[int]:
    """为 Beat 认领到期意图；投递丢失时五分钟后会再次可见。"""
    now = timezone.now()
    with transaction.atomic():
        intents = list(
            TimeSeriesRuntimeCleanupIntent.objects.select_for_update()
            .filter(
                Q(status=TimeSeriesRuntimeCleanupIntent.Status.PENDING),
                Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now),
            )
            .order_by("pk")[:limit]
        )
        retry_at = now + timedelta(minutes=5)
        TimeSeriesRuntimeCleanupIntent.objects.filter(
            pk__in=[intent.pk for intent in intents]
        ).update(next_retry_at=retry_at)
    return [intent.pk for intent in intents]


def release_runtime_cleanup_intent(intent_id: int) -> None:
    TimeSeriesRuntimeCleanupIntent.objects.filter(
        pk=intent_id,
        status=TimeSeriesRuntimeCleanupIntent.Status.PENDING,
    ).update(next_retry_at=timezone.now())
