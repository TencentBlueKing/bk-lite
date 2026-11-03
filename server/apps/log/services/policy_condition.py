"""条件归一、stats 别名与 LogsQL 片段。

序列化写入与扫描读取都经过这里。本模块不记录用户输入或查询正文。
"""

import math

from apps.log.constants.alert_policy import AlertConstants

_COUNT_STATS_FUNCS = frozenset({"count", "count_rate"})


def normalize_condition(condition):
    """count_delta 归一为 count + delta + previous_window，并补缺省 compare / params。"""
    if not isinstance(condition, dict):
        return {}
    normalized = dict(condition)
    compare = normalized.get("compare")
    if isinstance(compare, dict):
        normalized["compare"] = dict(compare)
    params = normalized.get("params")
    if isinstance(params, dict):
        normalized["params"] = dict(params)

    if normalized.get("func") == "count_delta":
        normalized["func"] = "count"
        normalized["field"] = "_msg"
        normalized["compare"] = {"kind": "delta", "to": "previous_window"}

    compare = normalized.get("compare")
    if not isinstance(compare, dict) or not compare.get("kind"):
        normalized["compare"] = {"kind": "absolute"}
    else:
        compare = dict(compare)
        legacy = AlertConstants.COMPARE_LEGACY_OFFSETS.get(compare.get("to"))
        if legacy:
            compare["to"], compare["offset"] = legacy
        if compare.get("to") == "previous_window":
            compare.pop("offset", None)
        normalized["compare"] = compare
    if not isinstance(normalized.get("params"), dict):
        normalized["params"] = {}
    if normalized.get("func") in ("count_rate", "bytes_rate", "ratio") and not normalized.get("field"):
        normalized["field"] = "_msg"
    return normalized


def level_rank(level):
    """未知级别与空值记 0，低于 warning。不读策略对象。"""
    if level in (None, ""):
        return 0
    return AlertConstants.LEVEL_RANK.get(str(level).strip().lower(), 0)


def condition_thresholds(condition, default_level):
    """显式 thresholds 原样留下合法档；没有该字段时合成一档，级别由调用方传入。"""
    if not isinstance(condition, dict):
        return []
    raw = condition.get("thresholds")
    if isinstance(raw, list):
        steps = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            level = item.get("level")
            if level not in AlertConstants.LEVEL_RANK:
                continue
            steps.append({"level": level, "value": item.get("value")})
        return steps
    return [{"level": default_level, "value": condition.get("value")}]


def condition_role(condition):
    """缺省、空字符串和旧数据都是常规条件。未知值原样返回，交给校验拒绝。"""
    if not isinstance(condition, dict):
        return "regular"
    role = condition.get("role")
    if role in (None, "", "regular"):
        return "regular"
    return role


def highest_hit_level(value, op, thresholds, compare):
    """同一个数按同一运算符逐档比较，命中档取最高。未命中返回 None。"""
    if value is None or not op or compare is None:
        return None
    best = None
    best_rank = 0
    for step in thresholds or []:
        if not isinstance(step, dict):
            continue
        level = step.get("level")
        rank = AlertConstants.LEVEL_RANK.get(level, 0)
        if rank <= 0 or step.get("value") is None:
            continue
        if not compare(value, op, step.get("value")):
            continue
        if best is None or rank > best_rank:
            best = level
            best_rank = rank
    return best


def combine_levels(levels, mode):
    """and 取最轻，or 取最高。空或未知模式返回 None。"""
    usable = [level for level in levels or [] if level in AlertConstants.LEVEL_RANK]
    if not usable or mode not in ("and", "or"):
        return None
    pick = min if mode == "and" else max
    return pick(usable, key=lambda level: AlertConstants.LEVEL_RANK[level])


def highest_enabled_level(conditions, fallback=None):
    """条件里启用的最高档。没有阶梯时回落到 fallback（须是三档之一）。"""
    best = None
    best_rank = 0
    saw = False
    for condition in conditions or []:
        if not isinstance(condition, dict) or condition_role(condition) == "guard":
            continue
        raw = condition.get("thresholds")
        if isinstance(raw, list) and raw:
            levels = [item.get("level") for item in raw if isinstance(item, dict)]
        elif fallback in AlertConstants.LEVEL_RANK:
            levels = [fallback]
        else:
            continue
        for level in levels:
            rank = AlertConstants.LEVEL_RANK.get(level, 0)
            if rank > best_rank:
                best = level
                best_rank = rank
                saw = True
    if saw:
        return best
    return fallback if fallback in AlertConstants.LEVEL_RANK else None


def condition_alias(condition, index=0):
    """aggregate_result 键。quantile 带分位，ratio 用条件序号，字段中的点换成下划线。"""
    normalized = normalize_condition(condition)
    func = normalized.get("func") or ""
    field = _field_token(normalized.get("field"))
    if func == "quantile":
        return f"quantile_{_quantile_token((normalized.get('params') or {}).get('quantile'))}_{field}"
    if func == "ratio":
        return f"ratio_{index}"
    if func == "count_rate":
        return "count_rate"
    if func == "bytes_rate":
        return "bytes_rate"
    if func == "count":
        return f"count_{field}"
    return f"{func}_{field}"


def stats_alias(condition, index=0):
    """LogsQL `as` 别名。速率 / 字节速率 / 占比的统计列与结果键不同。"""
    normalized = normalize_condition(condition)
    func = normalized.get("func") or ""
    field = "_msg" if func in ("count_rate", "bytes_rate", "ratio") else normalized.get("field")
    token = _field_token(field)
    if func in _COUNT_STATS_FUNCS or func == "count_delta":
        return f"count_{token}"
    if func == "bytes_rate":
        return "bytes__msg"
    if func == "ratio":
        return f"ratio_{index}_hit"
    if func == "quantile":
        return condition_alias(normalized, index)
    return f"{func}_{token}"


def stats_expression(condition, index, filter_mapper):
    """返回一条 stats 函数片段。无法表达时返回 None。"""
    if not isinstance(condition, dict) or not condition.get("func"):
        return None
    normalized = normalize_condition(condition)
    func = normalized.get("func")
    field = normalized.get("field") or "_msg"
    alias = stats_alias(normalized, index)
    if func in _COUNT_STATS_FUNCS:
        return f"count() as {alias}"
    if func == "sum":
        return f"sum({field}) as {alias}"
    if func == "avg":
        return f"avg({field}) as {alias}"
    if func == "max":
        return f"max({field}) as {alias}"
    if func == "min":
        return f"min({field}) as {alias}"
    if func == "count_uniq":
        return f"count_uniq({field}) limit {AlertConstants.COUNT_UNIQ_LIMIT} as {alias}"
    if func == "quantile":
        quantile = _canonical_quantile((normalized.get("params") or {}).get("quantile"))
        if quantile is None:
            return None
        return f"quantile({_format_quantile(quantile)}, {field}) as {alias}"
    if func == "bytes_rate":
        return "sum_len(_msg) as bytes__msg"
    if func == "ratio":
        raw_filter = (normalized.get("params") or {}).get("filter") or ""
        mapped = raw_filter
        if filter_mapper is not None:
            mapped = filter_mapper(raw_filter)
        return f"count() if (({mapped})) as ratio_{index}_hit"
    return None


def collect_stats_expressions(conditions, filter_mapper):
    """按条件生成 stats 片段并去重。占比额外保证 count() as count__msg 出现一次。"""
    expressions = []
    needs_message_count = False
    for index, condition in enumerate(conditions or []):
        if not isinstance(condition, dict):
            continue
        expression = stats_expression(condition, index, filter_mapper)
        if expression:
            expressions.append(expression)
        if normalize_condition(condition).get("func") == "ratio":
            needs_message_count = True
    if needs_message_count:
        expressions.append("count() as count__msg")
    return list(dict.fromkeys(expressions))


def parse_metric(raw, *, as_int=False):
    """有限数值；空、NaN、非数值返回 None。不记录原值。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str(raw).strip()
        if not text or text.lower() in {"nan", "inf", "-inf", "+inf", "none"}:
            return None
        try:
            number = float(text)
        except (TypeError, ValueError):
            return None
    if not math.isfinite(number):
        return None
    if as_int:
        return int(number)
    return number


def canonical_quantile(raw):
    return _canonical_quantile(raw)


def uses_previous_count_delta(condition):
    """旧 count_delta，以及归一后的 count + delta + previous_window。"""
    normalized = normalize_condition(condition)
    compare = normalized.get("compare") or {}
    return normalized.get("func") == "count" and compare.get("kind") == "delta" and compare.get("to") == "previous_window"


def custom_offset_seconds(compare_to):
    """offset_hours:N / offset_days:N 换成秒。非法键返回 None。"""
    if not isinstance(compare_to, str) or ":" not in compare_to:
        return None
    family, _, raw = compare_to.partition(":")
    try:
        amount = int(raw)
    except ValueError:
        return None
    if family == "offset_hours" and 1 <= amount <= AlertConstants.MAX_COMPARE_OFFSET_HOURS:
        return amount * 3600
    if family == "offset_days" and 1 <= amount <= AlertConstants.MAX_COMPARE_OFFSET_DAYS:
        return amount * 86400
    return None


def baseline_key(compare):
    """对照查询的键。自定义小时 / 天数带上数量，避免不同偏移共用一次查询。"""
    if not isinstance(compare, dict):
        return None
    target = compare.get("to")
    if target in ("offset_hours", "offset_days"):
        offset = compare.get("offset")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 1:
            return None
        return f"{target}:{offset}"
    return target or None


def compare_targets(conditions):
    """条件里出现的对照时段，按出现顺序去重。绝对值不占查询。"""
    targets = []
    for condition in conditions or []:
        if not isinstance(condition, dict):
            continue
        compare = normalize_condition(condition).get("compare") or {}
        kind = compare.get("kind")
        target = baseline_key(compare)
        if kind in (None, "absolute") or not target or target in targets:
            continue
        targets.append(target)
    return targets


def _field_token(field):
    text = "_msg" if field in (None, "") else str(field)
    return text.replace(".", "_")


def _canonical_quantile(raw):
    if isinstance(raw, bool):
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    for choice in AlertConstants.QUANTILE_CHOICES:
        if math.isclose(number, choice, rel_tol=0, abs_tol=1e-9):
            return choice
    return None


def _quantile_token(raw):
    quantile = _canonical_quantile(raw)
    if quantile is None:
        return "invalid"
    return _format_quantile(quantile).replace(".", "_")


def _format_quantile(number):
    return format(number, "g")
