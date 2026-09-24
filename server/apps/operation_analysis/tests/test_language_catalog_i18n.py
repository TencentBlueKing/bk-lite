"""operation_analysis 语言包静态门禁：全目录 en / zh-Hans 字符串叶节点对称且占位符一致。

与 messages 专项（test_user_messages）互补：本用例覆盖 LanguageLoader 合并后的
全部 catalog（含内置画布 overlay），满足 #4340 AC4 的 server 侧对称检查。
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from apps.core.utils.loader import LanguageLoader, clear_language_cache

pytestmark = pytest.mark.unit

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _flatten_strings(node: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(node, str):
        if prefix:
            out[prefix] = node
        return out
    if isinstance(node, dict):
        for key, child in node.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_strings(child, next_prefix))
        return out
    if isinstance(node, list):
        for index, child in enumerate(node):
            next_prefix = f"{prefix}[{index}]"
            out.update(_flatten_strings(child, next_prefix))
        return out
    return out


def _catalog(language: str) -> dict[str, str]:
    clear_language_cache("operation_analysis", language)
    translations = LanguageLoader("operation_analysis", language).translations or {}
    flat = _flatten_strings(translations)
    assert flat, f"operation_analysis/{language} catalog is empty"
    return flat


def test_operation_analysis_language_catalogs_are_symmetric():
    en = _catalog("en")
    zh = _catalog("zh-Hans")

    missing_zh = sorted(set(en) - set(zh))
    missing_en = sorted(set(zh) - set(en))
    assert missing_zh == [], f"zh-Hans missing keys: {missing_zh[:20]}"
    assert missing_en == [], f"en missing keys: {missing_en[:20]}"

    mismatches = [key for key in en if sorted(_PLACEHOLDER.findall(en[key])) != sorted(_PLACEHOLDER.findall(zh[key]))]
    assert mismatches == [], f"placeholder mismatches: {mismatches[:20]}"
