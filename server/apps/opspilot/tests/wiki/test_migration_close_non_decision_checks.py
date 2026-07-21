import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_migration_closes_diagnostics_and_admits_legacy_qa_candidate():
    migrate_from = [("opspilot", "0064_decision_rule")]
    migrate_to = [("opspilot", "0065_close_non_decision_checks")]

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    KnowledgeBase = old_apps.get_model("opspilot", "WikiKnowledgeBase")
    KnowledgePage = old_apps.get_model("opspilot", "KnowledgePage")
    PageVersion = old_apps.get_model("opspilot", "PageVersion")
    CheckItem = old_apps.get_model("opspilot", "CheckItem")

    kb = KnowledgeBase.objects.create(name="migration-kb", team=[1])
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        title="legacy answer",
        page_type="concept",
        status="pending_review",
    )
    current = PageVersion.objects.create(
        page=page,
        no=1,
        body="old",
        change_type="ai_create",
        is_current=True,
    )
    candidate = PageVersion.objects.create(
        page=page,
        no=2,
        body="new answer",
        change_type="qa_answer_candidate",
        is_current=False,
    )
    page.current_version = current
    page.save(update_fields=["current_version"])
    qa_check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="qa_answer_candidate",
        status="open",
        candidate_version=candidate,
        suggested_actions=["accept", "reject"],
    )
    diagnostic = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="orphan",
        status="open",
        suggested_actions=["dismiss"],
    )
    incomplete_conflict = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="conflict",
        status="open",
        candidate_version=candidate,
        decision_key="",
        decision_context={},
        suggested_actions=["keep_current", "use_new"],
    )
    complete_conflict = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="material_update",
        status="open",
        candidate_version=candidate,
        decision_key="d" * 64,
        decision_context={
            "locked_current_version_id": current.pk,
            "decision_type": "knowledge_conflict",
            "subject_key": "page::concept::legacy-answer",
            "schema_fingerprint": "schema-v1",
            "participants": [{"material_id": 10, "material_version_id": 20, "content_hash": "hash-v1"}],
            "incoming": {
                "material_id": 10,
                "material_version_id": 20,
                "content_hash": "hash-v1",
            },
            "current_body_hash": "current-hash",
            "candidate_body_hash": "candidate-hash",
            "candidate_version_id": candidate.pk,
            "page_identity": {"page_id": page.pk, "title": page.title, "page_type": page.page_type},
        },
    )
    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    KnowledgePage = new_apps.get_model("opspilot", "KnowledgePage")
    PageVersion = new_apps.get_model("opspilot", "PageVersion")
    CheckItem = new_apps.get_model("opspilot", "CheckItem")

    migrated_page = KnowledgePage.objects.get(pk=page.pk)
    migrated_candidate = PageVersion.objects.get(pk=candidate.pk)
    migrated_incomplete_conflict = CheckItem.objects.get(pk=incomplete_conflict.pk)
    migrated_complete_conflict = CheckItem.objects.get(pk=complete_conflict.pk)
    migrated_current = PageVersion.objects.get(pk=current.pk)
    migrated_qa_check = CheckItem.objects.get(pk=qa_check.pk)
    migrated_diagnostic = CheckItem.objects.get(pk=diagnostic.pk)

    assert migrated_page.status == "active"
    assert migrated_page.current_version_id == candidate.pk
    assert migrated_page.update_method == "qa_answer"
    assert migrated_candidate.is_current is True
    assert migrated_candidate.change_type == "qa_answer"
    assert migrated_current.is_current is False
    assert migrated_qa_check.status == "auto_resolved"
    assert migrated_qa_check.suggested_actions == []
    assert migrated_qa_check.related["resolution"]["action"] == "automatic_admission"
    assert migrated_diagnostic.status == "auto_resolved"
    assert migrated_diagnostic.suggested_actions == []
    assert migrated_incomplete_conflict.status == "auto_resolved"
    assert migrated_incomplete_conflict.suggested_actions == []
    assert migrated_incomplete_conflict.related["resolution"]["reason"] == "decision_context_incomplete"
    assert migrated_complete_conflict.status == "open"

    assert migrated_diagnostic.related["resolution"]["action"] == "automatic_maintenance"
