"""Wiki 页面标题归一与别名规则。

构建、扫描、补链等链路都应复用这里的 canonical title 规则,避免
CMDB/配置平台 这类同一对象被重复生成页面或图谱节点。
"""

import re

COMMON_TITLE_ALIASES = {
    "cmdb": "配置平台",
    "配置平台": "配置平台",
    "job": "作业平台",
    "作业平台": "作业平台",
    "gse": "管控平台",
    "管控平台": "管控平台",
    "bkdata": "数据平台",
    "数据平台": "数据平台",
    "esb": "企业服务总线",
    "企业服务总线": "企业服务总线",
}


def compact_title_key(title):
    return re.sub(r"[\s\-_./\\（）()【】\[\]《》<>:：]+", "", (title or "").strip().lower())


def title_variants(title):
    value = (title or "").strip()
    if not value:
        return []
    variants = [value]
    match = re.fullmatch(r"(.+?)[（(]([^（）()]+)[）)]", value)
    if match:
        variants.extend([match.group(1).strip(), match.group(2).strip()])
    return [item for item in dict.fromkeys(variants) if item]


def iter_generation_rule_aliases(rules):
    raw = (rules or {}).get("title_aliases") or (rules or {}).get("titleAliases") or (rules or {}).get("aliases")
    if isinstance(raw, dict):
        for left, right in raw.items():
            if isinstance(right, str):
                yield left, right
            elif isinstance(right, (list, tuple)):
                for alias in right:
                    yield alias, left
        return
    if not isinstance(raw, (list, tuple)):
        return
    for item in raw:
        if isinstance(item, dict):
            canonical = item.get("canonical") or item.get("title") or item.get("name")
            for alias in item.get("aliases", []) or []:
                yield alias, canonical
        elif isinstance(item, (list, tuple)) and item:
            canonical = item[0]
            for alias in item:
                yield alias, canonical


def title_alias_map(kb):
    aliases = dict(COMMON_TITLE_ALIASES)

    def add_alias(alias, canonical):
        alias = (alias or "").strip()
        canonical = (canonical or "").strip()
        if not alias or not canonical:
            return
        aliases[compact_title_key(alias)] = canonical
        aliases[compact_title_key(canonical)] = canonical

    for alias, canonical in iter_generation_rule_aliases(getattr(kb, "generation_rules", {}) or {}):
        add_alias(alias, canonical)
    return aliases


def canonical_title(kb, title):
    title = (title or "").strip()
    if not title:
        return ""
    aliases = title_alias_map(kb)
    for variant in title_variants(title):
        canonical = aliases.get(compact_title_key(variant))
        if canonical:
            return canonical
    return title


def title_alias_terms_for_enrichment(kb, title):
    canonical_key = compact_title_key(canonical_title(kb, title))
    terms = set(title_variants(title))
    for alias, canonical in COMMON_TITLE_ALIASES.items():
        if compact_title_key(canonical) == canonical_key:
            terms.add(alias)
    for alias, canonical in iter_generation_rule_aliases(getattr(kb, "generation_rules", {}) or {}):
        if compact_title_key(canonical) == canonical_key:
            terms.add(alias)
    return [term for term in terms if term]
