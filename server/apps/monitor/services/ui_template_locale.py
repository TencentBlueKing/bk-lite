"""UI 模板按 locale 切换中英文字段。

UI.json 的 form_fields/table_columns 中每条带 label 字段(中文)。
同时支持 label_en(英文);如果用户 locale 属于英语系,且 label_en 非空,
就用 label_en 替换 label 再返回。

通用规则:任意 string 字段若有对应的 `<field>_en` 字段且非空,英语 locale 下用之替换。
"""
from __future__ import annotations

from typing import Any


_EN_LOCALES = {"en", "en-us", "en-gb"}


def _is_english(locale: str) -> bool:
    return (locale or "").lower().startswith("en")


def _localize_node(node: Any, locale: str) -> Any:
    """递归遍历节点,英语 locale 下用每个字段的 <name>_en 变体替换。"""
    if not _is_english(locale):
        return node
    if isinstance(node, dict):
        # 优先做 key 翻译:对 dict 中每个 string 字段,若存在对应的 <name>_en 变体,
        # 且变体非空,则替换。
        keys_snapshot = list(node.keys())
        for k in keys_snapshot:
            v = node[k]
            if isinstance(v, str):
                en_key = f"{k}_en"
                if en_key in node and isinstance(node[en_key], str) and node[en_key].strip():
                    node[k] = node[en_key]
            elif isinstance(v, (dict, list)):
                _localize_node(v, locale)
    elif isinstance(node, list):
        for item in node:
            _localize_node(item, locale)
    return node


def localize_ui_template(content: dict, locale: str) -> dict:
    """根据 locale 返回 UI.json 的本地化版本。空 dict 直接返回。"""
    if not content:
        return content
    if not _is_english(locale):
        return content
    return _localize_node(content, locale)
