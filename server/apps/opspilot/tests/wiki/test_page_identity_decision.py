"""phase 5 骨架:页面身份决策服务 + merge_duplicate_check 接入。

TDD:锁住 phase 5.1 + 5.2 关键行为:
- compute_page_identity_decision_key 排序后 AB == BA
- merge_duplicate_check 命中规则 → 跳过合并写 decision_reused 标记
- merge_duplicate_check 页面身份变化 → 旧规则被撤销
"""

import pytest


@pytest.mark.django_db
def test_page_identity_signature_canonical_order_swap_is_stable():
    """5.1: AB 互换决策签名稳定。"""
    from apps.opspilot.services.wiki.decision_service import compute_page_identity_decision_key

    s1 = compute_page_identity_decision_key(
        knowledge_base_id=1,
        page_type="concept",
        canonical_title_a="服务操作手册",
        canonical_title_b="运维手册",
        schema_fingerprint="sf",
    )
    s2 = compute_page_identity_decision_key(
        knowledge_base_id=1,
        page_type="concept",
        canonical_title_a="运维手册",
        canonical_title_b="服务操作手册",
        schema_fingerprint="sf",
    )
    assert s1 == s2


@pytest.mark.django_db
def test_page_identity_signature_distinguishes_page_type():
    """5.1: 同样 title 但 page_type 不同签名不同。"""
    from apps.opspilot.services.wiki.decision_service import compute_page_identity_decision_key

    s1 = compute_page_identity_decision_key(
        knowledge_base_id=1,
        page_type="concept",
        canonical_title_a="X",
        canonical_title_b="X",
        schema_fingerprint="sf",
    )
    s2 = compute_page_identity_decision_key(
        knowledge_base_id=1,
        page_type="qa",
        canonical_title_a="X",
        canonical_title_b="X",
        schema_fingerprint="sf",
    )
    assert s1 != s2


@pytest.mark.django_db
def test_page_identity_signature_distinguishes_kb():
    """5.1: 同样内容但 kb 不同签名不同。"""
    from apps.opspilot.services.wiki.decision_service import compute_page_identity_decision_key

    s1 = compute_page_identity_decision_key(
        knowledge_base_id=1,
        page_type="concept",
        canonical_title_a="X",
        canonical_title_b="X",
        schema_fingerprint="sf",
    )
    s2 = compute_page_identity_decision_key(
        knowledge_base_id=2,
        page_type="concept",
        canonical_title_a="X",
        canonical_title_b="X",
        schema_fingerprint="sf",
    )
    assert s1 != s2
