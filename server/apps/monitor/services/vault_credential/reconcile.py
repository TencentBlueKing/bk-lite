"""Enqueue vault credential refresh and periodic reconciliation."""

from __future__ import annotations

from collections import defaultdict

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig
from apps.rpc.system_mgmt import SystemMgmt

from .apply import apply_vault_credential

_RECONCILE_LIMIT = 500
_FAILED_QUOTA = 250
_VERSION_BATCH = 100


def refresh_credential_refs(credential_ids):
    ids = [str(item) for item in (credential_ids or []) if item]
    groups = _groups_for_credentials(ids)
    counts = _apply_groups(groups, trigger="refresh", skip_locked=False)
    logger.info(
        "event=vault_credential_refresh_finished id_count=%s processed=%s success=%s failed=%s skipped=%s",
        len(ids),
        counts["processed"],
        counts["success"],
        counts["failed"],
        counts["skipped"],
    )
    return counts


def reconcile_vault_credentials():
    groups = _stale_groups()
    selected = _select_quota(groups)
    counts = _apply_groups(selected, trigger="reconcile", skip_locked=True)
    logger.info(
        "event=vault_credential_reconcile_finished processed=%s success=%s failed=%s skipped=%s",
        counts["processed"],
        counts["success"],
        counts["failed"],
        counts["skipped"],
    )
    return counts


def _groups_for_credentials(credential_ids):
    if not credential_ids:
        return []
    rows = CollectConfig.objects.filter(vault_credential_id__in=credential_ids).order_by("id")
    grouped = {}
    for row in rows:
        key = (row.vault_credential_id, row.monitor_instance_id, row.monitor_plugin_id)
        grouped.setdefault(key, row)
    return [
        {
            "credential_id": key[0],
            "instance_id": key[1],
            "monitor_plugin_id": key[2],
        }
        for key in grouped
    ]


def _stale_groups():
    rows = list(
        CollectConfig.objects.exclude(vault_credential_id="").values(
            "monitor_instance_id",
            "monitor_plugin_id",
            "vault_credential_id",
            "vault_applied_version",
            "vault_sync_error",
            "vault_synced_at",
        )
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["vault_credential_id"], row["monitor_instance_id"], row["monitor_plugin_id"])].append(row)
    versions = _version_map(list({key[0] for key in grouped}))
    stale = []
    for (credential_id, instance_id, plugin_id), items in grouped.items():
        remote = versions.get(credential_id)
        applied = min(int(item["vault_applied_version"] or 0) for item in items)
        all_not_found = all(item["vault_sync_error"] == "not_found" for item in items)
        if remote is None:
            if all_not_found:
                continue
        elif int(remote) <= applied:
            continue
        sync_error = next((item["vault_sync_error"] for item in items if item["vault_sync_error"]), "")
        synced_at = None if any(item["vault_synced_at"] is None for item in items) else min(item["vault_synced_at"] for item in items)
        stale.append(
            {
                "credential_id": credential_id,
                "instance_id": instance_id,
                "monitor_plugin_id": plugin_id,
                "sync_error": sync_error,
                "synced_at": synced_at,
            }
        )
    return stale


def _select_quota(groups):
    failed = [item for item in groups if item.get("sync_error")]
    clean = [item for item in groups if not item.get("sync_error")]
    failed.sort(key=_synced_sort)
    clean.sort(key=_synced_sort)
    failed_budget = min(len(failed), _FAILED_QUOTA)
    clean_budget = min(len(clean), _RECONCILE_LIMIT - failed_budget)
    leftover = _RECONCILE_LIMIT - failed_budget - clean_budget
    if leftover and len(failed) > failed_budget:
        failed_budget = min(len(failed), failed_budget + leftover)
    return failed[:failed_budget] + clean[:clean_budget]


def _synced_sort(item):
    synced_at = item.get("synced_at")
    return (synced_at is not None, synced_at or "")


def _version_map(credential_ids):
    versions = {}
    ids = [str(item) for item in credential_ids if item]
    for offset in range(0, len(ids), _VERSION_BATCH):
        chunk = ids[offset : offset + _VERSION_BATCH]
        if not chunk:
            continue
        payload = SystemMgmt().get_credential_versions(chunk)
        if not isinstance(payload, dict) or payload.get("result") is False:
            raise RuntimeError("credential versions unavailable")
        chunk_versions = (payload.get("data") or {}).get("versions")
        if not isinstance(chunk_versions, dict):
            raise RuntimeError("credential versions unavailable")
        versions.update(chunk_versions)
    return versions


def _apply_groups(groups, *, trigger, skip_locked):
    counts = {"processed": 0, "success": 0, "failed": 0, "skipped": 0}
    for group in groups:
        status = apply_vault_credential(
            group["credential_id"],
            group["instance_id"],
            group["monitor_plugin_id"],
            trigger=trigger,
            skip_locked=skip_locked,
        )
        counts["processed"] += 1
        if status == "success":
            counts["success"] += 1
        elif status == "failed":
            counts["failed"] += 1
        else:
            counts["skipped"] += 1
        logger.debug(
            "event=vault_credential_apply_finished credential_id=%s instance_id=%s plugin_id=%s status=%s trigger=%s",
            group["credential_id"],
            group["instance_id"],
            group["monitor_plugin_id"],
            status,
            trigger,
        )
    return counts
