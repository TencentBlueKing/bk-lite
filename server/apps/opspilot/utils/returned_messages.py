# -*- coding: utf-8 -*-
"""把已经返回给页面的中文错误句换成当前语言。

词表只覆盖接口、知识库和技能包/记忆/参数校验。
工具结果、工作流节点和渠道回复不在这里。
"""
import json
import re

from apps.opspilot.utils.returned_message_pairs import PAIRS

_CJK = re.compile(r"[\u4e00-\u9fff]")
_PLACEHOLDER = re.compile(r"\{[^{}]+\}")
_MESSAGE_KEYS = {"message", "detail", "reason", "error", "non_field_errors"}


def _pairs():
    from apps.opspilot.utils.returned_message_gap_pairs import GAP_PAIRS
    from apps.opspilot.utils.returned_message_more_pairs import MORE_PAIRS

    return PAIRS + GAP_PAIRS + MORE_PAIRS


def _compile():
    exact = {}
    templates = []
    for zh, en in _pairs():
        if "{" not in zh:
            exact[zh] = en
            continue
        parts = _PLACEHOLDER.split(zh)
        pattern = "^" + "(.*)".join(re.escape(part) for part in parts) + "$"
        templates.append((re.compile(pattern), en, zh.count("{"), len(zh)))
    templates.sort(key=lambda item: item[3], reverse=True)
    return exact, templates


_EXACT, _TEMPLATES = None, None


def _catalog():
    global _EXACT, _TEMPLATES
    if _EXACT is None:
        _EXACT, _TEMPLATES = _compile()
    return _EXACT, _TEMPLATES


def _is_chinese_locale(locale):
    normalized = (locale or "en").replace("_", "-").lower()
    return normalized.startswith("zh")


def locale_from_loader(loader):
    if loader is None:
        return "en"
    return getattr(loader, "default_lang", None) or "en"


def localize_returned_text(text, loader=None):
    """整句匹配词表。中文界面原样返回。未收录的句子保持原文。"""
    if not isinstance(text, str) or not text or not _CJK.search(text):
        return text
    if _is_chinese_locale(locale_from_loader(loader)):
        return text
    exact, templates = _catalog()
    stripped = text.strip()
    if stripped in exact:
        return exact[stripped]
    for pattern, english, groups, _length in templates:
        matched = pattern.fullmatch(stripped)
        if not matched or len(matched.groups()) != groups:
            continue
        try:
            return english.format(*matched.groups())
        except (IndexError, KeyError):
            continue
    if ":" not in stripped and ";" not in stripped:
        return text
    segments = []
    changed = False
    for segment in stripped.split(";"):
        if ":" in segment:
            key, value = segment.split(":", 1)
            translated = localize_returned_text(value, loader)
            changed = changed or translated != value
            segments.append(f"{key}:{translated}")
        else:
            translated = exact.get(segment, segment)
            changed = changed or translated != segment
            segments.append(translated)
    if not changed:
        return text
    return ";".join(segments)


def localize_embedded_text(text, loader=None):
    """整句翻译；否则把词表里的完整句子从工具结果正文里替换掉。过短的词不替换。"""
    if not isinstance(text, str) or not text or not _CJK.search(text):
        return text
    if _is_chinese_locale(locale_from_loader(loader)):
        return text
    whole = localize_returned_text(text.strip(), loader)
    if whole != text.strip():
        prefix = text[: len(text) - len(text.lstrip())]
        suffix = text[len(text.rstrip()) :]
        return f"{prefix}{whole}{suffix}"
    exact, _templates = _catalog()
    result = text
    for zh in sorted((key for key in exact if len(key) >= 8), key=len, reverse=True):
        if zh in result:
            result = result.replace(zh, exact[zh])
    return result


def localize_returned_payload(payload, loader):
    if loader is None or _is_chinese_locale(locale_from_loader(loader)):
        return payload

    def walk(node, key=None):
        if isinstance(node, str):
            if key in _MESSAGE_KEYS or node.strip() in _catalog()[0]:
                return localize_returned_text(node, loader)
            return node
        if isinstance(node, list):
            return [walk(item, key) for item in node]
        if isinstance(node, dict):
            return {name: walk(value, name) for name, value in node.items()}
        return node

    return walk(payload)


def translate_response_body(response, request):
    loader = getattr(request, "opspilot_language_loader", None)
    if loader is None or _is_chinese_locale(locale_from_loader(loader)):
        return
    if getattr(response, "streaming", False):
        return
    content_type = response.get("Content-Type", "")
    if "application/json" not in content_type:
        return
    raw = getattr(response, "content", None)
    if not raw or len(raw) > 512_000 or not _CJK.search(raw.decode("utf-8", errors="ignore")):
        return
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError, TypeError):
        return
    translated = localize_returned_payload(payload, loader)
    if translated == payload:
        return
    response.content = json.dumps(translated, ensure_ascii=False).encode("utf-8")
    if "Content-Length" in response:
        response["Content-Length"] = str(len(response.content))
