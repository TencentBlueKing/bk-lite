"""监控接口查询。按 IF-MIB 即时查询后，与有权实例相交，一行一个接口。"""

from __future__ import annotations

from apps.core.logger import monitor_logger as logger
from apps.monitor.services.generic_query import GenericQueryError, _checked_sort, _optional_page, _table
from apps.monitor.services.generic_query_limits import INSTANCE_LIST_MAX
from apps.monitor.services.instance_distribution import _object_labels
from apps.monitor.services.interface_metrics_query import INTERFACE_METRIC_QUERIES, merge_interface_metric_rows, parse_instant_vector
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

MATCH_ALL = "all"
MATCH_UP = "up"
MATCH_DOWN = "down"
MATCH_ERROR = "error"
MATCH_DISCARD = "discard"
_MATCHES = {MATCH_ALL, MATCH_UP, MATCH_DOWN, MATCH_ERROR, MATCH_DISCARD}
_SORT_FIELDS = {"in_rate", "out_rate", "error_rate", "if_name"}
_OPER_UP = 1
_OPER_DOWN = 2
_OPER_LABELS = {
    1: "Up",
    2: "Down",
    3: "Testing",
    4: "Unknown",
    5: "Dormant",
    6: "NotPresent",
    7: "LowerLayerDown",
}


def query_interface_current_rows(
    instances,
    *,
    interface_match=None,
    order_by=None,
    order_dir=None,
    page=None,
    page_size=None,
    locale=None,
    vm_api=None,
    bounded=True,
):
    match = _match(interface_match)
    requested_sort = _checked_sort(order_by, order_dir, _SORT_FIELDS)
    rows = _rows(list(instances), match=match, locale=locale, vm_api=vm_api or VictoriaMetricsAPI())
    rows.sort(key=lambda row: _sort_key(row, requested_sort))
    return _page(rows, page, page_size, bounded=bounded, present=_with_rate_units)


def _match(value) -> str:
    if value in (None, ""):
        return MATCH_ALL
    text = str(value).strip()
    if text not in _MATCHES:
        raise GenericQueryError("接口情况不受支持")
    return text


def _rows(instances, *, match: str, locale, vm_api) -> list[dict]:
    if not instances:
        return []
    objects = []
    seen = set()
    by_id = {}
    by_label: dict[str, list] = {}
    for instance in instances:
        by_id[str(instance.id)] = instance
        label = _vm_label(instance.id)
        by_label.setdefault(label, []).append(instance)
        monitor_object = instance.monitor_object
        if monitor_object is not None and monitor_object.id not in seen:
            seen.add(monitor_object.id)
            objects.append(monitor_object)
    object_labels = _object_labels(objects, locale)
    matched = []
    for item in _query_interface_rows(vm_api):
        owners = _owners(item.get("instance_id"), by_id, by_label)
        for instance in owners:
            matched.append(_present(instance, item, object_labels))
    kept = [row for row in matched if _keeps(row, match)]
    for row in kept:
        row["oper_status"] = _oper_label(row["oper_status"])
    return kept


def _vm_label(instance_id) -> str:
    parsed = parse_instance_id(instance_id)
    if not parsed:
        return str(instance_id)
    return str(parsed[0] or "").strip() or str(instance_id)


def _owners(vm_instance_id, by_id, by_label):
    vm_id = str(vm_instance_id or "").strip()
    if not vm_id:
        return []
    exact = by_id.get(vm_id)
    if exact is not None:
        return [exact]
    return list(by_label.get(vm_id, []))


def _query_interface_rows(vm_api) -> list[dict]:
    rows = []
    for metric_name, template, _is_rate in INTERFACE_METRIC_QUERIES:
        query = template.format(selector="")
        try:
            payload = vm_api.query(query, step="5m")
        except Exception as exc:
            logger.exception("interface metric query failed metric=%s", metric_name)
            raise GenericQueryError("接口指标查询失败") from exc
        rows.extend(parse_instant_vector(payload, metric_name))
    return merge_interface_metric_rows(rows)


def _present(instance, item: dict, object_labels: dict) -> dict:
    metrics = item.get("metrics") or {}
    monitor_object = instance.monitor_object
    object_id = getattr(monitor_object, "id", None)
    in_rate = _preferred(metrics, "interface_ifHCInOctets", "interface_ifInOctets")
    out_rate = _preferred(metrics, "interface_ifHCOutOctets", "interface_ifOutOctets")
    in_errors = _number(metrics.get("interface_ifInErrors"))
    out_errors = _number(metrics.get("interface_ifOutErrors"))
    in_discards = _number(metrics.get("interface_ifInDiscards"))
    out_discards = _number(metrics.get("interface_ifOutDiscards"))
    return {
        "instance_id": instance.id,
        "instance_name": instance.name or "",
        "monitor_object_name": object_labels.get(object_id, "") if object_id is not None else "",
        "if_name": item.get("ifDescr") or "",
        "oper_status": _number(metrics.get("interface_ifOperStatus")),
        "in_rate": in_rate,
        "out_rate": out_rate,
        "in_errors": in_errors,
        "out_errors": out_errors,
        "in_discards": in_discards,
        "out_discards": out_discards,
    }


def _preferred(metrics: dict, primary: str, fallback: str):
    if primary in metrics:
        return _number(metrics.get(primary))
    if fallback in metrics:
        return _number(metrics.get(fallback))
    return None


def _number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _oper_label(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    code = int(value)
    if code != value:
        return None
    return _OPER_LABELS.get(code, str(code))


def _is_status(value, expected: int) -> bool:
    return value is not None and value == expected


def _positive(value) -> bool:
    return value is not None and value > 0


def _keeps(row: dict, match: str) -> bool:
    if match == MATCH_ALL:
        return True
    if match == MATCH_UP:
        return _is_status(row["oper_status"], _OPER_UP)
    if match == MATCH_DOWN:
        return _is_status(row["oper_status"], _OPER_DOWN)
    if match == MATCH_ERROR:
        return _positive(row["in_errors"]) or _positive(row["out_errors"])
    return _positive(row["in_discards"]) or _positive(row["out_discards"])


def _sort_key(row: dict, requested):
    if requested is None:
        return (
            row["instance_name"].casefold(),
            row["instance_name"],
            row["if_name"].casefold(),
            row["if_name"],
            row["instance_id"],
        )
    field, descending = requested
    if field == "if_name":
        folded = row["if_name"].casefold()
        ranks = tuple(-ord(char) for char in folded) if descending else tuple(ord(char) for char in folded)
        return (folded == "", ranks, row["instance_id"])
    number = _error_sum(row) if field == "error_rate" else row[field]
    if descending:
        return (number is None, -(number or 0), row["if_name"].casefold(), row["instance_id"])
    return (number is None, number or 0, row["if_name"].casefold(), row["instance_id"])


def _error_sum(row: dict):
    if row["in_errors"] is None and row["out_errors"] is None:
        return None
    return (row["in_errors"] or 0) + (row["out_errors"] or 0)


_RATE_STEPS = (
    (1000**4, "TB/s"),
    (1000**3, "GB/s"),
    (1000**2, "MB/s"),
    (1000, "KB/s"),
)


def _rate_text(value):
    """字节/秒换成当前量级，例如 220000 → 220 KB/s。没有采样时保持空。"""
    if value is None:
        return None
    number = float(value)
    sign = "-" if number < 0 else ""
    absolute = abs(number)
    factor, suffix = next(((step, unit) for step, unit in _RATE_STEPS if absolute >= step), (1, "B/s"))
    scaled = absolute / factor
    if scaled == int(scaled):
        text = str(int(scaled))
    else:
        text = f"{scaled:.2f}".rstrip("0").rstrip(".")
    return f"{sign}{text} {suffix}"


def _with_rate_units(rows: list[dict]) -> list[dict]:
    shown = []
    for row in rows:
        item = dict(row)
        item["in_rate"] = _rate_text(row.get("in_rate"))
        item["out_rate"] = _rate_text(row.get("out_rate"))
        shown.append(item)
    return shown


def _page(rows: list[dict], page, page_size, *, bounded: bool, present=None):
    total = len(rows)
    paging = _optional_page(page, page_size)
    if paging is None:
        if bounded and total > INSTANCE_LIST_MAX:
            raise GenericQueryError(f"接口超过 {INSTANCE_LIST_MAX} 条，请缩小范围或填写分页")
        visible = rows
    else:
        page_no, size = paging
        start = (page_no - 1) * size
        visible = rows[start : start + size]
    shown = present(visible) if present else visible
    if paging is None:
        return shown
    return _table(shown, total, page_no, size)
