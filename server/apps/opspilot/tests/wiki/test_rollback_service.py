import pytest

from apps.opspilot.models import WikiGeneration
from apps.opspilot.services.wiki.active_generation_query_service import page_queryset, page_snapshot
from apps.opspilot.services.wiki.page_service import create_manual_page, edit_page
from apps.opspilot.services.wiki.rollback_service import RollbackServiceError, execute_generation_rollback, preview_generation_rollback
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

pytestmark = pytest.mark.django_db(transaction=True)


def _edited_kb(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="回退页面",
        body="正文 v1",
        created_by="admin",
    )
    knowledge_base.refresh_from_db()
    target_generation = knowledge_base.active_generation
    edit_page(page, body="正文 v2", updated_by="admin")
    knowledge_base.refresh_from_db()
    return knowledge_base, page, target_generation


def _payload(knowledge_base, target_generation, *, confirm=False):
    return {
        "target_generation_id": target_generation.pk,
        "base_generation_id": knowledge_base.active_generation_id,
        "structure_version": knowledge_base.active_structure_revision.revision_no,
        "confirm_structure_restore": confirm,
    }


def test_compatible_rollback_creates_new_generation_and_restores_snapshot(wiki_factory):
    knowledge_base, page, target = _edited_kb(wiki_factory)
    payload = _payload(knowledge_base, target)

    preview = preview_generation_rollback(
        knowledge_base,
        {key: payload[key] for key in ("target_generation_id", "base_generation_id", "structure_version")},
    )
    result = execute_generation_rollback(knowledge_base, payload, operator="admin")

    knowledge_base.refresh_from_db()
    page.refresh_from_db()
    active = knowledge_base.active_generation
    snapshot = page_snapshot(page_queryset(knowledge_base).get(pk=page.pk), knowledge_base=knowledge_base)
    assert preview["outcome"] == "compatible"
    assert preview["allow_restore"] is False
    assert result["structure_result"]["restored"] is False
    assert active.pk != target.pk
    assert active.kind == "rollback"
    assert active.rollback_of_id == target.pk
    assert snapshot.body == "正文 v1"
    assert page.current_version_id == snapshot.page_version_id


def test_rollback_rejects_stale_base_without_creating_candidate(wiki_factory):
    knowledge_base, _page, target = _edited_kb(wiki_factory)
    generation_count = WikiGeneration.objects.filter(knowledge_base=knowledge_base).count()
    payload = _payload(knowledge_base, target)
    payload["base_generation_id"] = target.pk

    with pytest.raises(RollbackServiceError) as captured:
        execute_generation_rollback(knowledge_base, payload, operator="admin")

    knowledge_base.refresh_from_db()
    assert captured.value.code == "base_generation_conflict"
    assert captured.value.retryable is True
    assert WikiGeneration.objects.filter(knowledge_base=knowledge_base).count() == generation_count


def test_rollback_target_must_belong_to_same_knowledge_base(wiki_factory):
    knowledge_base, _page, _target = _edited_kb(wiki_factory)
    other, _other_page, other_target = _edited_kb(wiki_factory)
    payload = _payload(knowledge_base, other_target)

    with pytest.raises(RollbackServiceError) as captured:
        preview_generation_rollback(
            knowledge_base,
            {key: payload[key] for key in ("target_generation_id", "base_generation_id", "structure_version")},
        )

    assert other.pk != knowledge_base.pk
    assert captured.value.code == "rollback_target_not_found"
