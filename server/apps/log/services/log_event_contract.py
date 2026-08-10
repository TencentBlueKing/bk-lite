"""日志正文契约。

采集、传输和提取阶段只使用 ``message``。VictoriaLogs 的 ``_msg`` 是存储实现
细节，只能在最终写入适配器中通过移动语义产生。
"""

import json
from typing import Any

LOGICAL_MESSAGE_FIELD = "message"
STORAGE_MESSAGE_FIELD = "_msg"
LEGACY_MESSAGE_FIELDS = ("_msg", "log_message", "raw_message", "trap_message")


NORMALIZE_EVENT_VRL = r'''
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
