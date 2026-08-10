"""主机监控 remote 提交适配：NATS adhoc + callback 上下文。"""

from __future__ import annotations

import time
from typing import Any, Mapping

import core.collection.host_remote.callback as callback_state
from core.collection.contracts import (
    CollectOutcome,
    CollectOutcomeStatus,
    TargetCollectionContext,
    build_collection_result_id,
)
from tasks.collectors.host_collector import HostCollector


async def submit_host_remote_collection(
    target: str,
    credential: Mapping[str, Any],
    context: TargetCollectionContext,
    *,
    params: dict[str, Any],
) -> CollectOutcome:
    submitted_at = int(time.time() * 1000)
    callback_params = {
        key: params[key]
        for key in (
            "host",
            "os_type",
            "monitor_type",
            "metrics_modules",
            "disk_include_fstypes",
            "disk_exclude_fstypes",
            "tags",
            "ansible_node_id",
            "collection_task_id",
            "collection_fence",
        )
        if key in params
    }
    callback_params["callback_timestamp"] = submitted_at
    callback_caller = str(params.get("ansible_node_id") or "")
    result_id = build_collection_result_id(
        task_id=context.task_id,
        plugin_ref=context.plugin_ref,
        target=target,
        fence=context.fence,
    )
    callback_task_id = "remote-" + result_id[:24]
    callback_params["collection_result_id"] = result_id
    callback_subject = callback_state.get_host_remote_callback_subject()
    callback_payload = {
        "task_id": callback_task_id,
        "collection_task_id": context.task_id,
        "collection_fence": context.fence,
        "collection_target": target,
        "collection_plugin_ref": context.plugin_ref,
        "collection_owner": context.owner_id,
        "collection_attempt": context.fence,
        "collection_caller": callback_caller,
    }
    await callback_state.store_host_remote_callback_context(
        callback_task_id,
        callback_params,
        {
            "owner_id": context.owner_id,
            "fence": context.fence,
            "plugin_ref": context.plugin_ref,
            "target": target,
            "collection_task_id": context.task_id,
            "attempt": context.fence,
            "caller": callback_caller,
        },
    )
    accepted = await HostCollector(params).submit_collection(
        callback_task_id,
        callback_subject,
        callback_payload,
    )
    accepted_result = accepted.get("result") or {}
    if accepted.get("success") is False or accepted_result.get("accepted") is False:
        await callback_state.clear_host_remote_callback_context(callback_task_id)
        return CollectOutcome(
            status=CollectOutcomeStatus.FAILED,
            error_code="remote_submission_failed",
        )
    await callback_state.mark_host_remote_submit_accepted(callback_task_id)
    return CollectOutcome(
        status=CollectOutcomeStatus.DEFERRED,
        value={
            "callback_task_id": callback_task_id,
            "submitted_at": submitted_at,
        },
    )
