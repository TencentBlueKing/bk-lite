"""告警通知正文与告警中心载荷里的样本、检索链接。不记录查询正文。"""

from datetime import datetime, timezone
from urllib.parse import urlencode


def flatten_sample_text(value, limit=200):
    """样本单行，超长截断并加省略号。"""
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def sample_message(item):
    if isinstance(item, dict):
        message = item.get("message")
        if message in (None, ""):
            message = item.get("_msg")
        return message
    return None


def truncate_samples(items, *, sample_limit=10, text_limit=200):
    rows = []
    for item in items or []:
        message = sample_message(item)
        if message in (None, ""):
            continue
        rows.append(flatten_sample_text(message, text_limit))
        if len(rows) >= sample_limit:
            break
    return rows


def format_window_text(window_start, window_end):
    start_dt = datetime.fromtimestamp(int(window_start), timezone.utc)
    end_dt = datetime.fromtimestamp(int(window_end), timezone.utc)
    start_text = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    if start_dt.date() == end_dt.date():
        end_text = end_dt.strftime("%H:%M:%S")
    else:
        end_text = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    return f"{start_text} ~ {end_text}"


_FUNC_LABELS = {
    "count": "计数",
    "sum": "求和",
    "avg": "平均",
    "max": "最大",
    "min": "最小",
    "count_uniq": "去重计数",
    "count_rate": "速率",
    "bytes_rate": "字节速率",
    "ratio": "占比",
}
_TARGET_LABELS = {
    "previous_window": "上一窗",
    "offset_1h": "1 小时前",
    "offset_24h": "24 小时前",
    "offset_7d": "7 天前",
}
_LEVEL_LABELS = {"warning": "警告", "error": "错误", "critical": "严重"}
_LEVEL_ORDER = {"warning": 1, "error": 2, "critical": 3}


def _target_label(compare):
    target = compare.get("to")
    offset = compare.get("offset")
    if target == "offset_hours" and isinstance(offset, int) and not isinstance(offset, bool):
        return f"{offset} 小时前"
    if target == "offset_days" and isinstance(offset, int) and not isinstance(offset, bool):
        return f"{offset} 天前"
    return _TARGET_LABELS.get(target, target or "")


def format_hit_line(aggregate_result):
    if not isinstance(aggregate_result, dict) or aggregate_result.get("count") is None:
        return ""
    text = f"命中条数：{aggregate_result['count']}"
    conditions = aggregate_result.get("conditions")
    if isinstance(conditions, list) and conditions:
        lines = [text]
        for condition in conditions:
            rendered = format_condition_line(condition)
            if rendered:
                lines.append(rendered)
        return "\n".join(lines)
    extras = []
    rate = aggregate_result.get("count_rate")
    if "count_rate" in aggregate_result and rate is not None:
        extras.append(f"速率 {float(rate):.2f} 条/秒")
    if "count_delta" in aggregate_result and aggregate_result.get("count_delta") is not None:
        delta = aggregate_result["count_delta"]
        try:
            number = int(delta)
        except (TypeError, ValueError):
            number = delta
        signed = f"+{number}" if isinstance(number, (int, float)) and number >= 0 else str(number)
        extras.append(f"较上一窗 {signed}")
    if extras:
        text += "（" + "，".join(extras) + "）"
    return text


def format_condition_line(condition):
    """一条条件的命中行。旧聚合结果没有 conditions 时不走这里。"""
    if not isinstance(condition, dict):
        return ""
    func = condition.get("func")
    label = _condition_label(condition)
    if not label:
        return ""
    headline = condition.get("current")
    if headline is None:
        headline = condition.get("value")
    if func == "ratio":
        body = _format_ratio_value(condition.get("value"))
    elif func == "count_rate":
        body = f"{_format_metric(headline)} 条/秒"
    elif func == "bytes_rate":
        body = f"{_format_metric(headline)} 字节/秒"
    elif func == "quantile":
        body = _format_metric(headline)
    else:
        body = _format_countish(headline)
    text = f"{label}：{body}"
    clause = _threshold_clause(condition)
    if clause:
        text = f"{text} {clause}"
    compare = condition.get("compare") if isinstance(condition.get("compare"), dict) else {}
    kind = compare.get("kind") or "absolute"
    if kind in ("delta", "percent") and condition.get("baseline") is not None and condition.get("value") is not None:
        target = _target_label(compare)
        if kind == "percent":
            change = f"{float(condition['value']):+.1f}%"
        else:
            change = _signed_count(condition.get("value"))
        text += f"（较 {target} {change}，对照 {_format_countish(condition.get('baseline'))}）"
    if func == "ratio" and condition.get("hit") is not None and condition.get("total") is not None:
        text += f"（{condition['hit']} / {condition['total']}）"
    return text


def _threshold_clause(condition):
    """阶梯条件的阈值文本。旧条件没有 thresholds，正文保持原样。"""
    steps = condition.get("thresholds")
    if not isinstance(steps, list) or not steps:
        return ""
    op = condition.get("op") or ""
    level = condition.get("level")
    threshold = condition.get("threshold")
    if not level:
        usable = [step for step in steps if isinstance(step, dict) and step.get("level") in _LEVEL_ORDER]
        if not usable:
            return ""
        lightest = min(usable, key=lambda step: _LEVEL_ORDER[step["level"]])
        level = lightest.get("level")
        threshold = lightest.get("value")
    label = _LEVEL_LABELS.get(level)
    if not op or threshold is None or not label:
        return ""
    return f"{op} {_format_threshold_text(threshold)}（{label}）"


def _format_threshold_text(value):
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _ladder_level_line(aggregate_result):
    if not isinstance(aggregate_result, dict):
        return ""
    conditions = aggregate_result.get("conditions")
    if not isinstance(conditions, list):
        return ""
    if not any(isinstance(item, dict) and item.get("thresholds") for item in conditions):
        return ""
    label = _LEVEL_LABELS.get(aggregate_result.get("level"))
    if not label:
        return ""
    return f"级别：{label}"


def _condition_label(condition):
    func = condition.get("func")
    field = condition.get("field") or ""
    if func == "quantile":
        params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
        try:
            mark = int(round(float(params.get("quantile")) * 100))
        except (TypeError, ValueError):
            mark = None
        prefix = f"P{mark}" if mark is not None else "分位数"
        return f"{prefix}({field})" if field else prefix
    if func == "count_uniq":
        return f"去重计数({field})" if field else "去重计数"
    if func == "ratio":
        params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
        raw_filter = params.get("filter") or ""
        return f"占比({raw_filter})" if raw_filter else "占比"
    if func in ("count", "sum", "avg", "max", "min") and field and field != "_msg":
        return f"{_FUNC_LABELS.get(func, func)}({field})"
    return _FUNC_LABELS.get(func, "")


def _format_metric(value):
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_countish(value):
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_ratio_value(value):
    if isinstance(value, bool) or value is None:
        return ""
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return ""


def _signed_count(value):
    try:
        number = int(value) if isinstance(value, int) or (isinstance(value, float) and float(value).is_integer()) else float(value)
    except (TypeError, ValueError):
        return str(value)
    if isinstance(number, float):
        text = f"{number:.2f}"
    else:
        text = str(number)
    if isinstance(number, (int, float)) and number >= 0:
        return f"+{text}"
    return text


def search_millis(value):
    number = int(value)
    if number < 10_000_000_000:
        return number * 1000
    return number


def build_search_url(base_url, jump_query, log_groups):
    if not isinstance(jump_query, dict) or not jump_query.get("query"):
        return ""
    params = [
        ("query", jump_query.get("query")),
        ("startTime", str(search_millis(jump_query.get("window_start")))),
        ("endTime", str(search_millis(jump_query.get("window_end")))),
    ]
    for group in log_groups or []:
        if group in (None, ""):
            continue
        params.append(("log_groups", str(group)))
    return f"{base_url}/log/search?{urlencode(params)}"


def _previous_window_count(aggregate_result):
    baseline = aggregate_result.get("baseline") if isinstance(aggregate_result.get("baseline"), dict) else {}
    values = baseline.get("values") if isinstance(baseline.get("values"), dict) else {}
    raw = values.get("count__msg", values.get("count", 0))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def format_aggregate_notice(event_obj, policy, raw_data, jump_query, *, base_url, sample_limit=10, text_limit=200):
    """含 aggregate_result 时的通知正文。调用方保证 raw_data 是聚合字典。"""
    aggregate_result = raw_data.get("aggregate_result") if isinstance(raw_data, dict) else {}
    no_data = isinstance(aggregate_result, dict) and aggregate_result.get("no_data") is True
    lines = [f"时间：{event_obj.event_time}"]
    if no_data:
        lines.append(f"本窗无日志，上一窗 {_previous_window_count(aggregate_result)} 条")
    lines.extend(
        [
            f"告警内容：{event_obj.content}",
        ]
    )
    level_line = _ladder_level_line(aggregate_result)
    if level_line:
        lines.append(level_line)
    lines.append(f"策略名称：{policy.name}")
    if not no_data:
        hit_line = format_hit_line(aggregate_result)
        if hit_line:
            lines.append(hit_line)
    if isinstance(jump_query, dict) and jump_query.get("window_start") is not None and jump_query.get("window_end") is not None:
        lines.append(f"检测窗口：{format_window_text(jump_query['window_start'], jump_query['window_end'])}")
    if not no_data:
        samples = truncate_samples(
            raw_data.get("samples") if isinstance(raw_data, dict) else [],
            sample_limit=sample_limit,
            text_limit=text_limit,
        )
        if samples:
            lines.append("样本（最多 10 条）：")
            lines.extend(f"  - {line}" for line in samples)
    search_url = build_search_url(base_url, jump_query, getattr(policy, "log_groups", None))
    if search_url:
        lines.append(f'查看命中日志：<a href="{search_url}">点击查看</a>')
    detail_url = f"{base_url}/log/event/alert"
    lines.append(f'查看告警详情：<a href="{detail_url}">点击查看详情</a>')
    return "【日志告警通知】", "\n".join(lines)


def _raw_data_for_event(event):
    raw = getattr(event, "raw_data", None)
    if raw is not None:
        return raw
    from apps.log.models.policy import EventRawData

    manager = getattr(EventRawData, "objects", None)
    event_id = getattr(event, "id", None)
    if manager is None or not event_id:
        return None
    row = manager.filter(event_id=event_id).order_by("-id").first()
    if row is None:
        return None
    return getattr(row, "data", None)


def _jump_query_for_event(event, raw):
    if isinstance(raw, dict) and isinstance(raw.get("jump_query"), dict):
        return raw.get("jump_query")
    from apps.log.models.policy import AlertSnapshot

    manager = getattr(AlertSnapshot, "objects", None)
    alert_id = getattr(event, "alert_id", None)
    if not alert_id:
        alert = getattr(event, "alert", None)
        alert_id = getattr(alert, "id", None)
    if manager is None or not alert_id:
        return None
    snapshot = manager.filter(alert_id=alert_id).first()
    items = getattr(snapshot, "snapshots", None) or []
    event_id = getattr(event, "id", None)
    fallback = None
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("jump_query"), dict):
            continue
        fallback = item.get("jump_query")
        if event_id and item.get("event_id") == event_id:
            return item.get("jump_query")
    return fallback


def notice_context(event, policy, *, base_url="", sample_limit=10, text_limit=200):
    """读取样本、聚合结果和冻结查询。读失败时返回空上下文，不抛出。"""
    try:
        raw = _raw_data_for_event(event)
        jump_query = _jump_query_for_event(event, raw)
    except Exception:
        raw = None
        jump_query = None
    aggregate_result = None
    sample_source = []
    if isinstance(raw, dict):
        if isinstance(raw.get("aggregate_result"), dict):
            aggregate_result = raw.get("aggregate_result")
        if isinstance(raw.get("samples"), list):
            sample_source = raw.get("samples")
    elif isinstance(raw, list):
        sample_source = raw
    jump = jump_query if isinstance(jump_query, dict) else None
    return {
        "raw": raw if isinstance(raw, dict) else None,
        "aggregate_result": aggregate_result,
        "samples": truncate_samples(sample_source, sample_limit=sample_limit, text_limit=text_limit),
        "jump_query": jump,
        "search_url": build_search_url(base_url, jump, getattr(policy, "log_groups", None)),
    }
