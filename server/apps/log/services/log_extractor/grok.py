"""把 Grok 原文展开成正则，并给出内部组名到属性路径的映射。"""

import re

from apps.log.services.log_extractor.grok_library import GROK_PATTERNS_BY_NAME

MAX_GROK_REFERENCES = 64
MAX_EXPANDED_REGEX_LENGTH = 16384
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SEGMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NAMED_GROUP = re.compile(r"\(\?P?<[A-Za-z_]")


class GrokPatternError(ValueError):
    pass


class _Build:
    def __init__(self):
        self.ref_count = 0
        self.user_ref_count = 0
        self.next_group = 0
        self.mapping: dict[str, str] = {}


def expand_grok(pattern: str) -> tuple[str, dict[str, str]]:
    if not isinstance(pattern, str):
        raise GrokPatternError("Grok 引用语法无效")
    state = _Build()
    expanded = _expand_text(pattern, state, (), None)
    if not state.mapping:
        raise GrokPatternError("Grok 模式没有写出字段")
    if len(expanded) > MAX_EXPANDED_REGEX_LENGTH:
        raise GrokPatternError("展开后的正则长度超过 16384")
    return expanded, dict(state.mapping)


def _expand_text(text: str, state: _Build, stack: tuple[str, ...], user_index: int | None) -> str:
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("%{", cursor)
        if start < 0:
            literal = text[cursor:]
            _reject_named_group(literal)
            parts.append(literal)
            break
        if start > cursor:
            literal = text[cursor:start]
            _reject_named_group(literal)
            parts.append(literal)
        end = text.find("}", start + 2)
        if user_index is None:
            state.user_ref_count += 1
            current_index = state.user_ref_count
        else:
            current_index = user_index
        state.ref_count += 1
        if state.ref_count > MAX_GROK_REFERENCES:
            raise GrokPatternError(f"引用 {current_index} 超过 Grok 引用数上限 64")
        if end < 0:
            raise GrokPatternError(f"引用 {current_index} 语法无效")
        parts.append(_expand_ref(text[start + 2 : end], state, stack, current_index))
        cursor = end + 1
    return "".join(parts)


def _expand_ref(body: str, state: _Build, stack: tuple[str, ...], user_index: int) -> str:
    name, path, type_filter = _parse_reference(body, user_index)
    pattern = GROK_PATTERNS_BY_NAME.get(name)
    if pattern is None:
        raise GrokPatternError(f"引用 {user_index} 的模式 {name} 不存在")
    if type_filter:
        raise GrokPatternError(f"引用 {user_index}（{name}）Grok 只写出字符串，如需数值比较请在查询中转换")
    if pattern.composite and path is not None:
        raise GrokPatternError(f"引用 {user_index} 不能给复合模式 {name} 命名")
    if path is not None:
        _validate_path(path, user_index, name)
    if name in stack:
        raise GrokPatternError(f"模式 {name} 存在循环引用")
    if "%{" in pattern.definition:
        inner = _expand_text(pattern.definition, state, stack + (name,), user_index)
    else:
        _reject_named_group(pattern.definition)
        inner = pattern.definition
    if pattern.composite:
        return inner
    wrapped = f"(?:{inner})"
    if path is None:
        return wrapped
    _claim_path(state, path, user_index, name)
    group = f"g{state.next_group}"
    state.next_group += 1
    state.mapping[group] = path
    return f"(?P<{group}>{wrapped})"


def _parse_reference(body: str, user_index: int) -> tuple[str, str | None, bool]:
    if not body or any(character.isspace() for character in body):
        raise GrokPatternError(f"引用 {user_index} 语法无效")
    parts = body.split(":")
    if len(parts) > 3 or any(part == "" for part in parts) or _NAME.fullmatch(parts[0]) is None:
        raise GrokPatternError(f"引用 {user_index} 语法无效")
    path = parts[1] if len(parts) >= 2 else None
    return parts[0], path, len(parts) == 3


def _validate_path(path: str, user_index: int, name: str) -> None:
    segments = path.split(".")
    if not segments or any(_SEGMENT.fullmatch(segment) is None for segment in segments):
        raise GrokPatternError(f"引用 {user_index}（{name}）的属性路径无效")


def _claim_path(state: _Build, path: str, user_index: int, name: str) -> None:
    from apps.log.services.log_extractor.semantics import PROTECTED_FIELDS

    root = path.split(".", 1)[0]
    if root in PROTECTED_FIELDS:
        raise GrokPatternError(f"引用 {user_index}（{name}）不能覆盖系统保护字段 {path}")
    if root == "message":
        raise GrokPatternError(f"引用 {user_index}（{name}）不能写出 message")
    for existing in state.mapping.values():
        if existing == path:
            raise GrokPatternError(f"引用 {user_index}（{name}）写出路径重复: {path}")
        if _paths_overlap(existing, path):
            raise GrokPatternError(f"引用 {user_index}（{name}）写出路径重叠: {existing} 与 {path}")


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = left.split(".")
    right_parts = right.split(".")
    shortest = min(len(left_parts), len(right_parts))
    return left_parts[:shortest] == right_parts[:shortest]


def _reject_named_group(literal: str) -> None:
    if _NAMED_GROUP.search(literal):
        raise GrokPatternError("Grok 字面量不能包含命名捕获组")
