"""概览工作区(P3 余下):聚合知识库健康摘要。

汇总页面/资料/构建/检查/关系等统计,供前端"概览"工作区与质量看板使用。
纯聚合查询,跨 DB 可用;图谱社区/孤立数复用 graph_service。
"""

from django.db.models import Count

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, PageRelation
from apps.opspilot.services.wiki.graph_service import build_graph


def _group_count(queryset, field):
    return {row[field]: row["c"] for row in queryset.values(field).annotate(c=Count("id"))}


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
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in BuildRecord.objects.filter(knowledge_base=kb).order_by("-id")[:5]
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
        },
        "recent_builds": recent_builds,
    }
