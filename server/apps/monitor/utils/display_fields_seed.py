def build_seed_display_fields(plugin_name, supplementary_indicators, metrics):
    """无显式 display_fields 块时，从 supplementary_indicators 派生默认展示列。"""
    display_name_map = {m["name"]: m.get("display_name") or m["name"] for m in metrics}
    columns = []
    for idx, metric_name in enumerate(supplementary_indicators or []):
        if metric_name not in display_name_map:
            continue
        columns.append(
            {
                "name": display_name_map[metric_name],
                "sort_order": idx,
                "metrics": [{"plugin": plugin_name, "metric": metric_name}],
            }
        )
    return columns


def merge_display_fields_bindings(*blocks):
    """后写块决定列名与顺序，同名列的 (plugin, metric) 绑定取并集。

    多个插件共享同一 MonitorObject（如 Host / Host Remote / Windows WMI /
    Host AIX Remote）时，plugin_init 不能用最后一份 display_fields 整表覆盖，
    否则会丢掉先写入的跨插件绑定。不新增后写块没有的列名。
    """
    present = [list(block) for block in blocks if block]
    if not present:
        return None
    bindings_by_name = {}
    for block in present:
        for col in block:
            if not isinstance(col, dict):
                continue
            name = col.get("name")
            if not name:
                continue
            seen = bindings_by_name.setdefault(name, [])
            seen_keys = {(item.get("plugin"), item.get("metric"), item.get("field")) for item in seen}
            for bind in col.get("metrics") or []:
                if not isinstance(bind, dict):
                    continue
                key = (bind.get("plugin"), bind.get("metric"), bind.get("field"))
                if key in seen_keys:
                    continue
                seen.append(dict(bind))
                seen_keys.add(key)
    merged = []
    for col in present[-1]:
        if not isinstance(col, dict):
            continue
        item = dict(col)
        name = item.get("name")
        if name in bindings_by_name:
            item["metrics"] = bindings_by_name[name]
        merged.append(item)
    return merged
