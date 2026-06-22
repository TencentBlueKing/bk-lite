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

from apps.opspilot.models import KnowledgePage, PageEvidence, PageRelation

LINK_RE = re.compile(r"\[\[\s*([^\[\]]+?)\s*\]\]")


@transaction.atomic
def rebuild_relations(knowledge_base):
    """重建某知识库的页面关系,返回新建的 PageRelation 列表。"""
    pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active"))
    PageRelation.objects.filter(from_page__knowledge_base=knowledge_base).delete()
    created = []
    created += _shared_source(pages)
    created += _references(pages)
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
    by_title = {p.title: p for p in pages}
    created = []
    for p in pages:
        body = p.current_version.body if p.current_version_id else ""
        seen = set()
        for title in LINK_RE.findall(body or ""):
            target = by_title.get(title.strip())
            if target and target.id != p.id and target.id not in seen:
                seen.add(target.id)
                created.append(PageRelation.objects.create(from_page=p, to_page=target, relation_type="reference", weight=1.0))
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
