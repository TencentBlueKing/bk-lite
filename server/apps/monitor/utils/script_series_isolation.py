"""原生 PromQL 排除脚本序列，脚本指标则收窄到本插件。

Host 点上经常没有 collect_type。排除脚本时用 unless 丢掉
collect_type="script" 的序列，没有该标签的主机序列仍保留。
不要写成 collect_type!="script"，那会把无标签的主机序列整批丢掉。
unless 加在聚合之前的原始序列上，避免「这台机器上只要有脚本在报，
整台主机就被从聚合结果里拿掉」。
"""

from __future__ import annotations

import re

_COLLECT_TYPE_RE = re.compile(r"""collect_type\s*(?:!?=~?|!=)\s*['"]""")
_RANGE_FUNC_RE = re.compile(
    r"(?P<func>rate|irate|increase|delta|idelta|deriv|"
    r"avg_over_time|min_over_time|max_over_time|sum_over_time|count_over_time|"
    r"last_over_time|stddev_over_time|stdvar_over_time|quantile_over_time|"
    r"absent_over_time|changes|resets|predict_linear)\s*"
    r"\(\s*(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)?\{(?P<body>[^{}]*)\}"
    r"(?P<range>\[[^\[\]]+\])(?P<rest>(?:\s*,[^)]*)?)\s*\)",
    re.IGNORECASE,
)
_SELECTOR_RE = re.compile(r"(?P<name>(?<![\w:.])[a-zA-Z_:][a-zA-Z0-9_:]*)?\{(?P<body>[^{}]*)\}(?P<range>\[[^\[\]]+\])?")
_HOLD = "__SCRIPT_SERIES_HOLD_{}__"
_SCRIPT_EXTRA = 'collect_type="script"'
_TLAST_RE = re.compile(
    r"tlast_over_time\(\((?P<inner>.*?)\)\[(?P<window>[^\]]+)\]\)",
    re.IGNORECASE,
)


def _has_collect_type(body: str) -> bool:
    return bool(_COLLECT_TYPE_RE.search(body or ""))


def _followed_by_unless(source: str, end: int) -> bool:
    return source[end:].lstrip().lower().startswith("unless")


def _join_body(body: str, extra: str) -> str:
    stripped = (body or "").strip().rstrip(",").strip()
    if not stripped:
        return extra
    return f"{stripped}, {extra}"


def _promql_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _tag_script_selectors(expr: str) -> str:
    def rewrite(match: re.Match) -> str:
        if _has_collect_type(match.group("body")):
            return match.group(0)
        name = match.group("name") or ""
        range_ = match.group("range") or ""
        return f"{name}{{{_join_body(match.group('body'), _SCRIPT_EXTRA)}}}{range_}"

    return _SELECTOR_RE.sub(rewrite, expr)


def isolate_status_timestamp_query(query: str) -> str:
    """状态查询先取原始样本时间，再按完整标签丢掉脚本序列。

    unless 作用在 tlast 之后、按 instance_id 聚合之前。这样没有 collect_type
    的主机序列还在，也不会因为同实例上有脚本在报就把整台主机判成可用。
    """
    from apps.monitor.utils.last_sample import last_sample_timestamp_query

    timestamp_query = last_sample_timestamp_query(query)

    def rewrite(match: re.Match) -> str:
        inner = match.group("inner")
        if _has_collect_type(inner) or _followed_by_unless(match.string, match.end()):
            return match.group(0)
        script_inner = _tag_script_selectors(inner)
        if script_inner == inner:
            return match.group(0)
        left = match.group(0)
        right = f"tlast_over_time(({script_inner})[{match.group('window')}])"
        return f"({left} unless {right})"

    return _TLAST_RE.sub(rewrite, timestamp_query)


def exclude_script_series(query: str) -> str:
    """去掉 collect_type="script" 的序列，保留没有该标签的序列。"""
    if not query or not str(query).strip():
        return query

    placeholders: list[str] = []

    def hold_range(match: re.Match) -> str:
        # 先把区间函数整段挪走，避免后面的选择器改写钻进 rate() 的参数。
        if _has_collect_type(match.group("body")) or _followed_by_unless(match.string, match.end()):
            replacement = match.group(0)
        else:
            name = match.group("name") or ""
            body = match.group("body")
            range_ = match.group("range")
            rest = match.group("rest") or ""
            func = match.group("func")
            left = f"{func}({name}{{{body}}}{range_}{rest})"
            right = f"{func}({name}{{{_join_body(body, _SCRIPT_EXTRA)}}}{range_}{rest})"
            replacement = f"({left} unless {right})"
        token = _HOLD.format(len(placeholders))
        placeholders.append(replacement)
        return token

    held = _RANGE_FUNC_RE.sub(hold_range, query)

    def rewrite_selector(match: re.Match) -> str:
        if _has_collect_type(match.group("body")) or _followed_by_unless(match.string, match.end()):
            return match.group(0)
        name = match.group("name") or ""
        body = match.group("body")
        range_ = match.group("range") or ""
        left = f"{name}{{{body}}}{range_}"
        right = f"{name}{{{_join_body(body, _SCRIPT_EXTRA)}}}{range_}"
        return f"({left} unless {right})"

    rewritten = _SELECTOR_RE.sub(rewrite_selector, held)
    for index, value in enumerate(placeholders):
        rewritten = rewritten.replace(_HOLD.format(index), value)
    return rewritten


def scope_to_script_plugin(query: str, template_id: str) -> str:
    """脚本指标只看本插件：collect_type=script，plugin_id 用模板 id，不用数字主键。"""
    if not query or not str(query).strip():
        return query
    template_id = str(template_id or "").strip()
    plugin_label = f'plugin_id="{_promql_quote(template_id)}"' if template_id else ""

    def rewrite(match: re.Match) -> str:
        body = match.group("body") or ""
        additions = []
        if not _has_collect_type(body):
            additions.append(_SCRIPT_EXTRA)
        if plugin_label and "plugin_id" not in body:
            additions.append(plugin_label)
        if not additions:
            return match.group(0)
        name = match.group("name") or ""
        range_ = match.group("range") or ""
        return f"{name}{{{_join_body(body, ', '.join(additions))}}}{range_}"

    return _SELECTOR_RE.sub(rewrite, query)


def isolate_metric_query(query: str, metric=None) -> str:
    """脚本插件指标收窄到模板 id；其它指标排除脚本序列。"""
    plugin = getattr(metric, "monitor_plugin", None) if metric is not None else None
    from apps.monitor.services.script_attach import is_script_plugin, script_template_id

    if is_script_plugin(plugin):
        return scope_to_script_plugin(query, script_template_id(plugin))
    return exclude_script_series(query)
