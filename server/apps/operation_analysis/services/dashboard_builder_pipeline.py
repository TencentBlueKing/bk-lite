"""把自然语言搭盘需求编译为可确定校验的方案。

模型可以提供 requirements，但用户明说的数据目标、图表形态和字段选择由这个
Module 收口，避免搜索工具、兜底执行器和提示词各自解释一遍。
"""

from __future__ import annotations

import re

from apps.operation_analysis.services.dashboard_proposal_service import draft_proposal_from_candidates, search_briefs, user_utterance

MAX_REQUIREMENTS = 8

_DISPLAY_RE = re.compile(r"(?:展示|看到|包含|包括|需要|想看)(?P<body>.+)")
_SPLIT_RE = re.compile(r"[、，,;；\n]+|以及|并且|同时|和(?=[^\s和]{2,})")
_LEADING_NOISE_RE = re.compile(r"^(?:帮我|请|想要|我要|给我|再)?(?:展示|看到|看|包含|包括)?")
_TRAILING_NOISE_RE = re.compile(r"(?:等等|等|的仪表盘|仪表盘|看板|大屏)$")

_CHART_HINTS = (
    (re.compile(r"top\s*\d*|排行|排名|榜单|最高|最多", re.I), "topN"),
    (re.compile(r"趋势|变化|走势|时间序列|时间范围|(?:按|随).{0,8}时间"), "line"),
    (re.compile(r"分布|占比|比例|构成|(?:分类|分组)统计|按.{0,12}统计|饼图"), "pie"),
    (re.compile(r"明细|列表|清单|详情|表格"), "table"),
    (re.compile(r"总数|数量|总量|多少"), "single"),
    (re.compile(r"关系|依赖|拓扑"), "nodeGraph"),
)

_ANALYSIS_HINTS = (
    (re.compile(r"概览|总览|概况|整体|overview|summary", re.I), "overview"),
    (re.compile(r"趋势|变化|走势|时间序列|时间范围|(?:按|随).{0,8}时间"), "trend"),
    (re.compile(r"分布|占比|比例|构成|(?:分类|分组)统计|按.{0,12}统计"), "distribution"),
    (re.compile(r"明细|列表|清单|详情"), "detail"),
    (re.compile(r"top\s*\d*|排行|排名|榜单", re.I), "ranking"),
)
_SEMANTIC_KEYS = ("domain", "metric", "dimension")
_ANALYSIS_TYPES = frozenset({"overview", "metric", "trend", "distribution", "detail", "ranking", "relationship"})

_CHART_ALIASES = {
    "bar": "bar",
    "line": "line",
    "pie": "pie",
    "table": "table",
    "single": "single",
    "topn": "topN",
    "topN": "topN",
    "柱状图": "bar",
    "折线图": "line",
    "趋势图": "line",
    "饼图": "pie",
    "表格": "table",
    "单值": "single",
    "排行": "topN",
}


def _chart_type(text: str, proposed=None) -> str:
    for pattern, chart_type in _CHART_HINTS:
        if pattern.search(text):
            return chart_type
    return _CHART_ALIASES.get(str(proposed or "").strip(), "")


def _analysis_type(text: str, proposed=None) -> str:
    value = str(proposed or "").strip().lower()
    if value in _ANALYSIS_TYPES:
        return value
    for pattern, analysis_type in _ANALYSIS_HINTS:
        if pattern.search(text):
            return analysis_type
    return ""


def _clean_goal(text: str) -> str:
    value = _LEADING_NOISE_RE.sub("", str(text or "").strip(" ，。！？、"))
    return _TRAILING_NOISE_RE.sub("", value).strip(" ，。！？、")


def _explicit_goals(message: str) -> list[str]:
    utterance = user_utterance(message)
    matched = _DISPLAY_RE.search(utterance)
    body = matched.group("body") if matched else utterance
    goals = [_clean_goal(part) for part in _SPLIT_RE.split(body)]
    goals = [goal for goal in goals if len(goal) >= 2][:MAX_REQUIREMENTS]
    if matched or (len(goals) >= 2 and all(_chart_type(goal) for goal in goals)):
        return goals
    return []


def plan_dashboard_requirements(message: str, proposed: list[dict] | None = None) -> list[dict]:
    """生成稳定的数据目标。用户明确列出多项时，不让模型把它们合并成一个模糊检索词。"""
    explicit = _explicit_goals(message)
    if len(explicit) >= 2:
        return [
            {
                "text": goal,
                "purpose": "visualization",
                **({"chartType": chart_type} if (chart_type := _chart_type(goal)) else {}),
            }
            for goal in explicit
        ]

    normalized = []
    for item in proposed or []:
        if not isinstance(item, dict):
            continue
        purpose = item.get("purpose") if item.get("purpose") in {"visualization", "parameter_options"} else "visualization"
        text = _clean_goal(str(item.get("text") or item.get("description") or ""))
        if not text:
            continue
        chart_type = _chart_type(text, item.get("chartType")) if purpose == "visualization" else ""
        normalized.append(
            {
                "text": text,
                "purpose": purpose,
                **({"chartType": chart_type} if chart_type else {}),
                **(
                    {"analysisType": analysis_type}
                    if (analysis_type := _analysis_type(text, item.get("analysisType"))) and purpose == "visualization"
                    else {}
                ),
                **{
                    key: str(item.get(key)).strip()
                    for key in _SEMANTIC_KEYS
                    if item.get(key) not in (None, "") and len(str(item.get(key)).strip()) <= 80
                },
            }
        )
        if len(normalized) >= MAX_REQUIREMENTS:
            break
    if normalized:
        return normalized

    fallback = explicit[0] if explicit else _clean_goal(user_utterance(message))
    if not fallback:
        return []
    chart_type = _chart_type(fallback)
    analysis_type = _analysis_type(fallback)
    return [
        {
            "text": fallback,
            "purpose": "visualization",
            **({"chartType": chart_type} if chart_type else {}),
            **({"analysisType": analysis_type} if analysis_type else {}),
        }
    ]


def _field_score(field: dict, text: str) -> int:
    body = f"{field.get('name') or ''} {field.get('desc') or ''}".lower()
    compact = re.sub(r"\s+", "", text.lower())
    score = 0
    for size in (2, 3, 4):
        for index in range(max(0, len(compact) - size + 1)):
            token = compact[index : index + size]
            if token in body:
                score += size
    if re.search(r"总数|数量|总量|多少", compact) and re.search(r"count|total|总数|数量", body):
        score += 8
    return score


def _candidate_for_requirement(requirement: dict, candidates: list[dict]) -> dict | None:
    chart_type = str(requirement.get("chartType") or "")
    compatible = [item for item in candidates if isinstance(item, dict) and (not chart_type or chart_type in (item.get("chart_type") or []))]
    pool = compatible or [item for item in candidates if isinstance(item, dict)]
    ranked = search_briefs([requirement], pool, limit_per_requirement=1, total_limit=1)
    if not ranked:
        return None
    selected = dict(ranked[0])
    if chart_type and chart_type in (selected.get("chart_type") or []):
        selected["chart_type"] = [chart_type]
    if chart_type == "single":
        fields = [item for item in (selected.get("fields") or []) if isinstance(item, dict)]
        if fields:
            selected["fields"] = [max(fields, key=lambda field: _field_score(field, str(requirement.get("text") or "")))]
    return selected


def draft_proposal_for_requirements(requirements: list[dict], candidates: list[dict]) -> dict | None:
    """每个数据目标只选一个最匹配数据源，再交给组件契约编译器生成方案。"""
    selected = []
    seen: set[tuple[object, str]] = set()
    for requirement in requirements or []:
        if not isinstance(requirement, dict) or requirement.get("purpose") == "parameter_options":
            continue
        candidate = _candidate_for_requirement(requirement, candidates)
        if not candidate:
            continue
        key = (candidate.get("id"), str((candidate.get("chart_type") or [""])[0]))
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
    return draft_proposal_from_candidates(selected) if selected else None


def unmatched_requirement_texts(requirements: list[dict], candidates: list[dict]) -> list[str]:
    """返回无可编译候选的数据目标，让产品明示部分成功而不是偷换维度。"""
    unmatched = []
    for requirement in requirements or []:
        if not isinstance(requirement, dict) or requirement.get("purpose") == "parameter_options":
            continue
        if _candidate_for_requirement(requirement, candidates) is None:
            text = str(requirement.get("text") or requirement.get("description") or "").strip()
            if text:
                unmatched.append(text)
    return unmatched


__all__ = ["draft_proposal_for_requirements", "plan_dashboard_requirements", "unmatched_requirement_texts"]
