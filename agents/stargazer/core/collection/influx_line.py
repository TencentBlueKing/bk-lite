"""把指标编码成 Telegraf 能接受的 Influx 行协议。

配置采集和监控在写出 NATS 消息前都走这里。tag 值先去掉控制字符，
再转义反斜杠、空格、逗号和等号。洗完仍不合法的行丢掉，不带着整批一起失败。
"""

from core.logger import logger, safe_log_value

TAG_VALUE_LIMIT = 8192
_VALID_ESCAPES = {" ", ",", "=", "\\"}
_LINE_SEPARATORS = ("\r", "\n", "\t", "\u2028", "\u2029", "\u0085")


def normalize_tag_text(value, limit):
    text = str(value).encode("utf-8", errors="replace").decode("utf-8")
    for char in _LINE_SEPARATORS:
        text = text.replace(char, " ")
    text = "".join(char for char in text if ord(char) >= 32 and char != "\x7f")
    return text.strip()[:limit]


def encode_influx_line(measurement, tags, field_name, field_value, timestamp_ns, *, tag_limit=TAG_VALUE_LIMIT):
    """返回一行协议。指标名不合法，或拼完仍不是合法行时返回 None。"""
    prepared = _prepare_measurement(measurement)
    if prepared is None:
        log_dropped_influx_line(measurement, tags, "invalid_measurement")
        return None
    cleaned = []
    if isinstance(tags, dict):
        for key, value in tags.items():
            tag_key = normalize_tag_text(key, 128)
            if not tag_key or value is None:
                continue
            text = normalize_tag_text(value, tag_limit)
            if text:
                cleaned.append((tag_key, text))
    tag_set = ",".join(f"{_escape_tag(key)}={_escape_tag(value)}" for key, value in sorted(cleaned))
    head = f"{prepared},{tag_set}" if tag_set else prepared
    field = _format_field(field_name, field_value)
    if timestamp_ns is None:
        line = f"{head} {field}"
    else:
        line = f"{head} {field} {int(timestamp_ns)}"
    if parse_influx_line(line) is None:
        log_dropped_influx_line(measurement, tags, "invalid_line")
        return None
    return line


def log_dropped_influx_line(measurement, tags, reason, *, level="warning"):
    instance_id = "-"
    if isinstance(tags, dict):
        raw = tags.get("instance_id")
        if raw not in (None, ""):
            instance_id = raw
    log = logger.warning if level == "warning" else logger.debug
    log(
        "event=influx_line_dropped measurement=%s reason=%s instance_id=%s",
        _log_copy(measurement),
        reason,
        _log_copy(instance_id),
    )


def _log_copy(value):
    text = "".join(char for char in safe_log_value(value) if ord(char) >= 32 and char != "\x7f")
    return text or "-"


def parse_influx_line(line):
    """解析一行。不合法时返回 None。"""
    if not line or any(char in line for char in ("\n", "\r", "\x00")):
        return None
    try:
        measurement, index = _read_escaped(line, 0, {",", " "})
        if not measurement:
            return None
        tags = {}
        if index < len(line) and line[index] == ",":
            index += 1
            while index < len(line) and line[index] != " ":
                key, index = _read_escaped(line, index, {"=", ",", " "})
                if index >= len(line) or line[index] != "=" or not key or key in tags:
                    return None
                index += 1
                value, index = _read_escaped(line, index, {",", " "})
                tags[key] = value
                if index < len(line) and line[index] == ",":
                    index += 1
        if index >= len(line) or line[index] != " ":
            return None
        fields, timestamp = _split_field_and_time(line[index + 1 :])
        if "=" not in fields or any(ord(char) < 32 or char == "\x7f" for char in fields):
            return None
        return measurement, tags, fields, timestamp
    except ValueError:
        return None


def _prepare_measurement(measurement):
    text = str(measurement).strip()
    if not text or any(ord(char) < 32 or char == "\x7f" for char in text):
        return None
    return _escape_tag(text)


def _format_field(name, value):
    key = _escape_tag(str(name))
    if isinstance(value, bool):
        return f"{key}={str(value).lower()}"
    if isinstance(value, int):
        return f"{key}={value}i"
    if isinstance(value, float):
        rendered = str(value)
        if rendered.endswith(".0"):
            rendered = rendered[:-2]
        return f"{key}={rendered}"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def _split_field_and_time(rest):
    in_quotes = False
    escaped = False
    last_space = None
    for index, char in enumerate(rest):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quotes = not in_quotes
            continue
        if char == " " and not in_quotes:
            last_space = index
    if last_space is not None and rest[last_space + 1 :].isdigit():
        return rest[:last_space], rest[last_space + 1 :]
    return rest, None


def _escape_tag(value):
    return value.replace("\\", "\\\\").replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def _read_escaped(line, index, stops):
    chars = []
    while index < len(line):
        char = line[index]
        if char == "\\":
            if index + 1 >= len(line) or line[index + 1] not in _VALID_ESCAPES:
                raise ValueError("invalid escape")
            chars.append(line[index + 1])
            index += 2
            continue
        if char in stops or ord(char) < 32 or char == "\x7f":
            if char in stops:
                break
            raise ValueError("control char")
        chars.append(char)
        index += 1
    return "".join(chars), index
