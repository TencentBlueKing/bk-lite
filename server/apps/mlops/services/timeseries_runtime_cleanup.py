from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing
from apps.mlops.utils.webhook_client import WebhookClient


def reconcile_orphan_timeseries_runtime(container_id: str, serving_id: int) -> dict:
    """幂等删除回滚 create 遗留的 runtime，并确认目标资源已经不存在。"""
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
