"""AD 用户同步拉取 DN 规范化。

规范形态为 root_dns 列表；兼容旧字段 root_dn（单字符串或多行文本）。
"""

from __future__ import annotations

AD_LOCAL_ROOT_SCOPE_ID = "__local_root__"
AD_ROOT_DNS_FIELD = "root_dns"
AD_LEGACY_ROOT_DN_FIELD = "root_dn"


def normalize_ad_pull_dns(business_config: dict | None) -> list[str]:
    """从 business_config 得到去空、去重、去掉被覆盖子孙后的拉取 DN 列表。"""
    config = business_config or {}
    raw = config.get(AD_ROOT_DNS_FIELD)
    if raw in (None, ""):
        raw = config.get(AD_LEGACY_ROOT_DN_FIELD)

    items: list[str] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            items.extend(_split_dn_text(item))
    elif raw is not None:
        items.extend(_split_dn_text(raw))

    deduped: list[str] = []
    seen_lower: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        deduped.append(item)

    return _drop_covered_descendant_dns(deduped)


def resolve_ad_local_root_scope_id(pull_dns: list[str]) -> str:
    """单个拉取 DN 时返回该 DN（折进本地根）；多个时返回合成本地根标识。"""
    if not pull_dns:
        return ""
    if len(pull_dns) == 1:
        return pull_dns[0]
    return AD_LOCAL_ROOT_SCOPE_ID


def is_ad_multi_pull(pull_dns: list[str]) -> bool:
    return len(pull_dns) > 1


def _split_dn_text(value) -> list[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _is_descendant_dn(candidate: str, ancestor: str) -> bool:
    candidate_lower = candidate.lower()
    ancestor_lower = ancestor.lower()
    if candidate_lower == ancestor_lower:
        return False
    return candidate_lower.endswith("," + ancestor_lower)


def _drop_covered_descendant_dns(pull_dns: list[str]) -> list[str]:
    kept: list[str] = []
    for dn in pull_dns:
        if any(_is_descendant_dn(dn, other) for other in pull_dns):
            continue
        kept.append(dn)
    return kept
