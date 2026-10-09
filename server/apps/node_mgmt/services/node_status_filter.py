from apps.node_mgmt.constants.collector import CollectorConstants

ACTIVE_WINDOW_SECONDS = 60

COLLECTOR_STATUS_NORMAL = 0
COLLECTOR_STATUS_UNKNOWN = 1
COLLECTOR_STATUS_ERROR = 2
COLLECTOR_STATUS_STOPPED = 3
COLLECTOR_STATUS_NOT_STARTED = 4
COLLECTOR_STATUS_INSTALLING = 10
COLLECTOR_STATUS_INSTALLED_NOT_STARTED = 11
COLLECTOR_STATUS_FAIL_INSTALL = 12

INSTALL_STATUS_SUCCESS = "success"
INSTALL_STATUS_ERROR = "error"
INSTALL_STATUS_RUNNING = "running"

ALLOWED_COLLECTOR_STATUS_CODES = {
    COLLECTOR_STATUS_NORMAL,
    COLLECTOR_STATUS_UNKNOWN,
    COLLECTOR_STATUS_ERROR,
    COLLECTOR_STATUS_STOPPED,
    COLLECTOR_STATUS_NOT_STARTED,
    COLLECTOR_STATUS_INSTALLING,
    COLLECTOR_STATUS_INSTALLED_NOT_STARTED,
    COLLECTOR_STATUS_FAIL_INSTALL,
}

STATUS_FILTER_ALIASES = {
    "not_started": {COLLECTOR_STATUS_NOT_STARTED, COLLECTOR_STATUS_INSTALLED_NOT_STARTED},
}


def collector_status_codes_from_filter_values(values):
    codes = set()
    if not values:
        return codes
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    for raw in values:
        if raw is None or raw == "":
            continue
        key = str(raw).strip().lower()
        if key in STATUS_FILTER_ALIASES:
            codes.update(STATUS_FILTER_ALIASES[key])
            continue
        try:
            code = int(raw)
        except (TypeError, ValueError):
            continue
        if code in ALLOWED_COLLECTOR_STATUS_CODES:
            codes.add(code)
    return codes


def install_row_display_status(install_status):
    if install_status == INSTALL_STATUS_SUCCESS:
        return COLLECTOR_STATUS_INSTALLED_NOT_STARTED
    if install_status == INSTALL_STATUS_ERROR:
        return COLLECTOR_STATUS_FAIL_INSTALL
    return COLLECTOR_STATUS_INSTALLING


def apply_display_collector_status(status, collector_name, verbose_message=""):
    try:
        display_status = int(status)
    except (TypeError, ValueError):
        return COLLECTOR_STATUS_UNKNOWN
    if display_status == COLLECTOR_STATUS_ERROR and collector_name in CollectorConstants.IGNORE_ERROR_COLLECTORS:
        message = verbose_message or ""
        if any(token in message for token in CollectorConstants.IGNORE_ERROR_COLLECTORS_MESSAGES):
            return COLLECTOR_STATUS_NORMAL
    return display_status


def _normalize_name(value):
    return str(value or "").strip().lower()


def collector_name_matches(collector_name, wanted_name):
    if not wanted_name:
        return True
    return _normalize_name(collector_name) == _normalize_name(wanted_name)


def hosted_collectors_for_filter(reported, install_rows, collector_name_by_id):
    hosted = []
    seen_ids = set()
    for item in reported or []:
        if not isinstance(item, dict):
            continue
        collector_id = item.get("collector_id")
        if collector_id in (None, ""):
            continue
        collector_id = str(collector_id)
        seen_ids.add(collector_id)
        name = collector_name_by_id.get(collector_id) or item.get("collector_name")
        hosted.append(
            {
                "collector_id": collector_id,
                "collector_name": name,
                "status": apply_display_collector_status(
                    item.get("status"),
                    name,
                    item.get("verbose_message") or "",
                ),
            }
        )
    for row in install_rows or []:
        if not isinstance(row, dict):
            continue
        collector_id = row.get("collector_id")
        if collector_id in (None, "") or str(collector_id) in seen_ids:
            continue
        collector_id = str(collector_id)
        name = collector_name_by_id.get(collector_id) or row.get("collector_name")
        hosted.append(
            {
                "collector_id": collector_id,
                "collector_name": name,
                "status": install_row_display_status(row.get("status")),
            }
        )
    return hosted


def node_matches_collector_filter(hosted, wanted_codes, collector_name=None):
    if not wanted_codes:
        return True
    wanted_name = (collector_name or "").strip() or None
    for item in hosted or []:
        if wanted_name and not collector_name_matches(item.get("collector_name"), wanted_name):
            continue
        try:
            status = int(item.get("status"))
        except (TypeError, ValueError):
            continue
        if status in wanted_codes:
            return True
    return False
