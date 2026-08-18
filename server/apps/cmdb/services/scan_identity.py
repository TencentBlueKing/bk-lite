NETWORK_CI_TYPES = frozenset({"switch", "router", "firewall", "loadbalance"})


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
