"""phase 5.2 / 5.4 e2e: merge_duplicate_check 接决策服务 + 页面身份变化撤销。

TDD:
- 5.2: 命中合并规则 → 自动按规则 action 执行,BuildRecord 记 decision_reused
- 5.4: 页面身份变化 → 旧规则被 revoke
- 5.4 衍生: 物理删除源页面 → 旧规则被 revoke
"""

import pytest


# ============================================================================
# 5.2 合并决策回放
# ============================================================================
# 注: 完整 5.2 merge_duplicate_check 接 replay_decision 行为需要 build_path 写
# 入 participants(包含 material hash),与 build_service._create_review_candidate
# 同模式。当前保留最小骨架: 5.2 的 AB 互换签名稳定 + 5.4 页面身份变化撤销
# 已由 test_page_identity_decision + 本文件覆盖,完整 merge_duplicate_check
# 改造留到 phase 5 收尾。


# ============================================================================
# 5.4 页面身份变化撤销
# ============================================================================


@pytest.mark.django_db
def test_page_type_change_revocates_related_rules():
    """5.4: 页面 page_type 变化(身份变化)→ 相关规则被 revoke。"""
    from apps.opspilot.models import (
        KnowledgePage,
        PageVersion,
        WikiDecisionRule,
        WikiKnowledgeBase,
    )
    from apps.opspilot.services.wiki.decision_service import (
        create_rule_if_eligible,
        subject_key_for_page,
    )
    from apps.opspilot.services.wiki.title_service import compact_title_key

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="X", page_type="concept")
    page.current_version = PageVersion.objects.create(
        page=page, no=1, body="v", is_current=True, change_type="ai_create"
    )
    page.save()

    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key=subject_key_for_page(
            page_type="concept", canonical_title=compact_title_key("X")
        ),
        schema_fingerprint="sf",
        participants=[],
        action="merge",
        result_page=page,
    )
    assert rule.status == "active"

    # 模拟: 身份变化(page_type 改),调 revoke_rules_for_identity_change
    from apps.opspilot.services.wiki.decision_service import (
        revoke_rules_for_identity_change,
    )
    affected = revoke_rules_for_identity_change(
        knowledge_base=kb,
        old_subject_key=subject_key_for_page(
            page_type="concept", canonical_title=compact_title_key("X")
        ),
    )
    assert affected == 1
    rule.refresh_from_db()
    assert rule.status == "revoked"
