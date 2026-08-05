"""Wiki 页面标题身份与别名规则。

构建、扫描、补链等链路都应复用这里的 canonical title 规则,避免
CMDB/配置平台 这类同一对象被重复生成页面或图谱节点。

页面身份使用 NFKC + Unicode 空白折叠 + casefold。所有页面状态共享
同一知识库级命名空间；写入方必须在 locked_unique_title 上下文内
完成创建或改名，确保知识库行锁覆盖冲突检查和最终写入。
"""

import re
import unicodedata
from contextlib import contextmanager

MAX_TITLE_LENGTH = 255
_COMPACT_TITLE_SEPARATORS = frozenset("-_./" + chr(92) + "（）()【】[]《》<>:：")


class InvalidWikiTitle(ValueError):
    """标题为空或超过持久化限制。"""


class WikiTitleConflict(ValueError):
    """同一知识库内存在规范化后等价的页面标题。"""

    def __init__(self, *, title, conflict_page_id, conflict_title, conflict_status):
        self.title = title
        self.conflict_page_id = conflict_page_id
        self.conflict_title = conflict_title
        self.conflict_status = conflict_status
        super().__init__(f"知识库内已存在同名页面：{conflict_title}")


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


def normalize_display_title(title):
    """返回可持久化的展示标题，保留大小写但统一兼容字符和空白。"""

    raw_value = str(title or "")
    if any(unicodedata.category(character) == "Cs" for character in raw_value):
        raise InvalidWikiTitle("页面标题包含无效 Unicode 字符")
    value = unicodedata.normalize("NFKC", raw_value)
    return " ".join(value.split())


def validate_display_title(title):
    value = normalize_display_title(title)
    if not value:
        raise InvalidWikiTitle("页面标题不能为空")
    if len(value) > MAX_TITLE_LENGTH:
        raise InvalidWikiTitle(f"页面标题不能超过 {MAX_TITLE_LENGTH} 个字符")
    return value


def title_identity_key(title):
    """知识库全局标题身份键；不移除标点，避免合并真实不同的标题。"""

    return normalize_display_title(title).casefold()


def compact_title_key(title):
    """别名匹配键；兼容历史规则，不作为页面唯一身份键使用。"""

    return "".join(
        character for character in normalize_display_title(title).casefold() if not character.isspace() and character not in _COMPACT_TITLE_SEPARATORS
    )


def title_variants(title):
    value = normalize_display_title(title)
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
        alias = normalize_display_title(alias)
        canonical = normalize_display_title(canonical)
        if not alias or not canonical:
            return
        aliases[compact_title_key(alias)] = canonical
        aliases[compact_title_key(canonical)] = canonical

    for alias, canonical in iter_generation_rule_aliases(getattr(kb, "generation_rules", {}) or {}):
        add_alias(alias, canonical)
    return aliases


def canonical_title(kb, title):
    title = normalize_display_title(title)
    if not title:
        return ""
    aliases = title_alias_map(kb)
    for variant in title_variants(title):
        canonical = aliases.get(compact_title_key(variant))
        if canonical:
            return canonical
    return title


def find_title_conflict(*, knowledge_base_id, title, exclude_page_id=None):
    """查找所有状态页面中的等价标题；调用方应已持有知识库行锁。"""

    from apps.opspilot.models import KnowledgePage

    identity_key = title_identity_key(title)
    queryset = KnowledgePage.objects.filter(knowledge_base_id=knowledge_base_id)
    if exclude_page_id is not None:
        queryset = queryset.exclude(pk=exclude_page_id)
    rows = queryset.values("id", "title", "status").iterator(chunk_size=500)
    for row in rows:
        if title_identity_key(row["title"]) == identity_key:
            return row
    return None


def assert_unique_title_locked(*, knowledge_base_id, title, exclude_page_id=None):
    """校验标题；必须与最终页面写入处于同一 KB 行锁事务。"""

    display_title = validate_display_title(title)
    conflict = find_title_conflict(
        knowledge_base_id=knowledge_base_id,
        title=display_title,
        exclude_page_id=exclude_page_id,
    )
    if conflict is not None:
        raise WikiTitleConflict(
            title=display_title,
            conflict_page_id=conflict["id"],
            conflict_title=conflict["title"],
            conflict_status=conflict["status"],
        )
    return display_title


@contextmanager
def locked_unique_title(*, knowledge_base, title, exclude_page_id=None):
    """锁定知识库并为页面创建/改名保留其全局标题命名空间。

    调用方必须在 yield 的上下文内完成页面写入；上下文结束后锁释放。
    返回 (locked_knowledge_base, normalized_display_title)。
    """

    from django.db import transaction

    from apps.opspilot.models import WikiKnowledgeBase

    knowledge_base_id = getattr(knowledge_base, "pk", knowledge_base)
    with transaction.atomic():
        locked_knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
        display_title = assert_unique_title_locked(
            knowledge_base_id=locked_knowledge_base.pk,
            title=title,
            exclude_page_id=exclude_page_id,
        )
        yield locked_knowledge_base, display_title


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
