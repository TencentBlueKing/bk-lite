def extract_metric_names(display_fields):
    """从 display_fields 抽取所有绑定指标名的并集（保持首次出现顺序，去重）。"""
    names = []
    seen = set()
    for col in display_fields or []:
        for binding in col.get("metrics", []):
            metric = binding.get("metric")
            if metric and metric not in seen:
                seen.add(metric)
                names.append(metric)
    return names
