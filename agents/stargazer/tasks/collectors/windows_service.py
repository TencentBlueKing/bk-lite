from typing import Any

SERVICE_SCOPE_NONE = "none"
SERVICE_SCOPE_ALL = "all"
SERVICE_SCOPE_NAMES = "names"
WINDOWS_SERVICE_QUERY = "SELECT Name, State FROM Win32_Service"


def normalize_service_scope(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in {SERVICE_SCOPE_ALL, SERVICE_SCOPE_NAMES}:
        return value
    return SERVICE_SCOPE_NONE


def parse_service_names(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple)):
        items = raw
    else:
        items = str(raw or "").split(",")
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = str(item).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def should_collect_windows_service(scope: Any, names: Any = None) -> bool:
    normalized = normalize_service_scope(scope)
    if normalized == SERVICE_SCOPE_ALL:
        return True
    if normalized == SERVICE_SCOPE_NAMES:
        return bool(parse_service_names(names))
    return False


def windows_service_state_value(state: Any) -> int:
    if isinstance(state, bool):
        return int(state)
    if isinstance(state, (int, float)):
        return 1 if int(state) == 1 else 0
    text = str(state or "").strip()
    if text == "1":
        return 1
    return 1 if text.lower() == "running" else 0


def _row_service_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("name") or row.get("Name") or "").strip()


def _row_service_state(row: Any) -> Any:
    if not isinstance(row, dict):
        return row
    if "state" in row:
        return row.get("state")
    return row.get("State")


def select_windows_services(rows: Any, scope: Any, names: Any = None) -> list[dict[str, Any]]:
    normalized = normalize_service_scope(scope)
    if normalized == SERVICE_SCOPE_NONE:
        return []

    parsed_rows: list[dict[str, Any]] = []
    by_lower: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        name = _row_service_name(row)
        if not name:
            continue
        item = {
            "name": name,
            "state": windows_service_state_value(_row_service_state(row)),
            "service_scope": normalized,
        }
        parsed_rows.append(item)
        by_lower[name.lower()] = item

    if normalized == SERVICE_SCOPE_ALL:
        return parsed_rows

    wanted = parse_service_names(names)
    if not wanted:
        return []

    selected: list[dict[str, Any]] = []
    for wanted_name in wanted:
        existing = by_lower.get(wanted_name.lower())
        if existing:
            selected.append({**existing, "service_scope": SERVICE_SCOPE_NAMES})
        else:
            selected.append(
                {
                    "name": wanted_name,
                    "state": 0,
                    "service_scope": SERVICE_SCOPE_NAMES,
                }
            )
    return selected
