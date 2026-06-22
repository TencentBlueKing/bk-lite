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
    """系统检查扫描(MVP 子集):孤立页面(无关系且无证据)、缺有效来源。

    幂等:同类型同页面已存在 open 检查则不重复创建。返回新建的 CheckItem 列表。
    """
    created = []
    pages = KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active")
    for page in pages:
        has_relation = page.relations_out.exists() or page.relations_in.exists()
        has_evidence = PageEvidence.objects.filter(page=page).exists()
        # 孤立:既无关系也无证据
        if not has_relation and not has_evidence:
            created += ensure_check(knowledge_base, "orphan", page)
        # 纯 AI 页面无证据 → 缺来源
        elif page.contribution == "ai" and not has_evidence:
            created += ensure_check(knowledge_base, "no_source", page)
    return created


def ensure_check(knowledge_base, check_type, page, suggested_actions=None):
    """幂等创建检查事项:同库同类型同页面已有 open 检查则不重复。返回新建列表。"""
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
            related={"pages": [page.id]},
            suggested_actions=suggested_actions or ["dismiss", "supplement_source"],
        )
    ]
