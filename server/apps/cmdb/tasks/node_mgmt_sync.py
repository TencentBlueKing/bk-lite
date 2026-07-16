from typing import Any

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService


def run_sync() -> dict[str, Any]:
    NodeMgmtSyncService.recover_stale_runs()
    return NodeMgmtSyncService.trigger_sync()


def run_collect() -> dict[str, Any]:
    NodeMgmtSyncService.recover_stale_runs()
    return NodeMgmtSyncService.trigger_collect()
