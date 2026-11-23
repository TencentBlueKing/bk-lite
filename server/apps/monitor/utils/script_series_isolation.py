"""原生 PromQL 排除脚本序列，脚本指标则收窄到本插件。

排除脚本序列时，在每个选择器里加 collect_type!="script"。
VictoriaMetrics 与 Prometheus 一致：!= 也匹配没有该标签的序列，
所以没有 collect_type 的主机序列仍保留。

不要用 `a unless a{collect_type="script"}` 包住选择器。策略会把区间直接拼在
基础查询后面，`(a unless b)[5m]` 是按步长重采样的子查询，不是原始区间，
changes / deriv 的结果会变。
"""

from __future__ import annotations

import re

_COLLECT_TYPE_RE = re.compile(r"""collect_type\s*(?:!?=~?|!=)\s*['"]""")
_STRING = r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'"
# 字符串整段跳过：标签值里的 {1,3} 这类正则量词不是选择器。
_SELECTOR_RE = re.compile(r"(?P<string>" + _STRING + r")|\{(?P<body>(?:" + _STRING + r"|[^{}\"'])*)\}")
_NOT_SCRIPT = 'collect_type!="script"'
_IS_SCRIPT = 'collect_type="script"'


def _has_collect_type(body: str) -> bool:
    return bool(_COLLECT_TYPE_RE.search(body or ""))


def _join_body(body: str, extra: str) -> str:
    stripped = (body or "").strip().rstrip(",").strip()
    if not stripped:
        return extra
    return f"{stripped}, {extra}"


def _promql_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _rewrite_selectors(query: str, additions_for) -> str:
    """对每个 {…} 选择器追加标签条件。additions_for(body) 返回要追加的条件列表。"""

    def rewrite(match: re.Match) -> str:
        if match.group("string") is not None:
            return match.group(0)
        body = match.group("body") or ""
        additions = additions_for(body)
        if not additions:
            return match.group(0)
        return "{" + _join_body(body, ", ".join(additions)) + "}"

    return _SELECTOR_RE.sub(rewrite, query)


def exclude_script_series(query: str) -> str:
    """去掉 collect_type="script" 的序列，保留没有该标签的序列。"""
    if not query or not str(query).strip():
        return query
    return _rewrite_selectors(query, lambda body: [] if _has_collect_type(body) else [_NOT_SCRIPT])


def isolate_status_timestamp_query(query: str) -> str:
    """状态查询先排除脚本序列，再取原始样本时间。"""
    from apps.monitor.utils.last_sample import last_sample_timestamp_query

    return last_sample_timestamp_query(exclude_script_series(query))


def scope_to_script_plugin(query: str, template_id: str) -> str:
    """脚本指标只看本插件：collect_type=script，plugin_id 用模板 id，不用数字主键。"""
    if not query or not str(query).strip():
        return query
    template_id = str(template_id or "").strip()
    plugin_label = f'plugin_id="{_promql_quote(template_id)}"' if template_id else ""

    def additions_for(body: str) -> list[str]:
        additions = []
        if not _has_collect_type(body):
            additions.append(_IS_SCRIPT)
        if plugin_label and "plugin_id" not in body:
            additions.append(plugin_label)
        return additions

    return _rewrite_selectors(query, additions_for)


def isolate_metric_query(query: str, metric=None) -> str:
    """脚本插件指标收窄到模板 id；其它指标排除脚本序列。"""
    plugin = getattr(metric, "monitor_plugin", None) if metric is not None else None
    from apps.monitor.services.script_attach import is_script_plugin, script_template_id

    if is_script_plugin(plugin):
        return scope_to_script_plugin(query, script_template_id(plugin))
    return exclude_script_series(query)
