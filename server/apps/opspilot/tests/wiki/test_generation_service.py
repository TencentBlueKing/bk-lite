import pytest

from apps.opspilot.models import WikiGeneration
from apps.opspilot.services.wiki.generation_service import activate_generation, begin_generation, clone_base_snapshot, mark_generation_ready
from apps.opspilot.services.wiki.page_service import create_manual_page
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

pytestmark = pytest.mark.django_db(transaction=True)


def _ready_kb_with_page(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="发布一致性",
        body="正文 v1",
        created_by="admin",
    )
    knowledge_base.refresh_from_db()
    return knowledge_base, page


def _candidate(knowledge_base, suffix):
    candidate = begin_generation(
        knowledge_base=knowledge_base,
        kind="governance",
        base_generation_id=knowledge_base.active_generation_id,
        structure_revision_id=knowledge_base.active_structure_revision_id,
        pipeline_version=f"test-{suffix}",
        source_fingerprints=[],
        operator="admin",
    )
    clone_base_snapshot(candidate.id)
    mark_generation_ready(candidate.id)
    candidate.refresh_from_db()
    return candidate


def test_manual_page_creation_publishes_complete_new_generation(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    baseline_id = knowledge_base.active_generation_id

    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="人工知识",
        body="内容",
        created_by="admin",
    )

    knowledge_base.refresh_from_db()
    page.refresh_from_db()
    active = knowledge_base.active_generation
    member = active.page_members.get(page=page)
    assert active.id != baseline_id
    assert active.status == "active"
    assert WikiGeneration.objects.get(pk=baseline_id).status == "superseded"
    assert member.page_version_id == page.current_version_id
    assert member.directory_id == page.directory_id
    assert member.assignment_mode == "manual"
    assert member.page_status == "active"


def test_two_candidates_from_same_base_only_first_can_activate(wiki_factory):
    knowledge_base, page = _ready_kb_with_page(wiki_factory)
    base_generation_id = knowledge_base.active_generation_id
    structure_revision = knowledge_base.active_structure_revision
    first = _candidate(knowledge_base, "first")
    second = _candidate(knowledge_base, "second")

    first_result = activate_generation(
        first.id,
        requested_base_generation_id=base_generation_id,
        expected_structure_revision_id=structure_revision.id,
        expected_structure_version=structure_revision.revision_no,
    )
    second_result = activate_generation(
        second.id,
        requested_base_generation_id=base_generation_id,
        expected_structure_revision_id=structure_revision.id,
        expected_structure_version=structure_revision.revision_no,
    )

    knowledge_base.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert first_result.outcome == "active"
    assert second_result.outcome == "superseded"
    assert knowledge_base.active_generation_id == first.id
    assert first.status == "active"
    assert second.status == "superseded"
    assert first.page_members.get(page=page).page_version_id == page.current_version_id


def test_candidate_clone_does_not_mutate_active_snapshot_before_activation(wiki_factory):
    knowledge_base, page = _ready_kb_with_page(wiki_factory)
    active_id = knowledge_base.active_generation_id

    candidate = _candidate(knowledge_base, "isolated")

    knowledge_base.refresh_from_db()
    assert knowledge_base.active_generation_id == active_id
    assert WikiGeneration.objects.get(pk=active_id).status == "active"
    assert candidate.status == "ready"
    assert candidate.page_members.get(page=page).page_version_id == page.current_version_id
