"""把主机进程采集编码成严格的 Influx 行协议。

influxdb_client.Point 的 tag 转义不处理反斜杠，值以 \\ 结尾时还会补一个未转义空格。
进程命令行、Windows 路径里这两种情况都很常见，写进 VictoriaMetrics 后会把同一
instance 的主机监控查询打坏。这里只接受合法 tag，非法进程行直接丢掉。
"""

import re

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
_VALID_ESCAPES = {" ", ",", "=", "\\"}


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
        text = _normalize_text(value, _TEXT_LIMITS.get(tag_key, _DEFAULT_TEXT_LIMIT))
        if text:
            cleaned[tag_key] = text
    if not cleaned.get("pid", "").isdigit() or not cleaned.get("name"):
        return None
    return cleaned


def host_proc_line(labels, timestamp_ns):
    """返回一条进程指标；pid 或 name 不合法时返回 None。"""
    cleaned = cleaned_host_proc_labels(labels)
    if cleaned is None:
        return None
    cleaned["model_id"] = "host_proc_usage"
    tag_set = ",".join(f"{key}={_escape_tag(cleaned[key])}" for key in sorted(cleaned))
    if timestamp_ns is None:
        line = f"{_MEASUREMENT},{tag_set} gauge=1i"
    else:
        line = f"{_MEASUREMENT},{tag_set} gauge=1i {int(timestamp_ns)}"
    if not _is_strict_line(line):
        return None
    return line


def _normalize_text(value, limit):
    text = str(value).encode("utf-8", errors="replace").decode("utf-8")
    for char in ("\r", "\n", "\t", "\u2028", "\u2029", "\u0085"):
        text = text.replace(char, " ")
    text = "".join(char for char in text if ord(char) >= 32 and char != "\x7f")
    return text.strip()[:limit]


def _escape_tag(value):
    return value.replace("\\", "\\\\").replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def _is_strict_line(line):
    if not line or any(char in line for char in ("\n", "\r", "\x00")):
        return False
    try:
        index = _skip_escaped(line, 0, {",", " "})
        if index >= len(line) or line[index] != ",":
            return False
        index += 1
        while index < len(line) and line[index] != " ":
            index = _skip_escaped(line, index, {"=", ",", " "})
            if index >= len(line) or line[index] != "=":
                return False
            index = _skip_escaped(line, index + 1, {",", " "})
            if index < len(line) and line[index] == ",":
                index += 1
        if index >= len(line) or line[index] != " ":
            return False
        fields, separator, timestamp = line[index + 1 :].rpartition(" ")
        return separator == " " and fields == "gauge=1i" and timestamp.isdigit()
    except ValueError:
        return False


def _skip_escaped(line, index, stops):
    while index < len(line):
        char = line[index]
        if char == "\\":
            if index + 1 >= len(line) or line[index + 1] not in _VALID_ESCAPES:
                raise ValueError("invalid escape")
            index += 2
            continue
        if char in stops:
            return index
        if ord(char) < 32 or char == "\x7f":
            raise ValueError("control char")
        index += 1
    return index
