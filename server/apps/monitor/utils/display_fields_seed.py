def build_seed_display_fields(plugin_name, supplementary_indicators, metrics):
    """无显式 display_fields 块时，从 supplementary_indicators 派生默认展示列。"""
    display_name_map = {m["name"]: m.get("display_name") or m["name"] for m in metrics}
    columns = []
    for idx, metric_name in enumerate(supplementary_indicators or []):
        if metric_name not in display_name_map:
            continue
        columns.append({
            "name": display_name_map[metric_name],
            "sort_order": idx,
            "metrics": [{"plugin": plugin_name, "metric": metric_name}],
        })
    return columns
