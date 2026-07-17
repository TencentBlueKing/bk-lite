"""_recount_pending_review 行为锁定(Issue: 列表显示 待审批 25 但 CheckTab 已审完)。

BuildRecord.counts.pending_review 是构建时的快照。后续 accept/reject/resolve
check 时只改 CheckItem.status,从不回写 counts,导致列表展示的 pending_review
永远是构建时的值。

修复:在 4 个 check 处理函数(accept_candidate/reject_candidate/resolve_check/
_merge_pages)末尾调 _recount_pending_review(check),按 check.candidate_version
关联 build(无 candidate 时按 KB 全 build 回算)重新数 open 检查项数。

revert 修复后,所有测试的"after close check, build.counts.pending_review
= N-1"断言会失败。
"""

import pytest

from apps.opspilot.models import BuildRecord, WikiKnowledgeBase
from apps.opspilot.services.wiki.check_service import accept_candidate, create_candidate, reject_candidate
from apps.opspilot.services.wiki.page_service import create_manual_page


def _make_kb_with_build(pending_review=3):
    """建一个 KB + BuildRecord(counts.pending_review=pending_review) 用于测试。"""
    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        counts={"new": 1, "updated": 0, "unchanged": 0, "pending_review": pending_review},
    )
    return kb, build


def _make_page(kb, title="T", body="v1"):
    return create_manual_page(kb, page_type="concept", title=title, body=body, created_by="u")


def _build_with_candidate(kb, body):
    """建页 + 创建候选 + check,返回 (build, check) — 用于 accept/reject 测试。"""
    page = _make_page(kb, body=body)
    check = create_candidate(page, body="candidate body", reason="conflict", check_type="conflict", created_by="ai")
    return check


@pytest.mark.django_db
def test_accept_candidate_decrements_pending_review():
    """accept_candidate 后 build.counts.pending_review 必须 -1。

    场景: build 下挂 2 个 check(open),accept 其中 1 个,期望 counts 减为 1。
    """
    kb, build = _make_kb_with_build(pending_review=2)
    # 建 2 个 page + 2 个 candidate check,都挂到同一 build
    check_a = _build_with_candidate(kb, body="c-a")
    check_b = _build_with_candidate(kb, body="c-b")
    for c in (check_a, check_b):
        c.candidate_version.build_record = build
        c.candidate_version.save()

    accept_candidate(check_a, operator="u")

    build.refresh_from_db()
    assert build.counts["pending_review"] == 1, f"accept 后 counts.pending_review 应为 1,实际 {build.counts['pending_review']}"


@pytest.mark.django_db
def test_reject_candidate_decrements_pending_review():
    """reject_candidate 后 build.counts.pending_review 必须 -1。"""
    kb, build = _make_kb_with_build(pending_review=2)
    check_a = _build_with_candidate(kb, body="c-a")
    check_b = _build_with_candidate(kb, body="c-b")
    for c in (check_a, check_b):
        c.candidate_version.build_record = build
        c.candidate_version.save()

    reject_candidate(check_b, operator="u")

    build.refresh_from_db()
    assert build.counts["pending_review"] == 1


@pytest.mark.django_db
def test_automatic_check_with_no_candidate_recomputes_for_all_builds():
    """自动维护项没有 candidate_version 时，按 KB 全 build 重算待审批数。"""
    kb, build = _make_kb_with_build(pending_review=2)
    from apps.opspilot.services.wiki.check_service import _recount_pending_review, ensure_check

    page = _make_page(kb, title="orphan")
    target = ensure_check(kb, "orphan", page)[0]
    ensure_check(kb, "no_source", page)
    _recount_pending_review(target)

    build.refresh_from_db()
    assert build.counts["pending_review"] == 0


@pytest.mark.django_db
def test_recount_is_idempotent_when_no_change():
    """counts 值与实际一致时不应触发不必要的 save(避免 updated_at 噪声)。"""
    kb, build = _make_kb_with_build(pending_review=0)  # 已无 open check
    # 直接调 _recount_pending_review,不应写库
    from apps.opspilot.services.wiki.check_service import _recount_pending_review, ensure_check

    page = _make_page(kb)
    check = ensure_check(kb, "orphan", page)[0]
    # 模拟: counts 已经是 0(没有 candidate 关联 check),不应触发 recount save
    build.refresh_from_db()
    updated_at_before = build.updated_at
    _recount_pending_review(check)
    build.refresh_from_db()
    assert build.updated_at == updated_at_before, "counts 一致时不应写库"
    assert build.counts["pending_review"] == 0


@pytest.mark.django_db
def test_recount_updates_when_count_differs():
    """counts 与实际不符时必须更新。"""
    kb, build = _make_kb_with_build(pending_review=10)  # 故意错
    # 无 candidate 的自动维护记录走 KB fallback，应把 10 改回 0。
    from apps.opspilot.services.wiki.check_service import _recount_pending_review, ensure_check

    page = _make_page(kb)
    check = ensure_check(kb, "orphan", page)[0]
    _recount_pending_review(check)
    build.refresh_from_db()
    assert build.counts["pending_review"] == 0
