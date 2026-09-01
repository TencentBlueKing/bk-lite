"""轮次完成标记：全部数据批次 NATS 发布成功后追加一条稳定标签指标。"""

from __future__ import annotations

import time
from typing import Any, Mapping

from core.collection.runtime import CollectionRequest
from core.logger import logger

ROUND_COMPLETE_METRIC = "cmdb_round_complete"
ROUND_COMPLETE_GAUGE = f"{ROUND_COMPLETE_METRIC}_gauge"
ROUND_COMPLETE_EXTRA_LABELS = frozenset(
    {
        "collection_role",
        "channel_config_version",
        "collect_task_id",
    }
)


def new_round_ts() -> int:
    return int(time.time())


def build_round_complete_labels(params: Mapping[str, Any]) -> dict[str, Any]:
    """从请求构造完成标记的稳定通道标签。"""
    labels = {
        "collection_role": params.get("collection_role") or "device",
        "channel_config_version": params.get("channel_config_version"),
        "collect_task_id": params.get("collect_task_id"),
    }
    return {key: value for key, value in labels.items() if value not in (None, "")}


def resolve_round_marker_identity(params: Mapping[str, Any]) -> tuple[str, str] | None:
    """返回 (instance_id, model_id)；非 CMDB VictoriaMetrics 对账任务返回 None。"""
    tags = params.get("tags") if isinstance(params.get("tags"), Mapping) else {}
    instance_id = str(tags.get("instance_id") or "").strip()
    if not instance_id:
        collect_task_id = params.get("collect_task_id")
        if collect_task_id not in (None, ""):
            instance_id = f"cmdb_{collect_task_id}"
    if not instance_id.startswith("cmdb_"):
        return None
    if str(params.get("callback_subject") or "").strip():
        # NATS 直推结果链路（如 config_file）不走 VictoriaMetrics 对账。
        return None
    model_id = str(params.get("model_id") or tags.get("config_type") or params.get("plugin_name") or "unknown").strip()
    return instance_id, model_id


def build_round_complete_prometheus(
    *,
    round_ts: int,
    instance_id: str,
    model_id: str,
    extra_labels: Mapping[str, Any] | None = None,
) -> str:
    labels = {
        "instance_id": instance_id,
        "model_id": model_id,
    }
    if extra_labels:
        for key, value in extra_labels.items():
            if key not in ROUND_COMPLETE_EXTRA_LABELS or value in (None, ""):
                continue
            labels[str(key)] = str(value)
    label_str = ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels.items())
    return f"# TYPE {ROUND_COMPLETE_METRIC} gauge\n" f"{ROUND_COMPLETE_METRIC}{{{label_str}}} {int(round_ts)}\n"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


async def publish_round_complete_marker(
    request: CollectionRequest,
    round_ts: int,
    *,
    metrics_publish=None,
    extra_labels: Mapping[str, Any] | None = None,
) -> bool:
    """发布成功返回 True；不适用或发布失败返回 False（失败不抛，由调用方记日志）。"""
    identity = resolve_round_marker_identity(request.params)
    if identity is None:
        return False
    instance_id, model_id = identity
    marker_labels = build_round_complete_labels(request.params)
    if extra_labels:
        marker_labels.update(extra_labels)
    payload = build_round_complete_prometheus(
        round_ts=round_ts,
        instance_id=instance_id,
        model_id=model_id,
        extra_labels=marker_labels,
    )
    params = dict(request.params)
    params.setdefault("tags", {})
    if isinstance(params["tags"], Mapping):
        params["tags"] = dict(params["tags"])
    else:
        params["tags"] = {}
    params["tags"]["instance_id"] = instance_id
    params["tags"].update(marker_labels)
    params["model_id"] = model_id
    # 标记走与任务相同的 metrics subject，便于 VM 按 instance_id 查询。
    if metrics_publish is None:
        from tasks.utils.nats_helper import publish_metrics_to_nats

        metrics_publish = publish_metrics_to_nats
    try:
        await metrics_publish({}, payload, params, request.task_id)
    except Exception as error:  # noqa: BLE001 - 标记失败不得改写已发布数据结果
        logger.warning(
            "event=round_complete_marker_failed task_id=%s instance_id=%s " "model_id=%s round_ts=%s error_type=%s",
            request.task_id,
            instance_id,
            model_id,
            round_ts,
            type(error).__name__,
        )
        return False
    logger.info(
        "event=round_complete_marker_published task_id=%s instance_id=%s " "model_id=%s round_ts=%s",
        request.task_id,
        instance_id,
        model_id,
        round_ts,
    )
    return True
