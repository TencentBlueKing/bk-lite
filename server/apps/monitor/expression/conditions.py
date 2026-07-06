from apps.monitor.expression.labels import format_to_vm_filter


def split_filter_groups(filters: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for index, item in enumerate(filters or []):
        logic = str(item.get("logic") or "and").lower()
        if logic not in {"and", "or"}:
            raise ValueError(f"filter[{index}].logic 非法，只允许 and/or")
        if index == 0:
            logic = "and"
        if logic == "or" and current:
            groups.append(current)
            current = []
        condition = {key: item.get(key) for key in ("name", "method", "value")}
        current.append(condition)
    if current:
        groups.append(current)
    return groups


def compile_filter_to_selectors(
    metric_query: str,
    filters: list[dict],
    base_filters: list[dict] | None = None,
) -> list[str]:
    groups = split_filter_groups(filters)
    base_filters = base_filters or []
    if not groups:
        vm_filter = format_to_vm_filter(base_filters) if base_filters else ""
        return [metric_query.replace("__$labels__", vm_filter)]

    selectors: list[str] = []
    for group in groups:
        vm_filter = format_to_vm_filter([*base_filters, *group])
        selectors.append(metric_query.replace("__$labels__", vm_filter))
    return selectors


def compile_filter_to_query(
    metric_query: str,
    filters: list[dict],
    base_filters: list[dict] | None = None,
) -> str:
    selectors = compile_filter_to_selectors(metric_query, filters, base_filters)
    if len(selectors) == 1:
        return selectors[0]
    return " or ".join(f"({selector})" for selector in selectors)
