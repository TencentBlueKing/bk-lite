"""页面关系识别(P1):从确定性信号派生 PageRelation(无需 LLM)。

信号(MVP 子集):
- shared_source:两页面共享 ≥1 资料(PageEvidence)→ 无向关系(只存一条,from=小 id),
  weight=共享资料数,via_material=共享资料中 id 最小者。
- reference:页面正文以 [[标题]] 引用同库另一页面 → 有向关系。

AI 语义关联(ai_identified)、4 信号关联度 + 社区发现留待 P5。
rebuild_relations 幂等:重建前清掉该库现有关系。
"""

import re
from itertools import combinations

from django.db import transaction
from django.db.models import Q

from apps.opspilot.models import KnowledgePage, PageEvidence, PageRelation
from apps.opspilot.services.wiki.title_service import canonical_title

LINK_RE = re.compile(r"\[\[\s*([^\]|\n]+?)(?:\|([^\]\n]*))?\s*\]\]")


def normalize_wikilink_key(value):
    """Normalize title/slug-style WikiLink targets for matching."""
    normalized = (value or "").strip().replace("\\", "/")
    leaf = normalized.rsplit("/", 1)[-1]
    if leaf.lower().endswith(".md"):
        leaf = leaf[:-3]
    return re.sub(r"[\s\-_]+", "", leaf.lower())


def _page_match_keys(page):
    keys = {normalize_wikilink_key(page.title)}
    canonical = canonical_title(page.knowledge_base, page.title)
    if canonical:
        keys.add(normalize_wikilink_key(canonical))
    return {key for key in keys if key}


def _target_match_keys(knowledge_base, title):
    keys = {normalize_wikilink_key(title)}
    canonical = canonical_title(knowledge_base, title)
    if canonical:
        keys.add(normalize_wikilink_key(canonical))
    return {key for key in keys if key}


def _page_lookups(pages):
    by_title = {}
    by_key = {}
    for page in pages:
        by_title.setdefault((page.title or "").strip(), []).append(page)
        for key in _page_match_keys(page):
            by_key.setdefault(key, []).append(page)
    return by_title, by_key


def _lookup_candidates(by_title, by_key, knowledge_base, title):
    exact = by_title.get(title)
    if exact:
        return exact
    candidates = []
    seen = set()
    for key in _target_match_keys(knowledge_base, title):
        for page in by_key.get(key, []):
            if page.id in seen:
                continue
            candidates.append(page)
            seen.add(page.id)
    return candidates


@transaction.atomic
def rebuild_relations(knowledge_base):
    """重建某知识库的页面关系,返回新建的 PageRelation 列表。"""
    pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active"))
    PageRelation.objects.filter(from_page__knowledge_base=knowledge_base).delete()
    created = []
    created += _shared_source(pages)
    created += _references(pages)
    return created


@transaction.atomic
def sync_relations_for_pages(knowledge_base, page_ids=None, deleted_titles=None):
    """增量同步受影响页面的关系。

    只删除/重建与 affected page 直接相关的边;不会清空整个知识库关系。
    deleted_titles 用于页面删除/改名后,把仍指向旧标题的 WikiLink 标记为 broken_relation。
    """
    affected_ids = {int(page_id) for page_id in (page_ids or []) if page_id}
    deleted_keys = {normalize_wikilink_key(title) for title in (deleted_titles or []) if title}
    active_pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version"))
    affected_pages = [page for page in active_pages if page.id in affected_ids]

    if affected_ids:
        PageRelation.objects.filter(from_page__knowledge_base=knowledge_base).filter(
            Q(from_page_id__in=affected_ids) | Q(to_page_id__in=affected_ids)
        ).delete()

    created = []
    created += _shared_source_touching(affected_pages, active_pages)
    created += _references_touching(active_pages, active_pages, affected_ids, deleted_keys)
    return created


def _shared_source(pages):
    by_id = {p.id: p for p in pages}
    mats = {pid: set(PageEvidence.objects.filter(page_id=pid).values_list("material_id", flat=True)) for pid in by_id}
    created = []
    for a, b in combinations(sorted(by_id), 2):
        shared = mats[a] & mats[b]
        if shared:
            created.append(
                PageRelation.objects.create(
                    from_page=by_id[a],
                    to_page=by_id[b],
                    relation_type="shared_source",
                    weight=float(len(shared)),
                    via_material_id=min(shared),
                )
            )
    return created


def _references(pages):
    from apps.opspilot.services.wiki.check_service import ensure_check

    by_title, by_key = _page_lookups(pages)
    created = []
    for p in pages:
        body = p.current_version.body if p.current_version_id else ""
        seen = set()
        for match in LINK_RE.finditer(body or ""):
            title = match.group(1).strip()
            candidates = _lookup_candidates(by_title, by_key, p.knowledge_base, title)
            candidates = [candidate for candidate in candidates if candidate.id != p.id]
            if len(candidates) > 1:
                ensure_check(
                    p.knowledge_base,
                    "ambiguous_link",
                    p,
                    suggested_actions=["dismiss", "edit_page"],
                    related={"pages": [p.id] + [candidate.id for candidate in candidates], "target": title},
                )
                continue
            if not candidates:
                ensure_check(
                    p.knowledge_base,
                    "broken_relation",
                    p,
                    suggested_actions=["dismiss", "edit_page"],
                    related={"pages": [p.id], "target": title},
                )
                continue
            target = candidates[0]
            if target.id not in seen:
                seen.add(target.id)
                created.append(PageRelation.objects.create(from_page=p, to_page=target, relation_type="reference", weight=1.0))
    return created


def _shared_source_touching(affected_pages, all_pages):
    if not affected_pages:
        return []
    pages_by_id = {page.id: page for page in all_pages}
    material_ids_by_page = {
        page_id: set(PageEvidence.objects.filter(page_id=page_id).values_list("material_id", flat=True)) for page_id in pages_by_id
    }
    created = []
    seen_pairs = set()
    for page in affected_pages:
        for other in all_pages:
            if page.id == other.id:
                continue
            left_id, right_id = sorted([page.id, other.id])
            if (left_id, right_id) in seen_pairs:
                continue
            seen_pairs.add((left_id, right_id))
            shared = material_ids_by_page[left_id] & material_ids_by_page[right_id]
            if not shared:
                continue
            created.append(
                PageRelation.objects.create(
                    from_page=pages_by_id[left_id],
                    to_page=pages_by_id[right_id],
                    relation_type="shared_source",
                    weight=float(len(shared)),
                    via_material_id=min(shared),
                )
            )
    return created


def _references_touching(source_pages, all_pages, affected_ids, deleted_keys):
    from apps.opspilot.services.wiki.check_service import ensure_check

    by_title, by_key = _page_lookups(all_pages)

    created = []
    seen_relations = set()
    for source in source_pages:
        body = source.current_version.body if source.current_version_id else ""
        source_touched = source.id in affected_ids
        for match in LINK_RE.finditer(body or ""):
            title = match.group(1).strip()
            title_key = normalize_wikilink_key(title)
            candidates = _lookup_candidates(by_title, by_key, source.knowledge_base, title)
            candidates = [candidate for candidate in candidates if candidate.id != source.id]
            candidate_ids = {candidate.id for candidate in candidates}
            touches_affected = source_touched or bool(candidate_ids & affected_ids)

            if len(candidates) > 1:
                if touches_affected:
                    ensure_check(
                        source.knowledge_base,
                        "ambiguous_link",
                        source,
                        suggested_actions=["dismiss", "edit_page"],
                        related={"pages": [source.id] + [candidate.id for candidate in candidates], "target": title},
                    )
                continue
            if not candidates:
                if source_touched or title_key in deleted_keys:
                    ensure_check(
                        source.knowledge_base,
                        "broken_relation",
                        source,
                        suggested_actions=["dismiss", "edit_page"],
                        related={"pages": [source.id], "target": title},
                    )
                continue

            target = candidates[0]
            if not touches_affected:
                continue
            relation_key = (source.id, target.id, "reference")
            if relation_key in seen_relations:
                continue
            seen_relations.add(relation_key)
            created.append(PageRelation.objects.create(from_page=source, to_page=target, relation_type="reference", weight=1.0))
    return created


def list_relations(knowledge_base):
    """返回该库关系边列表(供校验与后续图谱使用)。"""
    qs = PageRelation.objects.filter(from_page__knowledge_base=knowledge_base).select_related("from_page", "to_page")
    return [
        {
            "from": r.from_page_id,
            "from_title": r.from_page.title,
            "to": r.to_page_id,
            "to_title": r.to_page.title,
            "relation_type": r.relation_type,
            "weight": r.weight,
        }
        for r in qs
    ]
