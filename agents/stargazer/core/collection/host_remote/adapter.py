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
        attempt_id=context.attempt_id,
    )
    callback_params["collection_result_id"] = result_id
    callback_subject = callback_state.get_host_remote_callback_subject()
    v2_enabled = callback_state.is_host_remote_callback_v2_enabled()
    callback_task_id = ("remote-v2-" if v2_enabled else "remote-") + result_id[:24]
    if v2_enabled:
        _, trusted_identity = callback_state.issue_host_remote_callback_identity(
            fence=context.fence,
            target=target,
            collection_task_id=context.task_id,
            plugin_ref=context.plugin_ref,
            owner_id=context.owner_id,
            attempt=context.attempt_id,
            caller=callback_caller,
        )
    else:
        trusted_identity = {
            "fence": context.fence,
            "target": target,
            "collection_task_id": context.task_id,
            "plugin_ref": context.plugin_ref,
            "owner_id": context.owner_id,
            "attempt": context.attempt_id,
            "caller": callback_caller,
        }
    stored_context = await callback_state.store_host_remote_callback_context(
        callback_task_id,
        callback_params,
        trusted_identity,
    )
    persisted_identity = (stored_context or {}).get("ctx") or trusted_identity
    binding_fields = [
        "fence",
        "target",
        "collection_task_id",
        "plugin_ref",
        "owner_id",
        "attempt",
        "caller",
    ]
    if v2_enabled:
        binding_fields.insert(0, "protocol_version")
    if any(
        persisted_identity.get(key) != trusted_identity.get(key)
        for key in binding_fields
    ):
        raise RuntimeError("Host Remote stored identity conflict")
    callback_payload = {}
    if v2_enabled:
        callback_payload["context"] = (
            callback_state.restore_host_remote_callback_identity(persisted_identity)
        )
    accepted = await HostCollector(params).submit_collection(
        callback_task_id,
        callback_subject,
        callback_payload,
    )
    accepted_result = accepted.get("result") or {}
    if accepted.get("success") is False or accepted_result.get("accepted") is False:
        callback_state.log_host_remote_event(
            "submit_rejected_context_retained",
            callback_task_id,
            level="warning",
            execution="waiting_callback",
            failed_stage="executor_submit",
            error_type="executor_rejected",
        )
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
