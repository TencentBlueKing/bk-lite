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
    "查一下",
    "一下",
    "请问",
    "帮我",
    "看看",
    "现在",
    "当前",
    "有哪些",
    "有什么",
    "哪些",
    "什么",
    "我要查询",
    "一小时",
    "半小时",
    "查询",
    "小时",
    "分钟",
    "秒钟",
    "今天",
    "昨天",
    "前天",
    "本周",
    "上周",
    "本月",
    "有多少条",
    "有多少个",
    "多少条",
    "多少个",
    "几条",
    "几个",
    "多少",
    "怎么",
    "为什么",
    "的",
    "了",
    "和",
    "与",
    "在",
)

_NOT_CONTENT = (
    "自动关闭",
    "自动恢复",
    "未关闭",
    "未分派",
    "待响应",
    "处理中",
    "已关闭",
    "已恢复",
    "一小时",
    "半小时",
    "小时",
    "分钟",
    "秒钟",
    "今天",
    "昨天",
    "前天",
    "本周",
    "上周",
    "本月",
    "活动",
    "活跃",
)
_CHINESE_STOPS = frozenset((*_FILLERS, *_NOT_CONTENT, "我"))
_SEGMENT_STOPS = tuple(sorted((word for word in _CHINESE_STOPS if len(word) >= 2), key=len, reverse=True))
_ENGLISH_STOPS = frozenset(
    {
        "active",
        "closed",
        "pending",
        "resolved",
        "processing",
        "unassigned",
        "current",
        "currently",
        "open",
        "today",
        "yesterday",
        "last",
        "past",
        "recent",
        "now",
        "ago",
        "hour",
        "hours",
        "minute",
        "minutes",
        "second",
        "seconds",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "hr",
        "hrs",
        "min",
        "mins",
        "sec",
        "secs",
        "which",
        "what",
        "how",
        "why",
        "many",
        "search",
        "query",
        "alert",
        "alerts",
        "log",
        "logs",
        "page",
        "please",
        "show",
        "list",
        "find",
        "get",
        "the",
        "for",
        "do",
        "have",
        "of",
        "and",
        "to",
        "in",
        "on",
        "is",
        "are",
        "an",
        "with",
        "from",
        "me",
        "my",
        "there",
        "this",
        "that",
        "was",
        "were",
        "be",
        "does",
        "did",
        "has",
        "had",
        "any",
        "about",
        "at",
        "by",
        "or",
        "not",
        "new",
        "recovered",
        "word",
        "docx",
        "pdf",
        "excel",
        "ppt",
        "pptx",
    }
)
_GLUE_CHARS = frozenset("下条")
_SINGLE_CHAR_STOPS = frozenset(word for word in _CHINESE_STOPS if len(word) == 1)
_FIXED_ASCII_CONTENT = frozenset({"error", "errors", "timeout", "upstream"})
_IDENTIFIER_MARK = re.compile(r"[0-9._:\-]")
_TIME_UNIT_WORD = r"hours?|minutes?|seconds?|days?|weeks?|months?|hrs?|mins?|secs?|小时|分钟|秒钟|天|周"
_TIME_QUANTITY = re.compile(
    rf"(?<![A-Za-z0-9._:-])(\d+)\s*(?:{_TIME_UNIT_WORD})(?![A-Za-z0-9._:-])",
    re.IGNORECASE,
)
_TIME_UNIT_TOKEN = re.compile(r"\d+(?:hrs|hr|mins|min|secs|sec|h|m|d|s)\Z", re.IGNORECASE)
_LEADING_DIGITS = re.compile(r"\d+")

_ASCII_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
# 只剥整段页面块；导语里的「<current_page>」字样不能当地标。
_CURRENT_PAGE_RE = re.compile(r"(?im)^<current_page>\s*$[\s\S]*?</current_page>")
_FOCUSED_QUESTION_RE = re.compile(r"本轮用户问题是「([^」]+)」")
# skill_channel 注入的 page_context 导语/约束，切词时必须丢掉，否则会污染检索词。
_PAGE_CONTEXT_NOISE_MARKERS = (
    "以下是用户当前正在查看的页面快照",
    "只根据本轮",
    "时间范围、横轴起止与 KPI",
    "若缺少查询对象",
    "禁止沿用对话历史",
    "禁止回答、复述或续写历史",
    "截图上可能没有标题",
    "问使用率或容量时优先用 KPI",
    "问 Top 或排行时按图表列出",
    "用户本轮在询问凭据或密钥",
    "图表说明:",
)


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


def _time_numbers(text: str) -> set[str]:
    found = {match.group(1) for match in _TIME_QUANTITY.finditer(text or "")}
    for token in _ASCII_TOKEN.findall(text or ""):
        if not _TIME_UNIT_TOKEN.fullmatch(token):
            continue
        digits = _LEADING_DIGITS.match(token)
        if digits:
            found.add(digits.group(0))
    return found


def _longest_segment_stop(token: str, index: int) -> int:
    rest = token[index:]
    for word in _SEGMENT_STOPS:
        if rest.startswith(word):
            return len(word)
    return 0


def _tiled_by_stop_words(token: str) -> bool:
    if not token or token.isdigit():
        return False
    index = 0
    length = len(token)
    consumed_multi = False
    while index < length:
        if token[index].isdigit():
            index += 1
            while index < length and token[index].isdigit():
                index += 1
            continue
        hit = _longest_segment_stop(token, index)
        if hit:
            consumed_multi = True
            index += hit
            continue
        if token[index] in _GLUE_CHARS or token[index] in _SINGLE_CHAR_STOPS:
            index += 1
            continue
        if consumed_multi and length - index == 1:
            return True
        return False
    return True


def _is_non_content_token(token: str) -> bool:
    if _TIME_UNIT_TOKEN.fullmatch(token) or _TIME_QUANTITY.search(token):
        return True
    if token in _CHINESE_STOPS or token.casefold() in _ENGLISH_STOPS:
        return True
    return _tiled_by_stop_words(token)


def _is_observed_ascii_content(token: str) -> bool:
    if token.casefold() in _FIXED_ASCII_CONTENT:
        return True
    return _IDENTIFIER_MARK.search(token) is not None


def _ascii_content_terms(text: str) -> list[str]:
    time_numbers = _time_numbers(text)
    kept = []
    for token in _ASCII_TOKEN.findall(text):
        if token in time_numbers or _is_non_content_token(token) or not _is_observed_ascii_content(token):
            continue
        kept.append(token)
    return kept


def _keyword_is_content(keyword: str) -> bool:
    token = str(keyword or "").strip()
    if not token or _is_non_content_token(token):
        return False
    if _ASCII_TOKEN.fullmatch(token):
        return True
    return len("".join(_CJK_RUN.findall(token))) >= 2


def _phenomenon_terms(text: str) -> list[str]:
    extra: list[str] = []
    if "超时" in text:
        extra.append("超时")
    if _timeout_mentioned(text):
        extra.extend(("timeout", "timed out"))
    if "报错" in text:
        extra.append("报错")
    if _gateway_refusal(text):
        if "网关" in text:
            extra.append("网关")
        extra.extend(("connection refused", "502", "upstream"))
    return extra


def _observed_terms(text: str) -> list[str]:
    if not text:
        return []
    return [*_ascii_content_terms(text), *_phenomenon_terms(text)]


def _accepted_keyword_parts(model_keyword: str | None, text: str) -> list[str]:
    raw = str(model_keyword or "").strip()
    if not raw:
        return []
    time_numbers = _time_numbers(text)
    kept = []
    for part in re.split(r"\s+", raw):
        if part in time_numbers or not _keyword_is_content(part):
            continue
        if text and part.casefold() not in text.casefold():
            continue
        kept.append(part)
    return kept


def user_question_for_search(text: str) -> str:
    """从可能含 page_context 的拼装消息里抽出真正问句，避免页面文案污染词表。"""
    body = str(text or "").strip()
    if not body:
        return ""
    focused = _FOCUSED_QUESTION_RE.search(body)
    if focused and focused.group(1).strip():
        return focused.group(1).strip()
    body = _CURRENT_PAGE_RE.sub(" ", body)
    paragraphs = re.split(r"\n\s*\n", body)
    kept: list[str] = []
    for para in paragraphs:
        chunk = para.strip()
        if not chunk:
            continue
        if any(marker in chunk for marker in _PAGE_CONTEXT_NOISE_MARKERS):
            continue
        kept.append(chunk)
    cleaned = "\n".join(kept).strip()
    return cleaned or str(text or "").strip()


def build_search_terms(user_message: str) -> list[str]:
    return _dedupe(_observed_terms(user_question_for_search(user_message)))


def keyword_has_content(keyword: str | None) -> bool:
    return _keyword_is_content(str(keyword or "").strip())


def accepted_model_keyword(keyword: str | None, user_message: str = "") -> str:
    """模型关键字必须本身是正文。有用户原问时，还要原样出现在原问里。"""
    parts = _accepted_keyword_parts(keyword, user_question_for_search(user_message))
    return " ".join(parts)


def resolve_search_terms(user_message: str, model_keyword: str | None = None) -> list[str]:
    text = user_question_for_search(user_message)
    return _dedupe([*_observed_terms(text), *_accepted_keyword_parts(model_keyword, text)])


SEARCH_NOTE = "已按或条件检索上述词。空结果表示这些词都未命中，不要换关键字再搜。"


def user_message_from_config(config: Any) -> str:
    configurable = {}
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
    graph_request = configurable.get("graph_request")
    candidates = [
        getattr(graph_request, "graph_user_message", "") if graph_request is not None else "",
        getattr(graph_request, "user_message", "") if graph_request is not None else "",
        configurable.get("graph_user_message") or "",
        configurable.get("user_message") or "",
    ]
    for message in candidates:
        if isinstance(message, str) and message.strip():
            return user_question_for_search(message)
    return ""
