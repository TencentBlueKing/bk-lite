"""安全更新 + 检查/审核(P2)。

风险变更不污染当前有效版本:生成候选版本(PageVersion change_type=candidate, is_current=False)+ CheckItem。
审核动作:接受候选(置为当前并生成新版本)、拒绝(关闭检查)、忽略。
也提供系统检查扫描:孤立页面、缺来源等(MVP 子集)。
"""

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.opspilot.models import CheckItem, KnowledgePage, PageEvidence, PageRelation, PageVersion
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.embedding_service import clear_page_vectors
from apps.opspilot.services.wiki.graph_service import analyze_graph
from apps.opspilot.services.wiki.relation_service import LINK_RE, normalize_wikilink_key
from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key


@transaction.atomic
def create_candidate(
    page,
    body,
    reason,
    check_type="cannot_merge",
    build_record=None,
    created_by="",
    related=None,
    suggested_actions=None,
    change_type="candidate",
    meta_snapshot=None,
):
    """为风险变更创建候选版本 + 检查事项,不改动当前有效版本。"""
    last = page.page_versions.order_by("-no").first()
    next_no = (last.no + 1) if last else 1
    candidate = PageVersion.objects.create(
        page=page,
        no=next_no,
        body=body,
        change_type=change_type,
        is_current=False,
        build_record=build_record,
        created_by=created_by or "",
        meta_snapshot=meta_snapshot or {},
    )
    check = CheckItem.objects.create(
        knowledge_base=page.knowledge_base,
        check_type=check_type,
        status="open",
        related=related or {"pages": [page.id]},
        candidate_version=candidate,
        suggested_actions=suggested_actions or ["accept", "reject", "edit_accept"],
    )
    return check


@transaction.atomic
def accept_candidate(check, operator=""):
    """接受候选版本:置为当前有效版本,关闭检查。"""
    candidate = check.candidate_version
    if not candidate:
        raise ValueError("check has no candidate_version")
    page = candidate.page
    page.page_versions.filter(is_current=True).update(is_current=False)
    candidate.is_current = True
    candidate.save(update_fields=["is_current"])
    page.current_version = candidate
    if page.contribution == "human":
        page.contribution = "mixed"
    update_fields = ["current_version", "contribution", "updated_at"]
    if page.status != "active":
        page.status = "active"
        update_fields.append("status")
    if candidate.change_type == "qa_answer_candidate":
        page.update_method = "qa_answer"
        update_fields.append("update_method")
    page.save(update_fields=update_fields)
    check.status = "resolved"
    check.save(update_fields=["status", "updated_at"])
    maintenance = cascade(page.knowledge_base, [page.id], "accept")
    if candidate.build_record_id:
        candidate.build_record.maintenance = maintenance
        candidate.build_record.save(update_fields=["maintenance", "updated_at"])
    return candidate


@transaction.atomic
def reject_candidate(check, operator=""):
    """拒绝候选版本:删除候选版本,关闭检查,当前有效版本不变。"""
    candidate = check.candidate_version
    check.status = "dismissed"
    check.candidate_version = None
    check.save(update_fields=["status", "candidate_version", "updated_at"])
    if candidate and not candidate.is_current:
        page = candidate.page
        delete_shell_page = page.current_version_id is None and not page.page_versions.exclude(id=candidate.id).exists()
        candidate.delete()
        if delete_shell_page:
            page.delete()
    return check


@transaction.atomic
def resolve_check(check, operator="", note=""):
    """将无需候选版本的检查项标记为已处理,并记录处理结果。"""
    if check.status != "open":
        raise ValueError("only open checks can be resolved")
    if check.candidate_version_id:
        raise ValueError("candidate checks must be accepted or rejected")
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["resolution"] = {
        "action": "manual_resolve",
        "operator": operator or "",
        "note": note or "",
        "processed_at": timezone.now().isoformat(),
    }
    check.related = related
    check.status = "resolved"
    check.save(update_fields=["related", "status", "updated_at"])
    return check


def _related_pages_for_merge(check):
    related = check.related if isinstance(check.related, dict) else {}
    page_ids = related.get("pages", []) or []
    ordered_ids = []
    seen = set()
    for page_id in page_ids:
        try:
            parsed = int(page_id)
        except (TypeError, ValueError):
            continue
        if parsed in seen:
            continue
        ordered_ids.append(parsed)
        seen.add(parsed)
    pages = {
        page.id: page
        for page in KnowledgePage.objects.filter(
            knowledge_base=check.knowledge_base,
            id__in=ordered_ids,
            status="active",
        ).select_related("current_version")
    }
    return [pages[page_id] for page_id in ordered_ids if page_id in pages]


def _merge_target(check, pages):
    related = check.related if isinstance(check.related, dict) else {}
    canonical = (related.get("canonical_title") or "").strip()
    if canonical:
        canonical_key = compact_title_key(canonical)
        for page in pages:
            if compact_title_key(page.title) == canonical_key:
                return page, canonical
    return pages[0], canonical


def _merged_duplicate_body(target, sources):
    pieces = []
    current = (target.current_version.body if target.current_version_id else "") or ""
    if current.strip():
        pieces.append(current.strip())
    for source in sources:
        body = (source.current_version.body if source.current_version_id else "") or ""
        body = body.strip()
        if not body or body in pieces:
            continue
        pieces.append(f"## 合并自: {source.title}\n\n{body}")
    return "\n\n".join(pieces).strip()


def _move_page_evidence(target, sources):
    moved = 0
    for evidence in PageEvidence.objects.filter(page__in=sources):
        exists = PageEvidence.objects.filter(
            page=target,
            material_id=evidence.material_id,
            material_version_id=evidence.material_version_id,
            locator=evidence.locator,
        ).exists()
        if exists:
            evidence.delete()
            continue
        evidence.page = target
        evidence.save(update_fields=["page", "updated_at"])
        moved += 1
    return moved


@transaction.atomic
def merge_duplicate_check(check, operator=""):
    """处理同义/重复页检查:合并到规范标题页,旧页归档并触发增量维护。"""
    if check.check_type != "duplicate":
        raise ValueError("only duplicate checks can be merged")
    if check.status != "open":
        raise ValueError("only open checks can be merged")

    pages = _related_pages_for_merge(check)
    if len(pages) < 2:
        raise ValueError("duplicate check requires at least two active related pages")

    target, canonical = _merge_target(check, pages)
    sources = [page for page in pages if page.id != target.id]
    source_ids = [page.id for page in sources]
    source_titles = [page.title for page in sources]
    body = _merged_duplicate_body(target, sources)
    target.page_versions.filter(is_current=True).update(is_current=False)
    last = target.page_versions.order_by("-no").first()
    version = PageVersion.objects.create(
        page=target,
        no=(last.no + 1) if last else 1,
        body=body,
        change_type="merge_duplicate",
        is_current=True,
        created_by=operator or "",
        meta_snapshot={
            "merged_page_ids": source_ids,
            "merged_titles": source_titles,
            "canonical_title": canonical or target.title,
        },
    )
    if canonical:
        target.title = canonical
    target.current_version = version
    target.tags = list(dict.fromkeys(sum((page.tags or [] for page in pages), [])))
    target.status = "active"
    target.contribution = "mixed"
    target.update_method = "merge_duplicate"
    target.updated_by = operator or ""
    target.save(
        update_fields=[
            "title",
            "tags",
            "current_version",
            "status",
            "contribution",
            "update_method",
            "updated_by",
            "updated_at",
        ]
    )

    for source in sources:
        source.status = "archived"
        source.update_method = "merge_duplicate"
        source.updated_by = operator or ""
        source.save(update_fields=["status", "update_method", "updated_by", "updated_at"])

    moved_evidence = _move_page_evidence(target, sources)
    clear_page_vectors(source_ids)
    related = dict(check.related) if isinstance(check.related, dict) else {}
    related["merged_into"] = target.id
    related["archived_pages"] = source_ids
    check.related = related
    check.status = "resolved"
    check.save(update_fields=["related", "status", "updated_at"])
    maintenance = cascade(
        check.knowledge_base,
        [target.id, *source_ids],
        "merge_duplicate",
        deleted_titles=source_titles,
    )
    return {
        "target_page_id": target.id,
        "archived_page_ids": source_ids,
        "moved_evidence": moved_evidence,
        "maintenance": maintenance,
    }


def scan_health(knowledge_base):
    """系统检查扫描(spec 4.5):孤立、缺有效来源、来源全部失效、过期、疑似重复、冲突、失效关系、低置信度。

    幂等:同类型同页面已存在 open 检查则不重复创建。返回新建的 CheckItem 列表。
    (冲突/低置信为规则启发式;「不符合 Schema」「重要知识缺失」需 schema→类型映射,不在规则扫描内,
    由构建期 cannot_merge 等覆盖无法安全合并类。)
    """
    created = []
    kb = knowledge_base
    pages = list(KnowledgePage.objects.filter(knowledge_base=kb, status="active"))
    by_title = defaultdict(list)
    by_canonical_title = defaultdict(list)
    canonical_titles = {}

    for page in pages:
        has_relation = page.relations_out.exists() or page.relations_in.exists()
        evidences = list(PageEvidence.objects.filter(page=page).select_related("material"))
        has_evidence = bool(evidences)
        by_title[(page.title or "").strip().lower()].append(page)
        canonical = canonical_title(kb, page.title)
        canonical_key = (canonical or "").strip().lower()
        if canonical_key:
            by_canonical_title[canonical_key].append(page)
            canonical_titles[canonical_key] = canonical

        # 孤立:既无关系也无证据
        if not has_relation and not has_evidence:
            created += ensure_check(kb, "orphan", page)
        # 纯 AI 页面无证据 → 缺来源
        elif page.contribution == "ai" and not has_evidence:
            created += ensure_check(kb, "no_source", page)

        # 来源全部失效:有证据但所有证据资料均失效/解析失败
        if has_evidence and all(e.material.status in ("failed", "invalid") for e in evidences):
            created += ensure_check(kb, "all_sources_invalid", page)
        # 过期:证据资料处于「已更新待重建」
        if any(e.material.status == "updated" for e in evidences):
            created += ensure_check(kb, "stale", page)
        # 低置信:AI 页面正文过短
        cur = page.current_version
        if page.contribution == "ai" and cur and len((cur.body or "").strip()) < 30:
            created += ensure_check(kb, "low_confidence", page)

    # 同标题成组:同类型 → 疑似重复;不同类型 → 冲突
    for title, group in by_title.items():
        if not title or len(group) < 2:
            continue
        check_type = "conflict" if len({p.page_type for p in group}) > 1 else "duplicate"
        # 整组同标题页面放进同一条检查的 related,便于在审核详情里并列对比(而非每页一条只看到一页)。
        # ensure_check 幂等:首个页面创建含全组的检查,组内其余页面命中后跳过 → 每组一条。
        group_ids = [p.id for p in group]
        for page in group:
            created += ensure_check(kb, check_type, page, related={"pages": group_ids})

    # 规范标题成组:标题不同但归一到同一 canonical title → 疑似同义重复。
    for canonical_key, group in by_canonical_title.items():
        if not canonical_key or len(group) < 2:
            continue
        title_keys = {(p.title or "").strip().lower() for p in group if (p.title or "").strip()}
        if len(title_keys) < 2:
            continue
        check_type = "conflict" if len({p.page_type for p in group}) > 1 else "duplicate"
        related = {"pages": [p.id for p in group], "canonical_title": canonical_titles[canonical_key]}
        for page in group:
            created += ensure_check(kb, check_type, page, related=related)

    # 失效关系:关系指向非 active 页面
    broken = PageRelation.objects.filter(from_page__knowledge_base=kb).exclude(to_page__status="active").select_related("from_page")
    for rel in broken:
        created += ensure_check(kb, "broken_relation", rel.from_page)

    created += _missing_wikilink_checks(kb, pages)
    created += _graph_insight_checks(kb)
    return created


def _missing_wikilink_checks(knowledge_base, pages):
    active_keys = set()
    for page in pages:
        active_keys.add(normalize_wikilink_key(page.title))
        canonical = canonical_title(knowledge_base, page.title)
        if canonical:
            active_keys.add(normalize_wikilink_key(canonical))

    missing = {}
    for page in pages:
        body = page.current_version.body if page.current_version_id else ""
        for match in LINK_RE.finditer(body or ""):
            target = match.group(1).strip()
            canonical = canonical_title(knowledge_base, target)
            target_keys = {normalize_wikilink_key(target)}
            if canonical:
                target_keys.add(normalize_wikilink_key(canonical))
            target_keys = {key for key in target_keys if key}
            if not target_keys or active_keys & target_keys:
                continue
            target_key = sorted(target_keys)[0]
            item = missing.setdefault(target_key, {"target": canonical or target, "page_ids": set(), "source_titles": set()})
            item["page_ids"].add(page.id)
            item["source_titles"].add(page.title)

    created = []
    for target_key, item in sorted(missing.items()):
        page_ids = sorted(item["page_ids"])
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type="missing",
            status="open",
            related__target_key=target_key,
        ).exists()
        if exists or not page_ids:
            continue
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="missing",
                status="open",
                related={
                    "pages": page_ids,
                    "graph_insight": "knowledge_gap",
                    "target": item["target"],
                    "target_key": target_key,
                    "suggested_queries": _missing_suggested_queries(item["target"], item["source_titles"]),
                },
                suggested_actions=["create_page", "supplement_source", "dismiss"],
            )
        )
    return created


def _missing_suggested_queries(target, source_titles):
    queries = []
    target = (target or "").strip()
    if target:
        queries.append(target)
    for title in sorted(source_titles or []):
        title = (title or "").strip()
        if not title or not target:
            continue
        queries.append(f"{title} {target}")
    return list(dict.fromkeys(queries))


def _graph_insight_checks(knowledge_base):
    graph = analyze_graph(knowledge_base)
    insights = graph.get("insights") or {}
    sparse_page_ids = [page_id for community in insights.get("sparse_communities", []) for page_id in community.get("page_ids", []) if page_id]
    cross_edge_page_ids = [page_id for edge in insights.get("cross_community_edges", []) for page_id in (edge.get("from"), edge.get("to")) if page_id]
    pages = {
        page.id: page
        for page in KnowledgePage.objects.filter(
            knowledge_base=knowledge_base,
            status="active",
            id__in=[
                *[item.get("id") for item in insights.get("bridge_nodes", []) if item.get("id")],
                *sparse_page_ids,
                *cross_edge_page_ids,
            ],
        )
    }
    created = []
    for item in insights.get("bridge_nodes", []):
        page = pages.get(item.get("id"))
        if not page:
            continue
        related = {
            "pages": [page.id],
            "graph_insight": "bridge_node",
            "degree": item.get("degree", 0),
            "component_count_after_removal": item.get("component_count_after_removal", 0),
        }
        created += ensure_check(
            knowledge_base,
            "bridge_node",
            page,
            suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            related=related,
        )
    for item in insights.get("cross_community_edges", []):
        page_ids = sorted(page_id for page_id in [item.get("from"), item.get("to")] if page_id in pages)
        if len(page_ids) != 2:
            continue
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type="cross_community_edge",
            status="open",
            related__pages__contains=page_ids,
        ).exists()
        if exists:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "cross_community_edge",
            "from": item.get("from"),
            "to": item.get("to"),
            "from_title": item.get("from_title", ""),
            "to_title": item.get("to_title", ""),
            "weight": item.get("weight", 0),
            "signals": item.get("signals", {}),
            "from_community": item.get("from_community", -1),
            "to_community": item.get("to_community", -1),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="cross_community_edge",
                status="open",
                related=related,
                suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            )
        )
    for item in insights.get("sparse_communities", []):
        page_ids = [page_id for page_id in item.get("page_ids", []) if page_id in pages]
        if not page_ids:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "sparse_community",
            "density": item.get("density", 0),
            "edge_count": item.get("edge_count", 0),
            "possible_edges": item.get("possible_edges", 0),
        }
        created += ensure_check(
            knowledge_base,
            "sparse_community",
            pages[page_ids[0]],
            suggested_actions=["review_graph", "supplement_source", "restructure_page"],
            related=related,
        )
    # 惊奇连接:跨社区强边且两侧标题不共享显著词
    for item in insights.get("surprise_links", []):
        page_ids = sorted(page_id for page_id in [item.get("from"), item.get("to")] if page_id in pages)
        if len(page_ids) != 2:
            continue
        exists = CheckItem.objects.filter(
            knowledge_base=knowledge_base,
            check_type="surprise_link",
            status="open",
            related__pages__contains=page_ids,
        ).exists()
        if exists:
            continue
        related = {
            "pages": page_ids,
            "graph_insight": "surprise_link",
            "from": item.get("from"),
            "to": item.get("to"),
            "from_title": item.get("from_title", ""),
            "to_title": item.get("to_title", ""),
            "weight": item.get("weight", 0),
            "signals": item.get("signals", {}),
            "from_community": item.get("from_community", -1),
            "to_community": item.get("to_community", -1),
        }
        created.append(
            CheckItem.objects.create(
                knowledge_base=knowledge_base,
                check_type="surprise_link",
                status="open",
                related=related,
                suggested_actions=["review_graph", "restructure_page", "supplement_source"],
            )
        )
    return created


def ensure_check(knowledge_base, check_type, page, suggested_actions=None, related=None):
    """幂等创建检查事项:同库同类型同页面已有 open 检查则不重复。返回新建列表。

    related 可显式传入(如重复/冲突整组页面);缺省为仅本页 {"pages": [page.id]}。
    """
    exists = CheckItem.objects.filter(
        knowledge_base=knowledge_base, check_type=check_type, status="open", related__pages__contains=[page.id]
    ).exists()
    if exists:
        return []
    return [
        CheckItem.objects.create(
            knowledge_base=knowledge_base,
            check_type=check_type,
            status="open",
            related=related or {"pages": [page.id]},
            suggested_actions=suggested_actions or ["dismiss", "supplement_source"],
        )
    ]
