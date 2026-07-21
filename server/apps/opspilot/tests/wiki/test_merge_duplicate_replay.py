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
    from apps.opspilot.models import KnowledgePage, PageVersion, WikiKnowledgeBase
    from apps.opspilot.services.wiki.decision_service import create_rule_if_eligible, subject_key_for_page
    from apps.opspilot.services.wiki.title_service import compact_title_key

    kb = WikiKnowledgeBase.objects.create(name="kb", team=[1])
    page = KnowledgePage.objects.create(knowledge_base=kb, title="X", page_type="concept")
    page.current_version = PageVersion.objects.create(page=page, no=1, body="v", is_current=True, change_type="ai_create")
    page.save()

    rule = create_rule_if_eligible(
        knowledge_base=kb,
        decision_type="page_identity",
        subject_key=subject_key_for_page(page_type="concept", canonical_title=compact_title_key("X")),
        schema_fingerprint="sf",
        participants=[],
        action="merge",
        result_page=page,
    )
    assert rule.status == "active"

    # 模拟: 身份变化(page_type 改),调 revoke_rules_for_identity_change
    from apps.opspilot.services.wiki.decision_service import revoke_rules_for_identity_change

    affected = revoke_rules_for_identity_change(
        knowledge_base=kb,
        old_subject_key=subject_key_for_page(page_type="concept", canonical_title=compact_title_key("X")),
    )
    assert affected == 1
    rule.refresh_from_db()
    assert rule.status == "revoked"


def _identity_page(kb, title, body="body", page_type="concept"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title=title,
        page_type=page_type,
        contribution="human",
    )
    page.current_version = PageVersion.objects.create(
        page=page,
        no=1,
        body=body,
        is_current=True,
        change_type="ai_create",
    )
    page.save(update_fields=["current_version"])
    return page


def _alias_kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(
        name="kb",
        team=[1],
        generation_rules={
            "title_aliases": [
                {
                    "canonical": "配置平台",
                    "aliases": ["CMDB", "配置管理数据库"],
                }
            ]
        },
    )


@pytest.mark.django_db
def test_ensure_check_replays_keep_separate_for_new_ids_and_reversed_order():
    from apps.opspilot.models import CheckItem
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    original_target = _identity_page(kb, "配置平台")
    original_source = _identity_page(kb, "CMDB")
    original_check = ensure_check(
        kb,
        "duplicate",
        original_source,
        related={
            "pages": [original_source.id, original_target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(original_check, "keep_separate", operator="alice")

    fresh_target = _identity_page(kb, "配置平台")
    fresh_source = _identity_page(kb, "CMDB")
    decision_count = CheckItem.objects.filter(
        knowledge_base=kb,
        check_type__in=["duplicate", "conflict"],
    ).count()

    created = ensure_check(
        kb,
        "duplicate",
        fresh_source,
        related={
            "pages": [fresh_source.id, fresh_target.id],
            "canonical_title": "配置平台",
        },
    )

    assert created == []
    assert (
        CheckItem.objects.filter(
            knowledge_base=kb,
            check_type__in=["duplicate", "conflict"],
        ).count()
        == decision_count
    )
    rule.refresh_from_db()
    assert rule.status == "active"
    assert rule.replay_count == 1


@pytest.mark.django_db
def test_ensure_check_replays_merge_using_frozen_target_identity_without_check():
    from apps.opspilot.models import BuildRecord, CheckItem
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    original_target = _identity_page(kb, "配置平台", "original target")
    original_source = _identity_page(kb, "CMDB", "original source")
    original_check = ensure_check(
        kb,
        "duplicate",
        original_source,
        related={
            "pages": [original_source.id, original_target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(original_check, "merge", operator="alice")

    fresh_target = _identity_page(kb, "配置平台", "fresh target")
    fresh_source = _identity_page(kb, "CMDB", "fresh source")
    decision_count = CheckItem.objects.filter(
        knowledge_base=kb,
        check_type__in=["duplicate", "conflict"],
    ).count()

    created = ensure_check(
        kb,
        "duplicate",
        fresh_source,
        related={
            "pages": [fresh_source.id, fresh_target.id],
            "canonical_title": "配置平台",
        },
    )

    assert created == []
    fresh_target.refresh_from_db()
    fresh_source.refresh_from_db()
    assert fresh_target.status == "active"
    assert fresh_source.status == "archived"
    assert "fresh source" in fresh_target.current_version.body
    assert (
        CheckItem.objects.filter(
            knowledge_base=kb,
            check_type__in=["duplicate", "conflict"],
        ).count()
        == decision_count
    )
    rule.refresh_from_db()
    assert rule.replay_count == 1
    assert rule.result_page_id == fresh_target.id
    assert rule.result_version_id == fresh_target.current_version_id
    assert rule.result_snapshot["result_page_id"] == fresh_target.id
    assert rule.result_snapshot["result_version_id"] == fresh_target.current_version_id
    assert rule.result_snapshot["target_identity"]["page_id"] == fresh_target.id
    assert {item["page_id"] for item in rule.result_snapshot["source_identities"]} == {fresh_source.id}
    replay_record = BuildRecord.objects.get(
        trigger="decision",
        inputs__decision_rule_id=rule.id,
    )
    assert replay_record.inputs["decision_reused"] is True
    assert set(replay_record.affected_pages) == {fresh_target.id, fresh_source.id}


@pytest.mark.django_db
def test_merge_rule_replay_fails_closed_when_related_page_is_inactive():
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    original_target = _identity_page(kb, "配置平台")
    original_source = _identity_page(kb, "CMDB")
    original_check = ensure_check(
        kb,
        "duplicate",
        original_target,
        related={
            "pages": [original_target.id, original_source.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(original_check, "merge", operator="alice")

    fresh_target = _identity_page(kb, "配置平台", "unchanged")
    fresh_source = _identity_page(kb, "CMDB", "must not merge")
    fresh_source.status = "archived"
    fresh_source.save(update_fields=["status", "updated_at"])

    created = ensure_check(
        kb,
        "duplicate",
        fresh_target,
        related={
            "pages": [fresh_target.id, fresh_source.id],
            "canonical_title": "配置平台",
        },
    )

    assert created == []
    fresh_target.refresh_from_db()
    assert fresh_target.current_version.body == "unchanged"
    rule.refresh_from_db()
    assert rule.replay_count == 0


@pytest.mark.django_db
def test_scan_health_creates_unique_page_identity_pairs_and_keeps_diagnostics_separate():
    from apps.opspilot.models import CheckItem
    from apps.opspilot.services.wiki.check_service import scan_health

    kb = _alias_kb()
    pages = [
        _identity_page(kb, "配置平台", "A" * 40),
        _identity_page(kb, "CMDB", "B" * 40),
        _identity_page(kb, "配置管理数据库", "C" * 40),
    ]

    scan_health(kb)

    decision_checks = list(
        CheckItem.objects.filter(
            knowledge_base=kb,
            check_type__in=["duplicate", "conflict"],
            status="open",
        )
    )
    page_pairs = {frozenset(check.related["pages"]) for check in decision_checks}
    expected_pairs = {
        frozenset([pages[0].id, pages[1].id]),
        frozenset([pages[0].id, pages[2].id]),
        frozenset([pages[1].id, pages[2].id]),
    }
    assert page_pairs == expected_pairs
    assert (
        CheckItem.objects.filter(
            knowledge_base=kb,
            check_type="orphan",
            status="auto_resolved",
            related__resolution__action="automatic_maintenance",
        ).count()
        == 3
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"title": "配置项数据库"},
        {"page_type": "service"},
    ],
)
def test_editing_page_identity_revokes_related_rule(monkeypatch, api_client, payload):
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    target = _identity_page(kb, "配置平台")
    source = _identity_page(kb, "CMDB")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(check, "keep_separate", operator="alice")
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: {},
    )

    response = api_client.patch(
        f"/api/v1/opspilot/wiki_mgmt/page/{source.id}/",
        payload,
        format="json",
    )

    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "page identity changed"
    assert rule.result_snapshot["revoked_by"] == "testuser"


@pytest.mark.django_db
def test_body_only_edit_keeps_page_identity_rule_active():
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check
    from apps.opspilot.services.wiki.page_service import edit_page

    kb = _alias_kb()
    target = _identity_page(kb, "配置平台")
    source = _identity_page(kb, "CMDB")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(check, "keep_separate", operator="alice")

    edit_page(source, body="body changed", updated_by="bob")

    rule.refresh_from_db()
    assert rule.status == "active"


@pytest.mark.django_db
def test_restoring_merged_source_revokes_merge_rule(monkeypatch, api_client):
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    target = _identity_page(kb, "配置平台")
    source = _identity_page(kb, "CMDB")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(check, "merge", operator="alice")
    source.refresh_from_db()
    assert source.status == "archived"
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: {},
    )

    response = api_client.post(f"/api/v1/opspilot/wiki_mgmt/page/{source.id}/restore_from_archive/")

    assert response.status_code == 200, response.content
    source.refresh_from_db()
    rule.refresh_from_db()
    assert source.status == "active"
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "merged source restored"


@pytest.mark.django_db
def test_physical_page_delete_revokes_related_rule(monkeypatch, api_client):
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    target = _identity_page(kb, "配置平台")
    source = _identity_page(kb, "CMDB")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(check, "keep_separate", operator="alice")
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: {},
    )

    response = api_client.delete(f"/api/v1/opspilot/wiki_mgmt/page/{source.id}/")

    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "page physically deleted"


@pytest.mark.django_db
def test_batch_page_delete_revokes_related_rule(monkeypatch, api_client):
    from apps.opspilot.services.wiki.check_service import decide_check, ensure_check

    kb = _alias_kb()
    target = _identity_page(kb, "配置平台")
    source = _identity_page(kb, "CMDB")
    check = ensure_check(
        kb,
        "duplicate",
        source,
        related={
            "pages": [source.id, target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = decide_check(check, "keep_separate", operator="alice")
    monkeypatch.setattr(
        "apps.opspilot.viewsets.wiki_page_view.cascade",
        lambda *args, **kwargs: {},
    )

    response = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/page/batch_delete/",
        {"knowledge_base": kb.id, "ids": [source.id]},
        format="json",
    )

    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.status == "revoked"
    assert rule.result_snapshot["revoked_reason"] == "page physically deleted"


@pytest.mark.django_db
def test_merge_replay_revoked_between_lookup_and_claim_does_not_mutate_pages(
    monkeypatch,
):
    from apps.opspilot.services.wiki import check_service, decision_service

    kb = _alias_kb()
    original_target = _identity_page(kb, "配置平台", "original target")
    original_source = _identity_page(kb, "CMDB", "original source")
    original_check = check_service.ensure_check(
        kb,
        "duplicate",
        original_source,
        related={
            "pages": [original_source.id, original_target.id],
            "canonical_title": "配置平台",
        },
    )[0]
    rule = check_service.decide_check(original_check, "merge", operator="alice")
    fresh_target = _identity_page(kb, "配置平台", "fresh target")
    fresh_source = _identity_page(kb, "CMDB", "fresh source")
    real_find = check_service.find_active_rule

    def find_then_revoke(*args, **kwargs):
        found = real_find(*args, **kwargs)
        decision_service.revoke_rule(
            found,
            reason="revoked during merge claim",
            operator="admin",
        )
        return found

    monkeypatch.setattr(check_service, "find_active_rule", find_then_revoke)

    created = check_service.ensure_check(
        kb,
        "duplicate",
        fresh_source,
        related={
            "pages": [fresh_source.id, fresh_target.id],
            "canonical_title": "配置平台",
        },
    )

    assert len(created) == 1
    assert created[0].status == "open"
    fresh_target.refresh_from_db()
    fresh_source.refresh_from_db()
    assert fresh_target.status == "active"
    assert fresh_source.status == "active"
    assert fresh_target.current_version.body == "fresh target"
    rule.refresh_from_db()
    assert rule.status == "revoked"
    assert rule.replay_count == 0
