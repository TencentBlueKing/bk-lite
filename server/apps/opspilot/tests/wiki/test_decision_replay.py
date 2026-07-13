"""WikiDecisionRule 数据模型 + 唯一约束(phase 1.1 + 1.2)。

TDD:先写失败测试,锁住 phase 1 行为:
- WikiDecisionRule 字段可持久化(knowledge_base / decision_type / decision_key /
  subject_key / match_snapshot / result_snapshot / action / status / replay_count)
- 同一 KB + decision_type + decision_key 不能保存两条 active 规则
- 不同 KB / 不同 decision_type 可保存同摘要
- decision_key 长度 = SHA-256 hex = 64 字符

revert 修复(删除 model 定义)后,所有 import 失败,测试报错。
"""

import pytest


@pytest.mark.django_db
def test_decision_rule_persists_all_fields():
    """1.1: WikiDecisionRule 字段完整可持久化。"""
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    rule = WikiDecisionRule.objects.create(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        decision_key="a" * 64,  # SHA-256 hex 占位
        subject_key="page::concept::服务操作手册",
        match_snapshot={"participants": [{"material_id": 1, "content_hash": "h1"}]},
        result_snapshot={"winner_material_id": 1, "body_hash": "bh1"},
        action="use_new",
        # source_check / result_page / result_version 留空,FOREIGN KEY 无目标会报错
    )

    rule.refresh_from_db()
    assert rule.knowledge_base_id == kb.id
    assert rule.decision_type == "knowledge_conflict"
    assert rule.decision_key == "a" * 64
    assert rule.subject_key == "page::concept::服务操作手册"
    assert rule.match_snapshot["participants"][0]["material_id"] == 1
    assert rule.result_snapshot["winner_material_id"] == 1
    assert rule.action == "use_new"
    assert rule.status == "active"  # 默认
    assert rule.replay_count == 0  # 默认


@pytest.mark.django_db
def test_decision_key_uniqueness_within_kb_and_type():
    """1.2: 同一 KB + decision_type + decision_key 不能保存两条 active 规则。"""
    from django.db import IntegrityError, transaction

    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    key = "b" * 64

    WikiDecisionRule.objects.create(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        decision_key=key,
        subject_key="t1",
        match_snapshot={},
        result_snapshot={},
        action="use_new",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WikiDecisionRule.objects.create(
                knowledge_base=kb,
                decision_type="knowledge_conflict",
                decision_key=key,  # 同 key
                subject_key="t2",
                match_snapshot={},
                result_snapshot={},
                action="keep_current",
            )


@pytest.mark.django_db
def test_same_key_allowed_across_different_kb():
    """1.2 补充: 不同 KB 下可保存同 decision_key。"""
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase

    kb1 = WikiKnowledgeBase.objects.create(name="kb1", team=[1])
    kb2 = WikiKnowledgeBase.objects.create(name="kb2", team=[1])
    key = "c" * 64

    WikiDecisionRule.objects.create(
        knowledge_base=kb1,
        decision_type="knowledge_conflict",
        decision_key=key,
        subject_key="t",
        match_snapshot={},
        result_snapshot={},
        action="use_new",
    )
    WikiDecisionRule.objects.create(
        knowledge_base=kb2,
        decision_type="knowledge_conflict",
        decision_key=key,  # 同 key 但不同 KB
        subject_key="t",
        match_snapshot={},
        result_snapshot={},
        action="use_new",
    )

    assert WikiDecisionRule.objects.count() == 2


@pytest.mark.django_db
def test_same_key_allowed_across_different_decision_type():
    """1.2 补充: 同一 KB + 同 key 但不同 decision_type 可共存。"""
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    key = "d" * 64

    WikiDecisionRule.objects.create(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        decision_key=key,
        subject_key="t",
        match_snapshot={},
        result_snapshot={},
        action="use_new",
    )
    WikiDecisionRule.objects.create(
        knowledge_base=kb,
        decision_type="page_identity",
        decision_key=key,  # 同 key 但不同 decision_type
        subject_key="t",
        match_snapshot={},
        result_snapshot={},
        action="merge",
    )

    assert WikiDecisionRule.objects.count() == 2


@pytest.mark.django_db
def test_status_can_be_revoked():
    """1.1 补充: 状态可从 active 切到 revoked(为 phase 2 撤销 API 留路)。"""
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    rule = WikiDecisionRule.objects.create(
        knowledge_base=kb,
        decision_type="page_identity",
        decision_key="e" * 64,
        subject_key="t",
        match_snapshot={},
        result_snapshot={},
        action="keep_separate",
    )

    assert rule.status == "active"
    rule.status = "revoked"
    rule.save(update_fields=["status", "updated_at"])
    rule.refresh_from_db()
    assert rule.status == "revoked"
