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
        from apps.opspilot.models import WikiKnowledgeBase
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
        from apps.opspilot.models import WikiKnowledgeBase
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


@pytest.mark.django_db
def test_participant_builder_uses_all_evidence_and_incoming_snapshot():
    """来源集合必须包含现有 A+B 与本次 C，并优先使用 evidence 的版本 hash。"""
    from apps.opspilot.models import KnowledgePage, Material, MaterialVersion, PageEvidence, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import build_participants_from_page_evidence

    kb = WikiKnowledgeBase.objects.create(name="kb-full-participants", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    material_a = Material.objects.create(knowledge_base=kb, name="A", material_type="text", content_hash="material-a")
    version_a = MaterialVersion.objects.create(material=material_a, content_hash="version-a")
    material_b = Material.objects.create(knowledge_base=kb, name="B", material_type="text", content_hash="material-b")
    material_c = Material.objects.create(knowledge_base=kb, name="C", material_type="text", content_hash="material-c")
    version_c = MaterialVersion.objects.create(material=material_c, content_hash="version-c")
    PageEvidence.objects.create(page=page, material=material_a, material_version=version_a)
    PageEvidence.objects.create(page=page, material=material_b)

    participants = build_participants_from_page_evidence(
        page,
        incoming_snapshot={
            "material_id": material_c.id,
            "material_version_id": version_c.id,
            "content_hash": version_c.content_hash,
        },
    )

    assert {(item["material_id"], item["content_hash"]) for item in participants} == {
        (material_a.id, "version-a"),
        (material_b.id, "material-b"),
        (material_c.id, "version-c"),
    }


@pytest.mark.django_db
def test_material_builder_preserves_incomplete_participant():
    """构造参与者时不得静默丢弃缺 hash 的资料并退化为可回放子集。"""
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import build_participants_from_materials, is_participant_complete

    kb = WikiKnowledgeBase.objects.create(name="kb-incomplete-participants", team=[1])
    complete = Material.objects.create(knowledge_base=kb, name="complete", material_type="text", content_hash="hash-complete")
    incomplete = Material.objects.create(knowledge_base=kb, name="incomplete", material_type="text", content_hash="")
    participants = build_participants_from_materials([complete, incomplete])

    assert len(participants) == 2
    assert not is_participant_complete(participants)


@pytest.mark.django_db
def test_invalid_participant_prevents_replay_of_valid_subset():
    """A+无效 B 不能命中仅 A 的规则。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import _body_hash
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, replay_decision

    kb = WikiKnowledgeBase.objects.create(name="kb-invalid-replay", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    version = PageVersion.objects.create(page=page, no=1, body="approved", change_type="ai_create", is_current=True)
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    participant_a = {"material_id": 1, "content_hash": "hash-a"}
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=[participant_a],
        action="keep_current",
        result_snapshot={"body_hash": _body_hash(version.body)},
        result_page=page,
        result_version=version,
    )

    result, replayed_rule = replay_decision(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=[participant_a, {"material_id": 2, "content_hash": ""}],
        page=page,
    )

    rule.refresh_from_db()
    assert (result, replayed_rule) == ("pending", None)
    assert rule.replay_count == 0


@pytest.mark.django_db
def test_replay_accepts_new_version_id_with_same_final_body_hash():
    """最终正文未变时，PageVersion 行 ID 改变不应让规则失配。"""
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.check_service import _body_hash
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, replay_decision

    kb = WikiKnowledgeBase.objects.create(name="kb-body-hash-replay", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    old_version = PageVersion.objects.create(page=page, no=1, body="approved", change_type="ai_create", is_current=False)
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=[{"material_id": 1, "content_hash": "hash-a"}],
        action="keep_current",
        result_snapshot={"body_hash": _body_hash(old_version.body)},
        result_page=page,
        result_version=old_version,
    )
    replacement = PageVersion.objects.create(page=page, no=2, body="approved", change_type="restore", is_current=True)
    page.current_version = replacement
    page.save(update_fields=["current_version", "updated_at"])

    result, replayed_rule = replay_decision(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=[{"material_id": 1, "content_hash": "hash-a"}],
        page=page,
    )

    assert (result, replayed_rule.id) == ("replayed", rule.id)


@pytest.mark.django_db
def test_candidate_body_equal_to_current_returns_unchanged():
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import replay_decision

    kb = WikiKnowledgeBase.objects.create(name="kb-unchanged", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="p", page_type="concept")
    version = PageVersion.objects.create(page=page, no=1, body="same", change_type="ai_create", is_current=True)
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])

    result, rule = replay_decision(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=[{"material_id": 1, "content_hash": "hash-a"}],
        page=page,
        candidate_body="same",
    )

    assert (result, rule) == ("unchanged", None)


@pytest.mark.django_db
def test_mark_replayed_uses_atomic_increment_and_refreshes_stale_instance():
    from apps.opspilot.models import WikiDecisionRule, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, mark_replayed

    kb = WikiKnowledgeBase.objects.create(name="kb-atomic-replay", team=[1])
    first = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=[{"material_id": 1, "content_hash": "hash-a"}],
        action="keep_current",
    )
    stale = WikiDecisionRule.objects.get(pk=first.pk)

    mark_replayed(first)
    mark_replayed(stale)

    assert stale.replay_count == 2


@pytest.mark.django_db
def test_revoke_rules_for_pages_matches_any_frozen_identity_pair_member():
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_pages

    kb = WikiKnowledgeBase.objects.create(name="kb-revoke-pair-member", team=[1])
    source = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="Alpha",
        page_type="entity",
    )
    source.current_version = PageVersion.objects.create(
        page=source,
        no=1,
        body="source",
        change_type="ai_create",
        is_current=True,
    )
    source.save(update_fields=["current_version", "updated_at"])
    target = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="Beta",
        page_type="entity",
    )
    target.current_version = PageVersion.objects.create(
        page=target,
        no=1,
        body="target",
        change_type="ai_create",
        is_current=True,
    )
    target.save(update_fields=["current_version", "updated_at"])
    source_identity = {
        "page_id": source.id,
        "page_type": "entity",
        "canonical_title": "Alpha",
    }
    target_identity = {
        "page_id": target.id,
        "page_type": "entity",
        "canonical_title": "Beta",
    }
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key="identity::entity::alpha|entity::beta",
        schema_fingerprint="schema",
        participants=[],
        action="merge",
        match_snapshot={"page_identities": [source_identity, target_identity]},
        result_snapshot={
            "target_identity": target_identity,
            "source_identities": [source_identity],
        },
        result_page=target,
        result_version=target.current_version,
    )

    affected = revoke_rules_for_pages(
        [source],
        reason="source page deleted",
        operator="maintainer",
    )

    rule.refresh_from_db()
    assert affected == 1
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "source page deleted"
    assert rule.result_snapshot["revoked_by"] == "maintainer"
    target.refresh_from_db()
    assert target.current_version.body == "target"


@pytest.mark.django_db
def test_revoke_rules_for_materials_records_reason_and_operator():
    from apps.opspilot.models import Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_materials

    kb = WikiKnowledgeBase.objects.create(name="kb-revoke-material-audit", team=[1])
    material = Material.objects.create(
        knowledge_base=kb,
        name="source",
        material_type="text",
        content_hash="hash-source",
    )
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::alpha",
        schema_fingerprint="schema",
        participants=[{"material_id": material.id, "content_hash": "hash-source"}],
        action="keep_current",
    )

    affected = revoke_rules_for_materials(
        [material],
        reason="material deleted",
        operator="maintainer",
    )

    rule.refresh_from_db()
    assert affected == 1
    assert rule.result_snapshot["revoked_reason"] == "material deleted"
    assert rule.result_snapshot["revoked_by"] == "maintainer"


@pytest.mark.django_db
def test_revoke_identity_change_matches_member_inside_pair_subject():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, revoke_rules_for_identity_change, subject_key_for_page

    kb = WikiKnowledgeBase.objects.create(name="kb-revoke-identity-member", team=[1])
    alpha_identity = {
        "page_id": 101,
        "page_type": "entity",
        "canonical_title": "Alpha",
    }
    beta_identity = {
        "page_id": 102,
        "page_type": "entity",
        "canonical_title": "Beta",
    }
    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key="identity::entity::alpha|entity::beta",
        schema_fingerprint="schema",
        participants=[],
        action="keep_separate",
        match_snapshot={"page_identities": [alpha_identity, beta_identity]},
    )
    old_subject_key = subject_key_for_page(
        page_type="entity",
        canonical_title="Alpha",
    )

    affected = revoke_rules_for_identity_change(
        kb,
        old_subject_key,
        reason="identity changed",
        operator="editor",
    )

    rule.refresh_from_db()
    assert affected == 1
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "identity changed"
    assert rule.result_snapshot["revoked_by"] == "editor"


@pytest.mark.django_db
def test_schema_fingerprint_uses_canonical_generation_rules_json():
    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import compute_schema_fingerprint

    kb = WikiKnowledgeBase.objects.create(
        name="kb",
        team=[1],
        schema_md="# schema",
        generation_rules={
            "merge": {"b": 2, "a": 1},
            "title_aliases": [{"aliases": ["CMDB"], "canonical": "配置平台"}],
        },
    )
    first = compute_schema_fingerprint(kb)

    kb.generation_rules = {
        "title_aliases": [{"canonical": "配置平台", "aliases": ["CMDB"]}],
        "merge": {"a": 1, "b": 2},
    }
    reordered = compute_schema_fingerprint(kb)
    kb.generation_rules = {
        "title_aliases": [{"canonical": "配置平台", "aliases": ["CMDB"]}],
        "merge": {"a": 1, "b": 3},
    }
    changed = compute_schema_fingerprint(kb)

    assert first == reordered
    assert changed != first


@pytest.mark.django_db
def test_replay_fails_closed_when_rule_is_revoked_between_lookup_and_claim(monkeypatch):
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki import decision_service
    from apps.opspilot.services.wiki.check_service import _body_hash

    kb = WikiKnowledgeBase.objects.create(name="kb-replay-revoke-race", team=[1])
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="p",
        page_type="concept",
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body="approved",
        change_type="ai_create",
        is_current=True,
    )
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    participants = [{"material_id": 1, "content_hash": "hash-a"}]
    rule = decision_service.create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=participants,
        action="keep_current",
        result_snapshot={"body_hash": _body_hash("approved")},
        result_page=page,
        result_version=version,
    )
    real_find = decision_service.find_active_rule

    def find_then_revoke(*args, **kwargs):
        found = real_find(*args, **kwargs)
        decision_service.revoke_rule(
            found,
            reason="revoked during replay claim",
            operator="admin",
        )
        return found

    monkeypatch.setattr(decision_service, "find_active_rule", find_then_revoke)

    result, replayed_rule = decision_service.replay_decision(
        knowledge_base=kb,
        decision_type="knowledge_conflict",
        subject_key="page::concept::p",
        schema_fingerprint="schema",
        participants=participants,
        page=page,
        candidate_body="different candidate",
    )

    assert (result, replayed_rule) == ("pending", None)
    assert decision_service.mark_replayed(rule) is False
    rule.refresh_from_db()
    assert rule.status == "revoked"
    assert rule.replay_count == 0
    assert rule.last_replayed_at is None
