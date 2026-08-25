"""日志正文契约。

采集、传输和提取阶段只使用 ``message``。VictoriaLogs 的 ``_msg`` 是存储实现
细节，只能在最终写入适配器中通过移动语义产生。
"""

import json
import re
from typing import Any

LOGICAL_MESSAGE_FIELD = "message"
STORAGE_MESSAGE_FIELD = "_msg"
LEGACY_MESSAGE_FIELDS = ("_msg", "log_message", "raw_message", "trap_message")
# VictoriaLogs 内部字段不能当成普通 field:value 过滤器；检索侧用 timestamp / message。
HIDDEN_LOGICAL_FIELDS = frozenset({"@timestamp", "_stream", "_stream_id", "_time"})
# _stream / _stream_id / _time 的值不能是 *，空的 field: 也不能补成 exists 过滤。
SPECIAL_LOGSQL_FIELDS = frozenset({"_stream", "_stream_id", "_time"})
SIMPLE_LOGSQL_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
UNQUOTED_LOGSQL_FIELD = re.compile(r"[A-Za-z_@][A-Za-z0-9_.@/-]*")
LOGSQL_VALUE_BOUNDARY = re.compile(r"^(?:AND|OR)(?:\s|$|\|)", re.IGNORECASE)


NORMALIZE_TIMESTAMP_VRL = r'''
# timestamp 只表示中心系统 Vector 从 Server NATS 消费到事件的时间。
# 上游时间保持原值移动到 collect_timestamp；已经归一化过的事件保留最早的采集时间。
# NATS source 开启 namespace 后元数据不再混入负载；只显式恢复已有的可检索来源字段。
if exists(%vector.source_type) { .source_type = %vector.source_type }
if exists(%nats.subject) { .subject = %nats.subject }
if exists(.timestamp) {
  if !exists(.collect_timestamp) {
    .collect_timestamp = del(.timestamp)
  } else {
    del(.timestamp)
  }
}
.timestamp = now()
'''.strip()


NORMALIZE_MESSAGE_VRL = r'''
# 混合版本兼容：SNMP 的 trap_message 是去掉 syslog 头后的正文，优先于旧 raw message。
_collect_type = if exists(.collect_type) && is_string(.collect_type) { string!(.collect_type) } else { "" }
if _collect_type == "snmp_trap" && exists(.trap_message) && !is_null(.trap_message) {
  .message = del(.trap_message)
}

# 旧 Beat 配置曾直接生成 _msg。仅当标准正文缺失时移动，绝不保留两份。
_message_missing = !exists(.message) || is_null(.message)
if !_message_missing && is_string(.message) {
  _message_missing = string!(.message) == ""
}
if _message_missing && exists(._msg) && !is_null(._msg) {
  .message = del(._msg)
}

# 结构化遥测没有天然正文时生成短摘要，禁止序列化整个事件。
_message_missing = !exists(.message) || is_null(.message)
if !_message_missing && is_string(.message) {
  _message_missing = string!(.message) == ""
}
if _message_missing {
  if _collect_type == "http" {
    .message = "Packetbeat HTTP event"
  } else if _collect_type == "flows" {
    .message = "Packetbeat network flow"
  } else if _collect_type == "file_integrity" {
    .message = "Auditbeat file integrity event"
  } else {
    .message = "Log event without message"
  }
}

if !is_string(.message) {
  .message = encode_json(.message)
}

# 已知旧正文字段在归一化后必须消失。
del(._msg)
del(.log_message)
del(.raw_message)
del(.trap_message)
'''.strip()


# 系统 Vector 的平台归一化模块由互不覆盖字段的内部片段组成；对配置编译器仍只暴露
# 一个稳定接口和一个 normalize_event transform。
NORMALIZE_EVENT_VRL = "\n\n".join((NORMALIZE_TIMESTAMP_VRL, NORMALIZE_MESSAGE_VRL))


PREPARE_VICTORIA_LOGS_VRL = r'''
# VictoriaLogs 物理主消息只在存储适配器内存在；del 保证不是复制。
._msg = del(.message)
'''.strip()


def to_storage_field(field: str) -> str:
    """把公开逻辑字段转换为 VictoriaLogs 物理字段。"""
    return STORAGE_MESSAGE_FIELD if field == LOGICAL_MESSAGE_FIELD else field


def to_logical_field(field: str) -> str:
    """隐藏 VictoriaLogs 物理字段名。"""
    return LOGICAL_MESSAGE_FIELD if field == STORAGE_MESSAGE_FIELD else field


def to_public_logical_field(field: str) -> str | None:
    """转换成可展示/可检索的逻辑字段；内部字段返回 None。"""
    logical = to_logical_field(field)
    if logical in HIDDEN_LOGICAL_FIELDS:
        return None
    return logical


def quote_logsql_field(field: str) -> str:
    """把字段名编码成 LogsQL 过滤器左侧。"""
    if SIMPLE_LOGSQL_FIELD.fullmatch(field):
        return field
    return json.dumps(field, ensure_ascii=False)


def _empty_logsql_field_value(query: str, index: int) -> bool:
    while index < len(query) and query[index].isspace():
        index += 1
    if index >= len(query):
        return True
    current = query[index]
    if current in "|)":
        return True
    return LOGSQL_VALUE_BOUNDARY.match(query[index:]) is not None


def normalize_user_logsql_query(query: str) -> str:
    """补全空的 field: 过滤器，并给 @metadata.beat 这类字段名加引号。"""
    if not isinstance(query, str) or not query:
        return query

    result: list[str] = []
    index = 0
    quote = None
    escaped = False
    while index < len(query):
        current = query[index]
        if quote is not None:
            result.append(current)
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == quote:
                quote = None
            index += 1
            continue

        if current in {'"', "'", "`"}:
            quote_start = index
            quote = current
            result.append(current)
            index += 1
            while index < len(query):
                char = query[index]
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                    index += 1
                    break
                index += 1
            else:
                continue
            next_index = index
            while next_index < len(query) and query[next_index].isspace():
                result.append(query[next_index])
                next_index += 1
            if next_index < len(query) and query[next_index] == ":":
                quoted_field = query[quote_start + 1 : index - 1]
                result.append(":")
                index = next_index + 1
                if quoted_field not in SPECIAL_LOGSQL_FIELDS and _empty_logsql_field_value(
                    query, index
                ):
                    result.append("*")
            else:
                index = next_index
            continue

        match = UNQUOTED_LOGSQL_FIELD.match(query, index)
        if match:
            field = match.group(0)
            token_end = match.end()
            next_index = token_end
            while next_index < len(query) and query[next_index].isspace():
                next_index += 1
            if next_index < len(query) and query[next_index] == ":":
                result.append(quote_logsql_field(field))
                if token_end < next_index:
                    result.append(query[token_end:next_index])
                result.append(":")
                index = next_index + 1
                if field not in SPECIAL_LOGSQL_FIELDS and _empty_logsql_field_value(query, index):
                    result.append("*")
                continue

        result.append(current)
        index += 1
    return "".join(result)


def to_logical_event(event: Any) -> Any:
    """把 VictoriaLogs 查询结果转换为公开事件，且不保留第二份正文。"""
    if not isinstance(event, dict):
        return event
    normalized = dict(event)
    storage_message = normalized.pop(STORAGE_MESSAGE_FIELD, None)
    trap_message = normalized.pop("trap_message", None)
    normalized.pop("log_message", None)
    normalized.pop("raw_message", None)
    if normalized.get("collect_type") == "snmp_trap" and trap_message is not None:
        normalized[LOGICAL_MESSAGE_FIELD] = trap_message
    elif normalized.get(LOGICAL_MESSAGE_FIELD) is None and storage_message is not None:
        normalized[LOGICAL_MESSAGE_FIELD] = storage_message
    return normalized


def to_logical_json_line(line: str) -> str:
    """转换 VictoriaLogs NDJSON 行；非 JSON 内容原样返回。"""
    try:
        event = json.loads(line)
    except (TypeError, json.JSONDecodeError):
        return line
    if not isinstance(event, dict):
        return line
    return json.dumps(to_logical_event(event), ensure_ascii=False, separators=(",", ":"))


def to_storage_query(query: str) -> str:
    """把 LogSQL 中的顶层 ``message`` 字段引用映射到物理字段。

    处理字段过滤、``extract ... from message`` 与 ``fields message``，避免改写全文
    关键字、字符串值和 ``nginx.error.message`` 等结构化属性。
    """
    if not isinstance(query, str) or "message" not in query:
        return query

    result: list[str] = []
    index = 0
    segment_start = 0
    quote = None
    escaped = False
    while index < len(query):
        current = query[index]
        if quote is not None:
            result.append(current)
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == quote:
                quote = None
            index += 1
            continue

        if current in {'"', "'", "`"}:
            quote = current
            result.append(current)
            index += 1
            continue

        if current == "|":
            segment_start = index + 1
            result.append(current)
            index += 1
            continue

        token = "message"
        if query.startswith(token, index):
            previous = query[index - 1] if index else ""
            token_end = index + len(token)
            next_index = token_end
            while next_index < len(query) and query[next_index].isspace():
                next_index += 1
            left_boundary = not previous or not (previous.isalnum() or previous in "_.")
            right = query[token_end] if token_end < len(query) else ""
            right_boundary = not right or not (right.isalnum() or right in "_.")
            segment_prefix = query[segment_start:index].strip().lower()
            field_filter = next_index < len(query) and query[next_index] == ":"
            extract_source = segment_prefix == "from" or segment_prefix.endswith(" from")
            fields_operand = segment_prefix == "fields" or segment_prefix.startswith("fields ")
            if left_boundary and right_boundary and (field_filter or extract_source or fields_operand):
                result.append(STORAGE_MESSAGE_FIELD)
                index = token_end
                continue

        result.append(current)
        index += 1
    return "".join(result)
