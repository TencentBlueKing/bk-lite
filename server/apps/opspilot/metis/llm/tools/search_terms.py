"""从用户原问抽出检索词，并按固定现象表展开同义词。

不把两个概念粘成一个新短语。告警和日志共用这份词表，各自做一次或查询。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_MAX_TERMS = 8

# 长词在前，避免「告警」先吃掉「告警中心」。
_FILLERS = (
    "告警中心",
    "对应日志",
    "有没有",
    "对一下",
    "是不是",
    "还是",
    "以及",
    "最近",
    "特别",
    "两边",
    "对应",
    "告警",
    "日志",
    "页面",
    "一下",
    "请问",
    "帮我",
    "看看",
    "现在",
    "怎么",
    "为什么",
    "的",
    "了",
    "和",
    "与",
    "在",
)

# 从中文片段里剥下来单独保留的现象词。拒绝本身太宽，只走同义词表。
_PEEL_KEEP = ("超时", "报错")
_PEEL_DROP = ("拒绝", "太慢")

_ASCII_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def _gateway_refusal(text: str) -> bool:
    lowered = text.lower()
    if "connection refused" in lowered:
        return True
    if "网关" in text and "拒绝" in text:
        return True
    return "拒绝连接" in text


def _timeout_mentioned(text: str) -> bool:
    lowered = text.lower()
    return "超时" in text or "timeout" in lowered or "timed out" in lowered


def _dedupe(terms: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        cleaned = str(term or "").strip()
        if len(cleaned) < 2:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
        if len(ordered) >= _MAX_TERMS:
            break
    return ordered


def _chinese_terms(text: str) -> list[str]:
    cleaned = re.sub(r"[，。！？、,.!?;；:：\s]+", " ", text)
    for filler in _FILLERS:
        cleaned = cleaned.replace(filler, " ")
    found: list[str] = []
    for chunk in cleaned.split():
        pieces = _CJK_RUN.findall(chunk)
        if not pieces:
            continue
        rest = "".join(pieces)
        for word in (*_PEEL_KEEP, *_PEEL_DROP):
            if word not in rest:
                continue
            if word in _PEEL_KEEP:
                found.append(word)
            rest = rest.replace(word, " ")
        for piece in rest.split():
            if len(piece) >= 2:
                found.append(piece)
    return found


def _synonyms(text: str) -> list[str]:
    extra: list[str] = []
    if _timeout_mentioned(text):
        extra.extend(("timeout", "timed out"))
    if _gateway_refusal(text):
        extra.extend(("connection refused", "502", "upstream"))
    return extra


def build_search_terms(user_message: str) -> list[str]:
    """问句原词 + 固定同义词。没有可用原词时返回空列表。"""
    text = str(user_message or "").strip()
    if not text:
        return []
    ascii_terms = _ASCII_TOKEN.findall(text)
    return _dedupe([*_chinese_terms(text), *ascii_terms, *_synonyms(text)])


def resolve_search_terms(user_message: str, model_keyword: str | None = None) -> list[str]:
    """有用户原问就用词表，忽略模型粘出来的短语。否则只按空白拆开模型关键字。"""
    terms = build_search_terms(user_message)
    if terms:
        return terms
    raw = str(model_keyword or "").strip()
    if not raw:
        return []
    return _dedupe(part for part in re.split(r"\s+", raw) if part)


SEARCH_NOTE = "已按或条件检索上述词。空结果表示这些词都未命中，不要换关键字再搜。"


def user_message_from_config(config: Any) -> str:
    configurable = {}
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
    graph_request = configurable.get("graph_request")
    messages = [
        getattr(graph_request, "graph_user_message", "") if graph_request is not None else "",
        getattr(graph_request, "user_message", "") if graph_request is not None else "",
        configurable.get("graph_user_message") or "",
        configurable.get("user_message") or "",
    ]
    return " ".join(message for message in messages if isinstance(message, str) and message.strip())
