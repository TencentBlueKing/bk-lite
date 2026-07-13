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


# ============================================================================
# phase 2: 稳定签名 + 规则服务
# ============================================================================


def _make_kb_with_material(*, kb_name="kb", mat_name="mat-a", body="hello", mat_id=None, content_hash="h1"):
    """建 KB + 一个 material(给签名/规则测试用)。"""
    from apps.opspilot.models import Material, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name=kb_name, team=[1])
    mat = Material.objects.create(
        knowledge_base=kb,
        name=mat_name,
        material_type="text",
        text_content=body,
        content_hash=content_hash,
    )
    return kb, mat


def _participants_kb(signature):
    """构造一对 (material, content_hash) 参与者(用于签名测试)。"""
    return [
        {"material_id": 1, "content_hash": "hA"},
        {"material_id": 2, "content_hash": "hB"},
    ]


@pytest.mark.django_db
class TestSignatureStability:
    """2.1: 签名跨顺序/重复/空集 都确定可区分。"""

    def test_signature_stable_for_participant_order_swap(self):
        from apps.opspilot.services.wiki.decision_service import compute_decision_signature

        s1 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="page::concept::X",
            schema_fingerprint="sf1",
            participants=[{"material_id": 1, "content_hash": "hA"}, {"material_id": 2, "content_hash": "hB"}],
        )
        s2 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="page::concept::X",
            schema_fingerprint="sf1",
            participants=[{"material_id": 2, "content_hash": "hB"}, {"material_id": 1, "content_hash": "hA"}],
        )
        assert s1 == s2, "A、B 顺序互换,签名应保持稳定"

    def test_signature_dedupes_duplicate_participant(self):
        from apps.opspilot.services.wiki.decision_service import compute_decision_signature

        s1 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}, {"material_id": 1, "content_hash": "h"}],
        )
        s2 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        assert s1 == s2, "同一资料重复应去重"

    def test_signature_distinguishes_different_content_hash(self):
        from apps.opspilot.services.wiki.decision_service import compute_decision_signature

        s1 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h1"}],
        )
        s2 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h2"}],
        )
        assert s1 != s2, "content_hash 不同应区分"

    def test_signature_distinguishes_kb(self):
        from apps.opspilot.services.wiki.decision_service import compute_decision_signature

        s1 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        s2 = compute_decision_signature(
            knowledge_base_id=2,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        assert s1 != s2, "不同 KB 应区分"

    def test_signature_distinguishes_decision_type(self):
        from apps.opspilot.services.wiki.decision_service import compute_decision_signature

        s1 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        s2 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="page_identity",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        assert s1 != s2, "不同 decision_type 应区分"

    def test_signature_distinguishes_schema_fingerprint(self):
        from apps.opspilot.services.wiki.decision_service import compute_decision_signature

        s1 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf-A",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        s2 = compute_decision_signature(
            knowledge_base_id=1,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf-B",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        assert s1 != s2, "不同 schema 指纹应区分"


@pytest.mark.django_db
class TestRuleIneligibility:
    """2.3: 上下文不完整时不应创建可回放规则。"""

    def test_empty_participants_does_not_create_rule(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[],  # 空集
            action="use_new",
        )
        assert rule is None
        assert WikiDecisionRule.objects.count() == 0

    def test_missing_content_hash_does_not_create_rule(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": ""}],
            action="use_new",
        )
        assert rule is None
        assert WikiDecisionRule.objects.count() == 0

    def test_missing_material_id_does_not_create_rule(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": None, "content_hash": "h"}],
            action="use_new",
        )
        assert rule is None
        assert WikiDecisionRule.objects.count() == 0

    def test_missing_subject_key_does_not_create_rule(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="",  # 空
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action="use_new",
        )
        assert rule is None
        assert WikiDecisionRule.objects.count() == 0


@pytest.mark.django_db
class TestRuleQuery:
    """2.4: 规则查询/upsert/撤销/回放计数。"""

    def test_find_active_rule_by_key(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, find_active_rule

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action="use_new",
        )

        sig = WikiDecisionRule.objects.first().decision_key
        found = find_active_rule(kb, "knowledge_conflict", sig)
        assert found is not None
        assert found.action == "use_new"

    def test_find_active_rule_returns_none_for_revoked(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, find_active_rule, revoke_rule

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action="use_new",
        )
        revoke_rule(rule)
        found = find_active_rule(kb, "knowledge_conflict", rule.decision_key)
        assert found is None, "revoked 规则不应被查到"

    def test_replay_increments_count(self):
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, mark_replayed

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action="use_new",
        )
        assert rule.replay_count == 0
        mark_replayed(rule)
        mark_replayed(rule)
        rule.refresh_from_db()
        assert rule.replay_count == 2

    def test_upsert_updates_existing_rule(self):
        """相同签名再调 create: 复用同一条记录(不创建第二条),action 覆盖。"""
        from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        kwargs = dict(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
        )
        r1 = create_rule_if_eligible(**kwargs, action="use_new")
        r2 = create_rule_if_eligible(**kwargs, action="keep_current")
        assert r1.id == r2.id
        assert WikiDecisionRule.objects.count() == 1
        assert r2.action == "keep_current"


@pytest.mark.django_db
class TestRevokeRules:
    """2.5: 物理删除资料/页面/页面身份变化 → 相关规则被撤销,当前知识不回滚。"""

    def _create_active_rule(self, kb, *, decision_type="knowledge_conflict", action="use_new"):
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible

        return create_rule_if_eligible(
            knowledge_base=kb,
            decision_type=decision_type,
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action=action,
        )

    def test_revoke_rules_for_material_marks_active_rules_revoked(self):
        from apps.opspilot.models import Material, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_materials

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        mat = Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="x", content_hash="h")
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": mat.id, "content_hash": "h"}],
            action="use_new",
        )
        revoke_rules_for_materials([mat])
        rule.refresh_from_db()
        assert rule.status == "revoked"

    def test_revoke_rules_for_page_marks_active_rules_revoked(self):
        from apps.opspilot.models import KnowledgePage, WikiKnowledgeBase
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_pages

        kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
        page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
        rule = create_rule_if_eligible(
            knowledge_base=kb,
            decision_type="knowledge_conflict",
            subject_key="k",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action="use_new",
            result_page=page,
        )
        revoke_rules_for_pages([page])
        rule.refresh_from_db()
        assert rule.status == "revoked"

    def test_revoke_rules_for_identity_change_marks_active_rules_revoked(self):
        from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_identity_change

        kb_kb_holder = {}
        # page_identity 决策,subject_key 是页面身份签名
        rule = create_rule_if_eligible(
            knowledge_base=__import__("apps.opspilot.models", fromlist=["WikiKnowledgeBase"]).WikiKnowledgeBase.objects.create(name="kb", team=[1]),
            decision_type="page_identity",
            subject_key="page::concept::test::alpha",
            schema_fingerprint="sf",
            participants=[{"material_id": 1, "content_hash": "h"}],
            action="merge",
        )
        revoke_rules_for_identity_change(rule.knowledge_base, "page::concept::test::alpha")
        rule.refresh_from_db()
        assert rule.status == "revoked"
