"""概览工作区(P3 余下):聚合知识库健康摘要。

汇总页面/资料/构建/检查/关系等统计,供前端"概览"工作区与质量看板使用。
纯聚合查询,跨 DB 可用;图谱社区/孤立数复用 graph_service。
"""

from django.db.models import Count
from django.utils import timezone

from apps.opspilot.models import BuildRecord, CheckItem, LLMSkill, Material, PageEvidence
from apps.opspilot.services.wiki.active_generation_query_service import (
    assert_read_scope_current,
    bind_read_scope,
    page_queryset,
    page_snapshot,
    relation_queryset,
)
from apps.opspilot.services.wiki.graph_service import build_graph

_DECISION_CHECK_TYPES = (
    "cannot_merge",
    "material_update",
    "duplicate",
    "conflict",
)


def _group_count(queryset, field):
    return {row[field]: row["c"] for row in queryset.values(field).annotate(c=Count("id"))}


def _value_count(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _agents_using(kb):
    """使用该知识库的智能体(LLMSkill.wiki_knowledge_bases);字段缺失时优雅返回空。"""
    try:
        return [{"id": s.id, "name": s.name} for s in LLMSkill.objects.filter(wiki_knowledge_bases=kb).order_by("id")[:20]]
    except Exception:
        return []


def get_overview(knowledge_base):
    """返回知识库概览 {knowledge_base, counts, contribution, material_status, checks_by_type, health, recent_builds}。"""
    kb = knowledge_base
    read_scope = bind_read_scope(kb)
    page_rows = list(page_queryset(kb, statuses=("active",), read_scope=read_scope).order_by("-updated_at", "-id"))
    page_snapshots = [(page, page_snapshot(page, knowledge_base=kb)) for page in page_rows]
    active_page_ids = [snapshot.page_id for _page, snapshot in page_snapshots]
    materials = Material.objects.filter(knowledge_base=kb)
    open_checks = CheckItem.objects.filter(
        knowledge_base=kb,
        status="open",
        check_type__in=_DECISION_CHECK_TYPES,
    )
    relations = relation_queryset(kb, read_scope=read_scope)

    graph = build_graph(kb, read_scope=read_scope)
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
    total_pages = len(page_snapshots)
    invalid_material_ids = list(materials.filter(status__in=["failed", "invalid"]).values_list("id", flat=True))
    pages_with_valid_source = (
        PageEvidence.objects.filter(page_id__in=active_page_ids).exclude(material_id__in=invalid_material_ids).values("page_id").distinct().count()
    )
    source_coverage = round(pages_with_valid_source / total_pages * 100) if total_pages else 0

    recent_pages = [
        {
            "id": page.id,
            "title": snapshot.title,
            "page_type": snapshot.page_type,
            "contribution": snapshot.contribution,
            "directory_id": snapshot.directory_id,
            "directory_key": snapshot.directory_key,
            "directory_breadcrumb": list(snapshot.directory_breadcrumb),
            "generation_id": snapshot.generation_id,
            "updated_at": page.updated_at.isoformat() if page.updated_at else None,
        }
        for page, snapshot in page_snapshots[:5]
    ]

    result = {
        "knowledge_base": {"id": kb.id, "name": kb.name, "status": kb.status},
        "generation_id": read_scope.generation_id,
        "counts": {
            "pages": total_pages,
            "materials": materials.count(),
            "build_records": BuildRecord.objects.filter(knowledge_base=kb).count(),
            "open_checks": open_checks.count(),
            "relations": relations.count(),
        },
        "contribution": _value_count(snapshot.contribution for _page, snapshot in page_snapshots),
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
    assert_read_scope_current(read_scope)
    return result
