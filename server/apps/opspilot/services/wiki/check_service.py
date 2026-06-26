"""安全更新 + 检查/审核(P2)。

风险变更不污染当前有效版本:生成候选版本(PageVersion change_type=candidate, is_current=False)+ CheckItem。
审核动作:接受候选(置为当前并生成新版本)、拒绝(关闭检查)、忽略。
也提供系统检查扫描:孤立页面、缺来源等(MVP 子集)。
"""

from django.db import transaction

from apps.opspilot.models import CheckItem, KnowledgePage, PageEvidence, PageVersion


@transaction.atomic
def create_candidate(page, body, reason, check_type="cannot_merge", build_record=None, created_by="", related=None):
    """为风险变更创建候选版本 + 检查事项,不改动当前有效版本。"""
    last = page.page_versions.order_by("-no").first()
    next_no = (last.no + 1) if last else 1
    candidate = PageVersion.objects.create(
        page=page,
        no=next_no,
        body=body,
        change_type="candidate",
        is_current=False,
        build_record=build_record,
        created_by=created_by or "",
    )
    check = CheckItem.objects.create(
        knowledge_base=page.knowledge_base,
        check_type=check_type,
        status="open",
        related=related or {"pages": [page.id]},
        candidate_version=candidate,
        suggested_actions=["accept", "reject", "edit_accept"],
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
    page.save(update_fields=["current_version", "contribution", "updated_at"])
    check.status = "resolved"
    check.save(update_fields=["status", "updated_at"])
    return candidate


@transaction.atomic
def reject_candidate(check, operator=""):
    """拒绝候选版本:删除候选版本,关闭检查,当前有效版本不变。"""
    candidate = check.candidate_version
    check.status = "dismissed"
    check.candidate_version = None
    check.save(update_fields=["status", "candidate_version", "updated_at"])
    if candidate and not candidate.is_current:
        candidate.delete()
    return check


def scan_health(knowledge_base):
    """系统检查扫描(spec 4.5):孤立、缺有效来源、来源全部失效、过期、疑似重复、冲突、失效关系、低置信度。

    幂等:同类型同页面已存在 open 检查则不重复创建。返回新建的 CheckItem 列表。
    (冲突/低置信为规则启发式;「不符合 Schema」「重要知识缺失」需 schema→类型映射,不在规则扫描内,
    由构建期 cannot_merge 等覆盖无法安全合并类。)
    """
    from collections import defaultdict

    from apps.opspilot.models import PageRelation

    created = []
    kb = knowledge_base
    pages = list(KnowledgePage.objects.filter(knowledge_base=kb, status="active"))
    by_title = defaultdict(list)

    for page in pages:
        has_relation = page.relations_out.exists() or page.relations_in.exists()
        evidences = list(PageEvidence.objects.filter(page=page).select_related("material"))
        has_evidence = bool(evidences)
        by_title[(page.title or "").strip().lower()].append(page)

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

    # 失效关系:关系指向非 active 页面
    broken = PageRelation.objects.filter(from_page__knowledge_base=kb).exclude(to_page__status="active").select_related("from_page")
    for rel in broken:
        created += ensure_check(kb, "broken_relation", rel.from_page)

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
