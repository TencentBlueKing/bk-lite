"""概览工作区(P3 余下):聚合知识库健康摘要。

汇总页面/资料/构建/检查/关系等统计,供前端"概览"工作区与质量看板使用。
纯聚合查询,跨 DB 可用;图谱社区/孤立数复用 graph_service。
"""

from django.db.models import Count
from django.utils import timezone

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, LLMSkill, Material, PageEvidence, PageRelation
from apps.opspilot.services.wiki.graph_service import build_graph


def _group_count(queryset, field):
    return {row[field]: row["c"] for row in queryset.values(field).annotate(c=Count("id"))}


def _agents_using(kb):
    """使用该知识库的智能体(LLMSkill.wiki_knowledge_bases);字段缺失时优雅返回空。"""
    try:
        return [{"id": s.id, "name": s.name} for s in LLMSkill.objects.filter(wiki_knowledge_bases=kb).order_by("id")[:20]]
    except Exception:
        return []


def get_overview(knowledge_base):
    """返回知识库概览 {knowledge_base, counts, contribution, material_status, checks_by_type, health, recent_builds}。"""
    kb = knowledge_base
    pages = KnowledgePage.objects.filter(knowledge_base=kb, status="active")
    materials = Material.objects.filter(knowledge_base=kb)
    open_checks = CheckItem.objects.filter(knowledge_base=kb, status="open")
    relations = PageRelation.objects.filter(from_page__knowledge_base=kb)

    graph = build_graph(kb)
    insights = graph["insights"]

    recent_builds = [
        {
            "id": b.id,
            "trigger": b.trigger,
            "status": b.status,
            "stage": b.stage,
            "counts": b.counts,
            "created_at": timezone.localtime(b.created_at).isoformat() if b.created_at else None,
        }
        for b in BuildRecord.objects.filter(knowledge_base=kb).order_by("-id")[:5]
    ]

    # 有效来源覆盖率:有「有效资料」证据支撑的知识页面占比(资料未解析失败/未失效)
    total_pages = pages.count()
    invalid_material_ids = list(materials.filter(status__in=["failed", "invalid"]).values_list("id", flat=True))
    pages_with_valid_source = (
        PageEvidence.objects.filter(page__knowledge_base=kb, page__status="active")
        .exclude(material_id__in=invalid_material_ids)
        .values("page_id")
        .distinct()
        .count()
    )
    source_coverage = round(pages_with_valid_source / total_pages * 100) if total_pages else 0

    recent_pages = [
        {
            "id": p.id,
            "title": p.title,
            "page_type": p.page_type,
            "contribution": p.contribution,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in pages.order_by("-updated_at")[:5]
    ]

    return {
        "knowledge_base": {"id": kb.id, "name": kb.name, "status": kb.status},
        "counts": {
            "pages": pages.count(),
            "materials": materials.count(),
            "build_records": BuildRecord.objects.filter(knowledge_base=kb).count(),
            "open_checks": open_checks.count(),
            "relations": relations.count(),
        },
        "contribution": _group_count(pages, "contribution"),
        "material_status": _group_count(materials, "status"),
        "checks_by_type": _group_count(open_checks, "check_type"),
        "health": {
            "open_checks": open_checks.count(),
            "clusters": insights["cluster_count"],
            "isolated": len(insights["isolated"]),
            "hubs": insights["hubs"],
            "source_coverage": source_coverage,
        },
        "recent_builds": recent_builds,
        "recent_pages": recent_pages,
        "agents": _agents_using(kb),
    }
