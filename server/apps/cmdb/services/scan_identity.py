from apps.cmdb.models.scan_model import SCAN_DATABASE_TYPES, ScanExecution
from apps.core.exceptions.base_app_exception import BaseAppException

NETWORK_CI_TYPES = frozenset({"switch", "router", "firewall", "loadbalance"})
UNMATCH_UNKNOWN_SOID = "unknown_soid"
UNMATCH_EMPTY_SOID = "empty_soid"
UNMATCH_CREDENTIAL_FAILED = "credential_failed"
_TERMINAL_STATUSES = frozenset(
    {
        ScanExecution.STATUS_COMPLETED,
        ScanExecution.STATUS_FAILED,
        ScanExecution.STATUS_TIMED_OUT,
    }
)


def ensure_scan_execution_terminal(execution: ScanExecution, message: str = "扫描尚未收口，不能执行该操作"):
    if getattr(execution, "status", None) not in _TERMINAL_STATUSES:
        raise BaseAppException(message)


def _hit_snapshot(hit) -> dict:
    snapshot = getattr(hit, "snapshot", None)
    return snapshot if isinstance(snapshot, dict) else {}


def suggested_network_type(hit) -> str:
    """特征库或手选写入 snapshot 的建议类型；写入 CI 前对象模型列仍可为空。"""
    model_id = str(getattr(hit, "cmdb_model_id", "") or "").strip()
    if model_id in NETWORK_CI_TYPES:
        return model_id
    snapshot = _hit_snapshot(hit)
    device_type = str(snapshot.get("device_type") or "").strip()
    if device_type in NETWORK_CI_TYPES:
        return device_type
    return ""


def unmatch_reason_for_hit(hit) -> str:
    """尚未分类时给出可扩展原因；已有模型或建议类型的命中不进未匹配。"""
    family = str(getattr(getattr(hit, "family_run", None), "model_id", "") or "").strip()
    if str(getattr(hit, "cmdb_model_id", "") or "").strip():
        return ""
    if family == "network":
        if suggested_network_type(hit):
            return ""
        soid = str(getattr(hit, "soid", "") or "").strip()
        if soid:
            return UNMATCH_UNKNOWN_SOID
        return UNMATCH_EMPTY_SOID
    if family in SCAN_DATABASE_TYPES:
        status = str(getattr(hit, "status", "") or "")
        credential_id = str(getattr(hit, "credential_id", "") or "").strip()
        if status == "failed" and not credential_id:
            return UNMATCH_CREDENTIAL_FAILED
    return ""


def refine_scan_metrics(model_id, plugin_result, oid_map=None):
    """扫描写 CI 前的后处理。采集 mapping 的未知当 switch 不在这里沿用。"""
    result = plugin_result or {}
    if model_id != "network" and not (set(result) & NETWORK_CI_TYPES):
        return {key: list(rows) for key, rows in result.items()}

    oid_map = oid_map or {}
    refined = {}
    for ci_model, rows in result.items():
        if ci_model == "interface":
            continue
        kept = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            oid = str(row.get("soid") or row.get("oid") or row.get("sysobjectid") or "")
            mapped = oid_map.get(oid) if oid else None
            if not isinstance(mapped, dict):
                continue
            device_type = str(mapped.get("device_type") or "")
            if device_type not in NETWORK_CI_TYPES:
                continue
            kept.append(row)
        if kept:
            refined[ci_model] = kept
    return refined
