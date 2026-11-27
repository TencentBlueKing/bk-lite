"""把已声明的数据源参数填进 SQL、JSON 模板或 Excel 行。

NATS 把参数原样转给下游。这里只服务 MySQL、PostgreSQL、REST、Excel、Elasticsearch。
占位符按参数名生成。标量是名字本身，时间范围和日期范围是名字加 _start / _end。
SQL 只认冒号，JSON 只认整段双括号。另一种写法不会替换；本数据源的占位符又不在时返回 400。
日期范围的结束日是最后一天的下一天，比较时用大于等于开始并且小于结束。
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

from apps.operation_analysis.services.filter_snapshot import FilterSnapshotError
from apps.operation_analysis.services.filter_snapshot_resolver import resolve_date_range
from apps.operation_analysis.services.user_messages import oa_message


def _error(message: str, *, code: str):
    from apps.operation_analysis.services.datasource_preview.base import ConnectorError

    return ConnectorError(message, code=code)


def _fail(message_key: str, default: str, *, code: str, **params: object):
    return _error(oa_message(message_key, default, **params), code=code)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SQL_PLACEHOLDER_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
SQL_BRACED_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
TEMPLATE_PLACEHOLDER_RE = re.compile(r"^\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}$")
COLON_PLACEHOLDER_RE = re.compile(r"^:([A-Za-z_][A-Za-z0-9_]*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCALAR_TYPES = {"string", "number", "boolean", "date"}
RANGE_TYPES = {"timeRange", "dateRange"}
TEMPLATE_SOURCE_TYPES = {"mysql", "postgresql", "rest_api", "elasticsearch"}
DECLARED_PARAM_SOURCE_TYPES = TEMPLATE_SOURCE_TYPES | {"excel"}

_TRUE_TEXT = {"true", "1", "yes"}
_FALSE_TEXT = {"false", "0", "no"}


def validate_declared_params(source_type: str | None, params: list | None) -> None:
    if source_type not in DECLARED_PARAM_SOURCE_TYPES or not params:
        return
    if not isinstance(params, list):
        raise _error(oa_message("messages.params_array", "params 必须为数组"), code="params_array")

    range_count = 0
    for index, param in enumerate(params):
        if not isinstance(param, dict):
            raise _error(
                oa_message("messages.indexed_must_be_object", "[{index}] 必须为对象", index=index),
                code="params_item_invalid",
            )
        param_type = param.get("type")
        name = param.get("name")
        if param_type == "conditionFilter":
            raise _error(
                oa_message("messages.param_condition_unsupported", "该数据源不支持条件过滤参数"),
                code="param_condition_unsupported",
            )
        if param_type in RANGE_TYPES:
            range_count += 1
        if source_type in TEMPLATE_SOURCE_TYPES and isinstance(name, str) and name and not IDENTIFIER_RE.match(name):
            raise _error(
                oa_message(
                    "messages.param_name_identifier",
                    "参数名 {name} 只能使用英文字母、数字和下划线，且不能以数字开头",
                    name=name,
                ),
                code="param_name_invalid",
            )
    if range_count > 1:
        raise _error(
            oa_message("messages.param_single_range", "只能配置一个时间范围或日期范围参数"),
            code="param_single_range",
        )


def apply_sql_bindings(sql: str, param_specs: list | None, resolved: dict | None) -> tuple[str, dict[str, Any]]:
    binds = _bindings_for_resolved(param_specs, resolved)
    if not binds and not _declared_names(param_specs):
        return sql, {}
    present = set(SQL_PLACEHOLDER_RE.findall(sql or ""))
    foreign = set(SQL_BRACED_RE.findall(sql or ""))
    _reject_wrong_style(param_specs, present, foreign, style="sql")
    _require_placeholders(binds, present, style="sql")
    _require_unbound_references(param_specs, resolved, present)
    return sql, binds


def apply_json_template(payload: Any, param_specs: list | None, resolved: dict | None) -> Any:
    binds = _bindings_for_resolved(param_specs, resolved)
    if not binds and not _declared_names(param_specs):
        return payload
    cloned = deepcopy(payload)
    present: set[str] = set()
    foreign: set[str] = set()
    replaced = _replace_template_node(cloned, binds, present, foreign)
    _reject_wrong_style(param_specs, present, foreign, style="template")
    _require_placeholders(binds, present, style="template")
    _require_unbound_references(param_specs, resolved, present)
    return replaced


def filter_excel_rows(rows: list, param_specs: list | None, resolved: dict | None) -> list:
    columns = _bound_excel_columns(param_specs, resolved)
    if columns:
        headers: set[str] = set()
        for row in rows or []:
            if isinstance(row, dict):
                headers.update(key for key in row.keys() if isinstance(key, str))
        if headers:
            missing = [name for name in columns if name not in headers]
            if missing:
                raise _fail(
                    "messages.param_placeholder_missing",
                    "查询没有引用这些参数：{names}",
                    code="param_placeholder_missing",
                    names=", ".join(missing),
                )
    predicates = _excel_predicates(param_specs, resolved)
    if not predicates:
        return rows
    return [row for row in rows if isinstance(row, dict) and all(predicate(row) for predicate in predicates)]


def _bound_excel_columns(param_specs: list | None, resolved: dict | None) -> list[str]:
    values = resolved if isinstance(resolved, dict) else {}
    columns = []
    for spec in param_specs or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if isinstance(name, str) and name and name in values:
            columns.append(name)
    return columns


def _declared_names(param_specs: list | None) -> set[str]:
    names = set()
    for spec in param_specs or []:
        if isinstance(spec, dict) and isinstance(spec.get("name"), str) and spec.get("name"):
            names.add(spec["name"])
    return names


def _bindings_for_resolved(param_specs: list | None, resolved: dict | None) -> dict[str, Any]:
    values = resolved if isinstance(resolved, dict) else {}
    binds: dict[str, Any] = {}
    for spec in param_specs or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not name or name not in values:
            continue
        binds.update(_bind_one(name, spec.get("type"), values[name]))
    return binds


def _bind_one(name: str, param_type: str | None, value: Any) -> dict[str, Any]:
    if param_type in RANGE_TYPES:
        start, end = _range_endpoints(name, param_type, value)
        return {f"{name}_start": start, f"{name}_end": end}
    if param_type not in SCALAR_TYPES:
        raise _error(
            oa_message("messages.param_type_unsupported", "参数 {name} 的类型不能填进查询", name=name),
            code="param_type_unsupported",
        )
    if isinstance(value, (list, dict)):
        raise _error(
            oa_message("messages.param_multiple_unsupported", "参数 {name} 只接受单个值", name=name),
            code="param_multiple_unsupported",
        )
    return {name: value}


def _range_endpoints(name: str, param_type: str, value: Any) -> tuple[Any, Any]:
    if param_type == "dateRange":
        start, end = _date_range_pair(name, value)
        return start, _next_day(end)
    start, end = _time_range_pair(name, value)
    return start, end


def _date_range_pair(name: str, value: Any) -> tuple[str, str]:
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(item, str) and DATE_RE.match(item) for item in value):
        if value[0] > value[1]:
            raise _range_error(name)
        return value[0], value[1]
    if isinstance(value, dict):
        range_type = value.get("rangeType")
        if range_type == "custom":
            start = value.get("startDate")
            end = value.get("endDate")
            if not (isinstance(start, str) and isinstance(end, str) and DATE_RE.match(start) and DATE_RE.match(end) and start <= end):
                raise _range_error(name)
            return start, end
        if isinstance(range_type, str):
            try:
                return resolve_date_range(range_type, reference_at=datetime.now(timezone.utc), timezone_name="UTC")
            except FilterSnapshotError as exc:
                raise _range_error(name) from exc
    raise _range_error(name)


def _time_range_pair(name: str, value: Any) -> tuple[str, str]:
    pair = None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        pair = value
    elif isinstance(value, dict) and value.get("start") and value.get("end") and not _positive_minutes(value.get("selectValue")):
        pair = (value.get("start"), value.get("end"))
    if pair is None or not all(isinstance(item, str) and item.strip() for item in pair):
        raise _range_error(name)
    return str(pair[0]), str(pair[1])


def _positive_minutes(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _next_day(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return (parsed + timedelta(days=1)).isoformat()


def _range_error(name: str):
    return _fail(
        "messages.param_range_invalid",
        "参数 {name} 不是可用的时间范围",
        code="param_range_invalid",
        name=name,
    )


def _require_unbound_references(param_specs: list | None, resolved: dict | None, present: set[str]) -> None:
    values = resolved if isinstance(resolved, dict) else {}
    for spec in param_specs or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not name or name in values:
            continue
        expected = [f"{name}_start", f"{name}_end"] if spec.get("type") in RANGE_TYPES else [name]
        if any(item in present for item in expected):
            raise _error(
                oa_message("messages.param_value_missing", "参数 {name} 没有值", name=name),
                code="param_value_missing",
            )


def _placeholder_names(name: str, param_type: str | None) -> list[str]:
    if param_type in RANGE_TYPES:
        return [f"{name}_start", f"{name}_end"]
    return [name]


def _reject_wrong_style(param_specs: list | None, present: set[str], foreign: set[str], *, style: str) -> None:
    missing = []
    for spec in param_specs or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            continue
        native = _placeholder_names(name, spec.get("type"))
        watched = [name, *native] if spec.get("type") in RANGE_TYPES else native
        if any(token in foreign for token in watched) and not any(token in present for token in native):
            missing.extend(native)
    if missing:
        _raise_placeholder_missing(missing, style=style)


def _require_placeholders(binds: dict[str, Any], present: set[str], *, style: str) -> None:
    missing = [name for name in binds if name not in present]
    if missing:
        _raise_placeholder_missing(missing, style=style)


def _raise_placeholder_missing(names: list[str], *, style: str) -> None:
    rendered = ", ".join(f":{name}" if style == "sql" else "{{" + name + "}}" for name in names)
    raise _error(
        oa_message(
            "messages.param_placeholder_missing",
            "查询没有引用这些参数：{names}",
            names=rendered,
        ),
        code="param_placeholder_missing",
    )


def _replace_template_node(node: Any, binds: dict[str, Any], present: set[str], foreign: set[str]) -> Any:
    if isinstance(node, dict):
        return {key: _replace_template_node(value, binds, present, foreign) for key, value in node.items()}
    if isinstance(node, list):
        return [_replace_template_node(value, binds, present, foreign) for value in node]
    if isinstance(node, str):
        match = TEMPLATE_PLACEHOLDER_RE.match(node)
        if match:
            present.add(match.group(1))
            if match.group(1) in binds:
                return binds[match.group(1)]
        colon = COLON_PLACEHOLDER_RE.match(node)
        if colon:
            foreign.add(colon.group(1))
    return node


def _excel_predicates(param_specs: list | None, resolved: dict | None):
    values = resolved if isinstance(resolved, dict) else {}
    predicates = []
    for spec in param_specs or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not isinstance(name, str) or not name or name not in values:
            continue
        param_type = spec.get("type")
        value = values[name]
        if param_type in RANGE_TYPES:
            start, end = _range_endpoints(name, param_type, value)
            predicates.append(_range_predicate(name, start, end))
        elif param_type in SCALAR_TYPES:
            if isinstance(value, (list, dict)):
                raise _error(
                    oa_message("messages.param_multiple_unsupported", "参数 {name} 只接受单个值", name=name),
                    code="param_multiple_unsupported",
                )
            predicates.append(_scalar_predicate(name, param_type, value))
        else:
            raise _error(
                oa_message("messages.param_type_unsupported", "参数 {name} 的类型不能填进查询", name=name),
                code="param_type_unsupported",
            )
    return predicates


def _scalar_predicate(column: str, param_type: str, expected: Any):
    def matches(row: dict) -> bool:
        if column not in row:
            return False
        cell = row.get(column)
        if param_type == "number":
            try:
                return float(cell) == float(expected)
            except (TypeError, ValueError):
                return False
        if param_type == "boolean":
            return _as_bool(cell) is _as_bool(expected) and _as_bool(cell) is not None
        return str(cell).strip() == str(expected).strip()

    return matches


def _range_predicate(column: str, start: Any, end: Any):
    def matches(row: dict) -> bool:
        if column not in row:
            return False
        current = _parse_cell_datetime(row.get(column))
        if current is None:
            return False
        start_at = _parse_cell_datetime(start)
        end_at = _parse_cell_datetime(end)
        if start_at is None or end_at is None:
            return False
        current, start_at, end_at = _align_timezones(current, start_at, end_at)
        return start_at <= current < end_at

    return matches


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_TEXT:
            return True
        if lowered in _FALSE_TEXT:
            return False
    return None


def _parse_cell_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _align_timezones(*moments: datetime) -> tuple[datetime, ...]:
    if all(moment.tzinfo is None for moment in moments):
        return moments
    aligned = []
    for moment in moments:
        if moment.tzinfo is None:
            aligned.append(moment.replace(tzinfo=timezone.utc))
        else:
            aligned.append(moment)
    return tuple(aligned)
