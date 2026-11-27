"""把主机进程采集编码成严格的 Influx 行协议。

进程行比普通指标多两条业务规则：pid 必须是数字，name 不能空。
转义和拼行交给 influx_line，避免再维护一套 tag 转义。
"""

import re

from core.collection.influx_line import encode_influx_line, log_dropped_influx_line, normalize_tag_text, parse_influx_line

_TAG_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\Z")
_TEXT_LIMITS = {
    "arg": 1024,
    "ports": 1024,
    "exe": 512,
    "cwd": 512,
    "name": 512,
    "pid": 32,
}
_DEFAULT_TEXT_LIMIT = 255
_MEASUREMENT = "host_proc_usage_info"


def cleaned_host_proc_labels(labels):
    """去掉进程标签里的控制字符。pid 或 name 不合法时返回 None。"""
    if not isinstance(labels, dict):
        return None
    cleaned = {}
    for key, value in labels.items():
        tag_key = str(key)
        if tag_key == "gauge" or tag_key.startswith("_") or _TAG_KEY.fullmatch(tag_key) is None:
            continue
        if value is None or isinstance(value, (list, dict)):
            continue
        text = normalize_tag_text(value, _TEXT_LIMITS.get(tag_key, _DEFAULT_TEXT_LIMIT))
        if text:
            cleaned[tag_key] = text
    if not cleaned.get("pid", "").isdigit() or not cleaned.get("name"):
        return None
    return cleaned


def host_proc_line(labels, timestamp_ns):
    """返回一条进程指标。pid、name 或时间戳不合法时返回 None。"""
    cleaned = cleaned_host_proc_labels(labels)
    if cleaned is None:
        source = labels if isinstance(labels, dict) else {}
        log_dropped_influx_line(_MEASUREMENT, source, "invalid_process", level="debug")
        return None
    if timestamp_ns is None:
        log_dropped_influx_line(_MEASUREMENT, cleaned, "missing_timestamp", level="debug")
        return None
    cleaned["model_id"] = "host_proc_usage"
    line = encode_influx_line(_MEASUREMENT, cleaned, "gauge", 1, int(timestamp_ns))
    if line is None:
        return None
    parsed = parse_influx_line(line)
    if parsed is None or parsed[2] != "gauge=1i" or parsed[3] is None:
        log_dropped_influx_line(_MEASUREMENT, cleaned, "invalid_line")
        return None
    return line
