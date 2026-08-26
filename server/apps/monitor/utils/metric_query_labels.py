"""指标公式中的实例标签占位符规范化。"""

from __future__ import annotations

import re

METRIC_LABELS_PLACEHOLDER = "__$labels__"

_SELECTOR_RE = re.compile(r"\{([^{}]*)\}")
_BARE_METRIC_RE = re.compile(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\b(?!\s*[\({])")
_CLAUSE_PROTECT_RE = re.compile(
    r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)",
    re.IGNORECASE,
)
_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
# 单个瞬时向量选择器：裸指标名，或指标名 + 一层 {...} 标签选择器。
_RAW_VECTOR_SELECTOR_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^{}]*\})?\s*$")

_PROMQL_KEYWORDS = {
    "sum",
    "min",
    "max",
    "avg",
    "group",
    "stddev",
    "stdvar",
    "count",
    "count_values",
    "quantile",
    "rate",
    "irate",
    "increase",
    "delta",
    "idelta",
    "deriv",
    "predict_linear",
    "last_over_time",
    "avg_over_time",
    "min_over_time",
    "max_over_time",
    "sum_over_time",
    "count_over_time",
    "stddev_over_time",
    "stdvar_over_time",
    "quantile_over_time",
    "absent",
    "absent_over_time",
    "ceil",
    "floor",
    "round",
    "clamp",
    "clamp_min",
    "clamp_max",
    "abs",
    "sgn",
    "ln",
    "log2",
    "log10",
    "exp",
    "sqrt",
    "timestamp",
    "time",
    "vector",
    "scalar",
    "label_replace",
    "label_join",
    "histogram_quantile",
    "sort",
    "sort_desc",
    "topk",
    "bottomk",
    "by",
    "without",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "and",
    "or",
    "unless",
    "bool",
    "offset",
    "atan2",
    "nan",
    "inf",
}


def is_raw_vector_selector(query: str | None) -> bool:
    """判断公式是否为单个原始向量选择器（可点选插入，非计算表达式）。"""
    if query is None:
        return False
    trimmed = query.strip()
    if not trimmed:
        return False
    return bool(_RAW_VECTOR_SELECTOR_RE.fullmatch(trimmed))


def _in_protected_range(start: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start >= left and start < right for left, right in ranges)


def ensure_metric_labels_placeholder(query: str | None) -> str:
    """写入前确保公式带有 __$labels__，兼容用户只写裸指标名的场景。"""
    if query is None:
        return ""
    trimmed = query.strip()
    if not trimmed:
        return query

    # 引号字符串内的标识符/花括号不得注入（如 label_replace 的 dst/src）。
    string_ranges = [(m.start(), m.end()) for m in _STRING_RE.finditer(trimmed)]

    def _inject_selector(match: re.Match[str]) -> str:
        if _in_protected_range(match.start(), string_ranges):
            return match.group(0)
        inner = match.group(1)
        if METRIC_LABELS_PLACEHOLDER in inner:
            return match.group(0)
        cleaned = inner.strip()
        if not cleaned:
            return "{" + METRIC_LABELS_PLACEHOLDER + "}"
        return "{" + cleaned + "," + METRIC_LABELS_PLACEHOLDER + "}"

    with_selectors = _SELECTOR_RE.sub(_inject_selector, trimmed)
    # 选择器 / by|without|on 子句 / 字符串均不得再当裸指标注入。
    protected_ranges = [(m.start(), m.end()) for m in _STRING_RE.finditer(with_selectors)]
    protected_ranges.extend((m.start(), m.end()) for m in _SELECTOR_RE.finditer(with_selectors))
    protected_ranges.extend((m.start(), m.end()) for m in _CLAUSE_PROTECT_RE.finditer(with_selectors))

    def _inject_bare(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.lower() in _PROMQL_KEYWORDS:
            return name
        if _in_protected_range(match.start(), protected_ranges):
            return name
        return f"{name}{{{METRIC_LABELS_PLACEHOLDER}}}"

    return _BARE_METRIC_RE.sub(_inject_bare, with_selectors)
