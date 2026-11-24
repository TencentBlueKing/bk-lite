"""监控接口查询。先把范围收进有权实例，算完当前值，再过滤、排序和分页。"""

from __future__ import annotations

from apps.core.logger import monitor_logger as logger
from apps.monitor.services.generic_query import GenericQueryError, _checked_sort, _optional_page, _table
from apps.monitor.services.generic_query_limits import INSTANCE_LIST_MAX
from apps.monitor.services.instance_distribution import _object_labels
from apps.monitor.services.interface_metrics_query import (
    INTERFACE_METRIC_QUERIES,
    build_instance_id_selector,
    merge_interface_metric_rows,
    parse_instant_vector,
)
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.vm_query_batch import run_unique_vm_queries

MATCH_ALL = "all"
MATCH_UP = "up"
MATCH_DOWN = "down"
MATCH_ERROR = "error"
MATCH_DISCARD = "discard"
_MATCHES = {MATCH_ALL, MATCH_UP, MATCH_DOWN, MATCH_ERROR, MATCH_DISCARD}
_SORT_FIELDS = {"in_rate", "out_rate", "error_rate", "if_name"}
_OPER = "interface_ifOperStatus"
_HC_IN = "interface_ifHCInOctets"
_HC_OUT = "interface_ifHCOutOctets"
_IN = "interface_ifInOctets"
_OUT = "interface_ifOutOctets"
_ERR_IN = "interface_ifInErrors"
_ERR_OUT = "interface_ifOutErrors"
_DISC_IN = "interface_ifInDiscards"
_DISC_OUT = "interface_ifOutDiscards"
# ifHighSpeed、ifSpeed 不参与。32 位和 64 位同批读取，这样只有 32 位的接口仍在统计里；两边都有时用 64 位。
_SNAPSHOT_METRICS = (_OPER, _HC_IN, _HC_OUT, _IN, _OUT, _ERR_IN, _ERR_OUT, _DISC_IN, _DISC_OUT)
_COUNT_METRICS = {
    MATCH_ALL: _SNAPSHOT_METRICS,
    MATCH_UP: (_OPER,),
    MATCH_DOWN: (_OPER,),
    MATCH_ERROR: (_ERR_IN, _ERR_OUT),
    MATCH_DISCARD: (_DISC_IN, _DISC_OUT),
}
_TEMPLATES = {name: template for name, template, _is_rate in INTERFACE_METRIC_QUERIES}
# 与采集查询同一量级：一条选择器里的实例标签预算，超出后拆块。
_SELECTOR_BUDGET = 8000
# 超过后走 form POST，避免选择器撑破 URL。
_LONG_QUERY = 3000
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


def query_interface_current_count(instances, *, interface_match=None, vm_api=None) -> int:
    """范围内按接口情况计数。只读判定指标，不算明细列，不排序。"""
    match = _match(interface_match)
    scoped = list(instances)
    if not scoped:
        return 0
    by_id, by_label = _indexes(scoped)
    items = _query_metrics(vm_api or VictoriaMetricsAPI(), _scope_labels(scoped), _COUNT_METRICS[match])
    total = 0
    for item in items:
        owners = _owners(item.get("instance_id"), by_id, by_label)
        if owners and _keeps(_stat_row(item), match):
            total += len(owners)
    return total


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
    by_id, by_label = _indexes(instances)
    objects = []
    seen = set()
    for instance in instances:
        monitor_object = instance.monitor_object
        if monitor_object is not None and monitor_object.id not in seen:
            seen.add(monitor_object.id)
            objects.append(monitor_object)
    object_labels = _object_labels(objects, locale)
    # 块只划分实例范围。合并全部块之后才过滤、排序和分页。
    items = _query_metrics(vm_api, _scope_labels(instances), _SNAPSHOT_METRICS)
    matched = []
    for item in items:
        owners = _owners(item.get("instance_id"), by_id, by_label)
        for instance in owners:
            matched.append(_present(instance, item, object_labels))
    kept = [row for row in matched if _keeps(row, match)]
    for row in kept:
        row["oper_status"] = _oper_label(row["oper_status"])
    return kept


def _indexes(instances):
    by_id = {}
    by_label: dict[str, list] = {}
    for instance in instances:
        by_id[str(instance.id)] = instance
        by_label.setdefault(_vm_label(instance.id), []).append(instance)
    return by_id, by_label


def _scope_labels(instances) -> list[str]:
    labels = []
    seen = set()
    for instance in instances:
        label = _vm_label(instance.id)
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _label_chunks(labels: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for label in labels:
        trial = current + [label]
        if current and len(build_instance_id_selector(trial)) > _SELECTOR_BUDGET:
            chunks.append(current)
            current = [label]
        else:
            current = trial
    if current:
        chunks.append(current)
    return chunks


def _query_metrics(vm_api, labels: list[str], metric_names: tuple[str, ...]) -> list[dict]:
    if not labels:
        return []
    jobs = []
    for chunk in _label_chunks(labels):
        selector = build_instance_id_selector(chunk)
        for name in metric_names:
            jobs.append((name, _TEMPLATES[name].format(selector=selector)))
    results, errors = run_unique_vm_queries(
        (promql for _name, promql in jobs),
        lambda promql: _read_instant(vm_api, promql),
    )
    if errors:
        failed = next(promql for promql in errors)
        metric_name = next(name for name, promql in jobs if promql == failed)
        _fail_metric_query(metric_name, errors[failed])
    rows = []
    for name, promql in jobs:
        rows.extend(parse_instant_vector(results.get(promql), name))
    return merge_interface_metric_rows(rows)


def _read_instant(vm_api, promql: str):
    if len(promql) > _LONG_QUERY and hasattr(vm_api, "query_form"):
        return vm_api.query_form(promql, step="5m")
    return vm_api.query(promql, step="5m")


def _fail_metric_query(metric_name: str, exc: Exception):
    try:
        raise exc
    except Exception:
        logger.exception("interface metric query failed metric=%s", metric_name)
        raise GenericQueryError("接口指标查询失败") from exc


def _stat_row(item: dict) -> dict:
    metrics = item.get("metrics") or {}
    return {
        "oper_status": _number(metrics.get(_OPER)),
        "in_errors": _number(metrics.get(_ERR_IN)),
        "out_errors": _number(metrics.get(_ERR_OUT)),
        "in_discards": _number(metrics.get(_DISC_IN)),
        "out_discards": _number(metrics.get(_DISC_OUT)),
    }


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
