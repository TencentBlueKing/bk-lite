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


def format_hit_line(aggregate_result):
    if not isinstance(aggregate_result, dict) or aggregate_result.get("count") is None:
        return ""
    text = f"命中条数：{aggregate_result['count']}"
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


def format_aggregate_notice(event_obj, policy, raw_data, jump_query, *, base_url, sample_limit=10, text_limit=200):
    """含 aggregate_result 时的通知正文。调用方保证 raw_data 是聚合字典。"""
    aggregate_result = raw_data.get("aggregate_result") if isinstance(raw_data, dict) else {}
    lines = [
        f"时间：{event_obj.event_time}",
        f"告警内容：{event_obj.content}",
        f"策略名称：{policy.name}",
    ]
    hit_line = format_hit_line(aggregate_result)
    if hit_line:
        lines.append(hit_line)
    if isinstance(jump_query, dict) and jump_query.get("window_start") is not None and jump_query.get("window_end") is not None:
        lines.append(f"检测窗口：{format_window_text(jump_query['window_start'], jump_query['window_end'])}")
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
