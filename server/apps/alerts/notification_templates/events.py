"""告警通知模板的事件数据访问与区块产出。

区块只接受 ``key=value`` 声明，没有表达式、条件和自定义循环体。取哪些列、多少条由
使用者决定，具体排版和转义由本模块按渠道生成。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Mapping, Sequence

MAX_EVENT_ROWS = 100
MAX_EVENT_COLUMNS = 10
MAX_EVENT_BLOCKS = 5
MAX_CELL_LENGTH = 200
MAX_LABEL_LENGTH = 32
MAX_JSON_PATH_PARTS = 4
DEFAULT_LIMIT = 10
DEFAULT_ORDER = "-start_time"
DEFAULT_EMPTY = "无关联事件"
MISSING_VALUE = "—"

EVENT_SCALAR_FIELDS = {
    "event_id": "事件 ID",
    "external_id": "外部事件 ID",
    "title": "事件标题",
    "description": "事件描述",
    "level": "事件级别",
    "status": "事件状态",
    "action": "事件动作",
    "event_type": "事件类型",
    "item": "监控指标",
    "value": "事件值",
    "service": "所属服务",
    "location": "发生位置",
    "start_time": "发生时间",
    "end_time": "结束时间",
    "received_at": "接收时间",
    "resource_id": "资源 ID",
    "resource_name": "资源名称",
    "resource_type": "资源类型",
    "push_source_id": "推送来源",
    "rule_id": "规则 ID",
    "source_name": "告警源",
}
EVENT_JSON_ROOTS = {"tags", "labels", "enrichment"}
ORDER_CHOICES = {"-start_time", "start_time", "-received_at", "received_at"}
FORMAT_CHOICES = {"table", "list"}
BLOCK_KEYS = {"columns", "limit", "order", "format", "empty"}

EVENT_PATH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$")
BLOCK_KEY_PATTERN = re.compile(r"(?:^|\s)([a-z_]+)=")
TOKEN_PATTERN = re.compile(r"\{\{@\s*([^{}]*?)\s*@\}\}|\{\{\s*([^{}@]+?)\s*\}\}")
LABEL_FORBIDDEN = set(",={}@")


class EventBlockError(ValueError):
    """事件区块声明不合法。"""


class EventBlockBudgetError(EventBlockError):
    """区块在给定字节预算内放不下一行。"""


@dataclass(frozen=True)
class EventColumn:
    path: str
    label: str


@dataclass(frozen=True)
class EventBlockSpec:
    columns: tuple[EventColumn, ...]
    limit: int | None
    order: str
    fmt: str | None
    empty: str


@dataclass(frozen=True)
class EventUsage:
    orders: frozenset[str]
    need_latest: bool
    need_first: bool
    need_count: bool

    @property
    def used(self) -> bool:
        return bool(self.orders or self.need_latest or self.need_first or self.need_count)


def validate_event_path(path: str) -> None:
    """事件字段路径白名单校验；``raw_data`` 等无界或内部字段不在其中。"""
    if not EVENT_PATH_PATTERN.fullmatch(path):
        raise EventBlockError(f"事件字段语法不合法: {path}")
    parts = path.split(".")
    if parts[0] in EVENT_SCALAR_FIELDS:
        if len(parts) != 1:
            raise EventBlockError(f"该事件字段不支持子路径: {path}")
        return
    if parts[0] in EVENT_JSON_ROOTS:
        if len(parts) < 2:
            raise EventBlockError(f"{parts[0]} 必须指定具体字段: {path}")
        if len(parts) > MAX_JSON_PATH_PARTS:
            raise EventBlockError(f"事件字段路径不能超过 {MAX_JSON_PATH_PARTS} 段: {path}")
        return
    raise EventBlockError(f"不支持的事件字段: {path}")


def default_label(path: str) -> str:
    if path in EVENT_SCALAR_FIELDS:
        return EVENT_SCALAR_FIELDS[path]
    return path.replace(".", "_")


def _split_params(text: str) -> dict[str, str]:
    matches = list(BLOCK_KEY_PATTERN.finditer(text))
    if not matches:
        return {}
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        raise EventBlockError("事件区块存在无法识别的内容")
    params: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = match.group(1)
        if key in params:
            raise EventBlockError(f"事件区块参数重复: {key}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        params[key] = text[match.end() : end].strip()
    return params


def _parse_columns(raw: str) -> tuple[EventColumn, ...]:
    columns: list[EventColumn] = []
    for item in raw.split(","):
        entry = item.strip()
        if not entry:
            continue
        path, separator, label = entry.partition(" as ")
        path = path.strip()
        label = label.strip() if separator else ""
        validate_event_path(path)
        if label:
            if len(label) > MAX_LABEL_LENGTH:
                raise EventBlockError(f"列表头不能超过 {MAX_LABEL_LENGTH} 个字符: {label}")
            if LABEL_FORBIDDEN.intersection(label) or "\n" in label or "\r" in label:
                raise EventBlockError(f"列表头不能包含 , = {{ }} @ : {label}")
        columns.append(EventColumn(path=path, label=label or default_label(path)))
    if not columns:
        raise EventBlockError("事件区块必须至少配置 1 列")
    if len(columns) > MAX_EVENT_COLUMNS:
        raise EventBlockError(f"事件区块最多配置 {MAX_EVENT_COLUMNS} 列")
    if len({column.path for column in columns}) != len(columns):
        raise EventBlockError("事件区块存在重复的列")
    return tuple(columns)


def parse_event_block(body: str) -> EventBlockSpec:
    text = " ".join(body.split())
    if not text.startswith("events"):
        raise EventBlockError("事件区块必须以 events 开头")
    params = _split_params(text[len("events") :].strip())
    unknown = sorted(set(params) - BLOCK_KEYS)
    if unknown:
        raise EventBlockError(f"不支持的事件区块参数: {', '.join(unknown)}")
    if "columns" not in params:
        raise EventBlockError("事件区块必须声明 columns")

    raw_limit = params.get("limit", str(DEFAULT_LIMIT))
    if raw_limit == "all":
        limit = None
    else:
        try:
            limit = int(raw_limit)
        except ValueError:
            raise EventBlockError(f"limit 必须是 1~{MAX_EVENT_ROWS} 的整数或 all: {raw_limit}") from None
        if not 1 <= limit <= MAX_EVENT_ROWS:
            raise EventBlockError(f"limit 必须是 1~{MAX_EVENT_ROWS} 的整数或 all: {raw_limit}")

    order = params.get("order", DEFAULT_ORDER)
    if order not in ORDER_CHOICES:
        raise EventBlockError(f"order 只支持 {', '.join(sorted(ORDER_CHOICES))}")

    fmt = params.get("format")
    if fmt is not None and fmt not in FORMAT_CHOICES:
        raise EventBlockError(f"format 只支持 {', '.join(sorted(FORMAT_CHOICES))}")

    empty = params.get("empty", DEFAULT_EMPTY)
    if len(empty) > MAX_LABEL_LENGTH:
        raise EventBlockError(f"empty 不能超过 {MAX_LABEL_LENGTH} 个字符")

    return EventBlockSpec(columns=_parse_columns(params["columns"]), limit=limit, order=order, fmt=fmt, empty=empty)


def inspect_event_usage(sources: Sequence[str]) -> EventUsage:
    """扫描模板源，决定要不要查事件、查哪种排序。解析失败的区块留给渲染期报错。"""
    orders: set[str] = set()
    need_latest = False
    need_first = False
    need_count = False
    for source in sources:
        for match in TOKEN_PATTERN.finditer(source or ""):
            block_body, path = match.group(1), match.group(2)
            if block_body is not None:
                try:
                    spec = parse_event_block(block_body)
                except EventBlockError:
                    continue
                orders.add(spec.order)
                need_count = True
                continue
            parts = (path or "").strip().split(".")
            if not parts or parts[0] != "events":
                continue
            if parts[1:2] == ["count"]:
                need_count = True
            elif parts[1:2] == ["latest"]:
                need_latest = True
            elif parts[1:2] == ["first"]:
                need_first = True
    return EventUsage(
        orders=frozenset(orders),
        need_latest=need_latest,
        need_first=need_first,
        need_count=need_count,
    )


def event_row(event: Any, level_names: Mapping[str, str]) -> dict[str, Any]:
    """把 Event 实例转成模板可用的纯数据行；不包含 raw_data。"""
    raw_level = str(getattr(event, "level", "") or "")
    source = getattr(event, "source", None)
    row: dict[str, Any] = {
        "level": level_names.get(raw_level, raw_level),
        "source_name": getattr(source, "name", "") or "",
    }
    for field in EVENT_SCALAR_FIELDS:
        if field in row:
            continue
        row[field] = getattr(event, field, None)
    row["tags"] = getattr(event, "tags", None) or {}
    row["labels"] = getattr(event, "labels", None) or {}
    row["enrichment"] = getattr(event, "enrichment", None) or {}
    return row


def resolve_event_value(row: Mapping[str, Any], path: str) -> Any:
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def cell_text(value: Any) -> str:
    if value is None or value == "":
        return MISSING_VALUE
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, datetime):
        text = value.isoformat(sep=" ", timespec="seconds")
    elif isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    else:
        text = str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    if len(text) > MAX_CELL_LENGTH:
        text = text[:MAX_CELL_LENGTH] + "…"
    return text


def _sort_rows(rows: Sequence[Mapping[str, Any]], order: str) -> list[Mapping[str, Any]]:
    field = order.lstrip("-")
    reverse = order.startswith("-")

    def sort_key(row: Mapping[str, Any]) -> str:
        value = row.get(field)
        if value in (None, ""):
            return ""
        return cell_text(value)

    return sorted(rows, key=sort_key, reverse=reverse)


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if "\u2e80" <= char <= "\ufaff" or char in "—｜" else 1
    return width


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _html_table(headers, rows, footer, escape):
    head = "".join(
        f'<th style="padding:6px 8px;border:1px solid #e5e7eb;background:#f5f7fa;text-align:left;">{escape(header)}</th>' for header in headers
    )
    body = "".join(
        "<tr>" + "".join(f'<td style="padding:6px 8px;border:1px solid #e5e7eb;">{escape(cell)}</td>' for cell in row) + "</tr>" for row in rows
    )
    table = f'<table style="width:100%;border-collapse:collapse;font-size:13px;"><tr>{head}</tr>{body}</table>'
    if footer:
        table += f'<p style="margin:6px 0 0;color:#6b7280;font-size:12px;">{escape(footer)}</p>'
    return table


def _html_list(headers, rows, footer, escape):
    items = "".join("<li>" + "；".join(f"{escape(headers[index])}: {escape(cell)}" for index, cell in enumerate(row)) + "</li>" for row in rows)
    output = f'<ul style="margin:0;padding-left:18px;font-size:13px;">{items}</ul>'
    if footer:
        output += f'<p style="margin:6px 0 0;color:#6b7280;font-size:12px;">{escape(footer)}</p>'
    return output


def _markdown_list(headers, rows, footer, escape):
    lines = ["- " + " | ".join(f"{escape(headers[index])}: {escape(cell)}" for index, cell in enumerate(row)) for row in rows]
    if footer:
        lines.extend(["", f"> {escape(footer)}"])
    return "\n".join(lines)


def _markdown_table(headers, rows, footer, escape):
    lines = ["| " + " | ".join(escape(header) for header in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(escape(cell) for cell in row) + " |")
    if footer:
        lines.extend(["", f"> {escape(footer)}"])
    return "\n".join(lines)


def _text_table(headers, rows, footer, _escape):
    widths = [
        max(_display_width(header), *(_display_width(row[index]) for row in rows)) if rows else _display_width(header)
        for index, header in enumerate(headers)
    ]
    lines = [" | ".join(_pad(header, widths[index]) for index, header in enumerate(headers))]
    for row in rows:
        lines.append(" | ".join(_pad(cell, widths[index]) for index, cell in enumerate(row)))
    if footer:
        lines.extend(["", footer])
    return "\n".join(lines)


def _text_list(headers, rows, footer, _escape):
    lines = ["- " + " | ".join(f"{headers[index]}: {cell}" for index, cell in enumerate(row)) for row in rows]
    if footer:
        lines.extend(["", footer])
    return "\n".join(lines)


_RENDERERS = {
    ("html", "table"): _html_table,
    ("html", "list"): _html_list,
    ("markdown", "table"): _markdown_table,
    ("markdown", "list"): _markdown_list,
    ("text", "table"): _text_table,
    ("text", "list"): _text_list,
}


def resolve_format(spec: EventBlockSpec, family: str) -> str:
    """未显式声明时按渠道选默认形态；Markdown 渠道不支持表格，默认出列表。"""
    if spec.fmt:
        return spec.fmt
    return "list" if family == "markdown" else "table"


def _ordered_rows(spec: EventBlockSpec, events_context: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], int]:
    grouped = events_context.get("rows_by_order") or {}
    if spec.order in grouped:
        ordered = list(grouped[spec.order])
    else:
        ordered = _sort_rows(events_context.get("rows") or [], spec.order)
    total = int(events_context.get("count") or 0)
    limit = MAX_EVENT_ROWS if spec.limit is None else spec.limit
    return ordered[:limit], total


def render_event_block(
    spec: EventBlockSpec,
    events_context: Mapping[str, Any],
    *,
    family: str,
    escape: Callable[[str], str],
    max_bytes: int | None = None,
) -> str:
    picked, total = _ordered_rows(spec, events_context)
    if not picked:
        text = escape(spec.empty)
        if max_bytes is not None and len(text.encode("utf-8")) > max_bytes:
            raise EventBlockBudgetError("模板渲染结果不能超过 256KB")
        return text

    headers = [column.label for column in spec.columns]
    rows = [[cell_text(resolve_event_value(row, column.path)) for column in spec.columns] for row in picked]
    renderer = _RENDERERS[(family, resolve_format(spec, family))]
    chosen = len(rows)
    while chosen >= 1:
        shown = rows[:chosen]
        footer = f"共 {total} 条，已展示前 {chosen} 条" if total > chosen else ""
        text = renderer(headers, shown, footer, escape)
        if max_bytes is None or len(text.encode("utf-8")) <= max_bytes:
            return text
        chosen -= 1
    raise EventBlockBudgetError("模板渲染结果不能超过 256KB")
