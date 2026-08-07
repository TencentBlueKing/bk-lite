from io import StringIO

import pytest
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError

_REQUIRED_COMMANDS = {
    "audit_wiki_directory_readiness",
    "backfill_wiki_directory_governance",
}
_missing_commands = sorted(_REQUIRED_COMMANDS - set(get_commands()))
if _missing_commands:
    pytest.skip(
        "directory migration commands not shipped yet: " + ", ".join(_missing_commands),
        allow_module_level=True,
    )

from apps.opspilot.management.commands.backfill_wiki_directory_governance import _begin_backfill
from apps.opspilot.models import (
    BuildRecord,
    KnowledgePage,
    PageDirectoryChange,
    PageRelation,
    PageVersion,
    WikiDirectory,
    WikiGeneration,
    WikiGenerationPage,
    WikiStructureRevision,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _legacy_page(knowledge_base, *, title, status="active"):
    page = KnowledgePage.objects.create(
        knowledge_base=knowledge_base,
        page_type="concept",
        title=title,
        status=status,
        contribution="ai",
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body=f"{title} body",
        change_type="ai_create",
        is_current=True,
    )
    page.current_version = version
    page.save(update_fields=["current_version", "updated_at"])
    return page


def test_audit_reports_all_state_normalized_title_conflicts_without_writes(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    _legacy_page(knowledge_base, title="Run\u3000Book", status="active")
    _legacy_page(knowledge_base, title=" run book ", status="archived")
    before = (
        WikiDirectory.objects.count(),
        WikiStructureRevision.objects.count(),
        WikiGeneration.objects.count(),
    )
    output = StringIO()

    with pytest.raises(CommandError):
        call_command(
            "audit_wiki_directory_readiness",
            knowledge_base_ids=[knowledge_base.id],
            compact=True,
            stdout=output,
        )

    assert "duplicate_page_title_identity" in output.getvalue()
    assert (
        WikiDirectory.objects.count(),
        WikiStructureRevision.objects.count(),
        WikiGeneration.objects.count(),
    ) == before


def test_backfill_dry_run_is_read_only_then_actual_run_is_idempotent(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    first = _legacy_page(knowledge_base, title="Legacy One")
    second = _legacy_page(knowledge_base, title="Legacy Two")
    archived = _legacy_page(knowledge_base, title="Legacy Archived", status="archived")
    relation = PageRelation.objects.create(
        from_page=first,
        to_page=second,
        relation_type="reference",
    )
    dry_run_output = StringIO()

    call_command(
        "backfill_wiki_directory_governance",
        knowledge_base_ids=[knowledge_base.id],
        batch_size=1,
        dry_run=True,
        stdout=dry_run_output,
    )

    knowledge_base.refresh_from_db()
    assert "[DRY-RUN]" in dry_run_output.getvalue()
    assert knowledge_base.directory_migration_state == "legacy"
    assert knowledge_base.active_structure_revision_id is None
    assert knowledge_base.active_generation_id is None
    assert WikiDirectory.objects.filter(knowledge_base=knowledge_base).count() == 0

    first_output = StringIO()
    call_command(
        "backfill_wiki_directory_governance",
        knowledge_base_ids=[knowledge_base.id],
        batch_size=1,
        stdout=first_output,
    )

    knowledge_base.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    archived.refresh_from_db()
    relation.refresh_from_db()
    generation = knowledge_base.active_generation
    unclassified = knowledge_base.directories.get(key="__unclassified__")
    assert knowledge_base.directory_migration_state == "ready"
    assert knowledge_base.directory_enabled is False
    assert generation.status == "active"
    assert generation.structure_revision_id == knowledge_base.active_structure_revision_id
    assert WikiGenerationPage.objects.filter(generation=generation).count() == 2
    assert set(WikiGenerationPage.objects.filter(generation=generation).values_list("page_id", flat=True)) == {first.id, second.id}
    assert {first.directory_id, second.directory_id, archived.directory_id} == {unclassified.id}
    assert {first.directory_assignment_mode, second.directory_assignment_mode, archived.directory_assignment_mode} == {"auto"}
    assert relation.generation_id == generation.id
    assert (
        PageDirectoryChange.objects.filter(
            generation=generation,
            source="baseline_backfill",
        ).count()
        == 3
    )

    counts = (
        WikiDirectory.objects.filter(knowledge_base=knowledge_base).count(),
        WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count(),
        WikiGeneration.objects.filter(knowledge_base=knowledge_base).count(),
        WikiGenerationPage.objects.filter(generation=generation).count(),
        PageDirectoryChange.objects.filter(generation=generation).count(),
    )
    second_output = StringIO()
    call_command(
        "backfill_wiki_directory_governance",
        knowledge_base_ids=[knowledge_base.id],
        batch_size=1,
        stdout=second_output,
    )

    assert "baseline \u5df2\u5b8c\u6210" in second_output.getvalue()
    assert (
        WikiDirectory.objects.filter(knowledge_base=knowledge_base).count(),
        WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count(),
        WikiGeneration.objects.filter(knowledge_base=knowledge_base).count(),
        WikiGenerationPage.objects.filter(generation=generation).count(),
        PageDirectoryChange.objects.filter(generation=generation).count(),
    ) == counts


def test_backfill_rejects_old_running_build_without_starting_fence(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    _legacy_page(knowledge_base, title="Blocked Legacy")
    build_record = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        status="running",
    )
    stderr = StringIO()

    with pytest.raises(CommandError, match=f"failed_kb_ids={knowledge_base.id}"):
        call_command(
            "backfill_wiki_directory_governance",
            knowledge_base_ids=[knowledge_base.id],
            stderr=stderr,
        )

    knowledge_base.refresh_from_db()
    assert f"build_record_ids={build_record.id}" in stderr.getvalue()
    assert knowledge_base.directory_migration_state == "legacy"
    assert knowledge_base.active_structure_revision_id is None
    assert knowledge_base.active_generation_id is None


def test_backfill_resumes_after_interruption_at_persisted_baseline(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    page = _legacy_page(knowledge_base, title="Interrupted Legacy")

    context = _begin_backfill(knowledge_base.id)

    knowledge_base.refresh_from_db()
    assert context is not None
    assert knowledge_base.directory_migration_state == "backfilling"
    assert WikiGeneration.objects.get(pk=context.generation_id).status == "preparing"
    assert WikiGenerationPage.objects.filter(generation_id=context.generation_id).count() == 0

    call_command(
        "backfill_wiki_directory_governance",
        knowledge_base_ids=[knowledge_base.id],
        batch_size=1,
    )

    knowledge_base.refresh_from_db()
    page.refresh_from_db()
    assert knowledge_base.directory_migration_state == "ready"
    assert knowledge_base.active_generation_id == context.generation_id
    assert WikiGenerationPage.objects.filter(
        generation_id=context.generation_id,
        page=page,
    ).exists()


def test_backfill_empty_knowledge_base_creates_empty_active_baseline(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()

    call_command(
        "backfill_wiki_directory_governance",
        knowledge_base_ids=[knowledge_base.id],
    )

    knowledge_base.refresh_from_db()
    assert knowledge_base.directory_migration_state == "ready"
    assert knowledge_base.active_generation.status == "active"
    assert knowledge_base.active_generation.page_members.count() == 0
    assert knowledge_base.directories.filter(key="__unclassified__").count() == 1


def test_backfill_rejects_invalid_page_status_before_starting_fence(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    page = _legacy_page(knowledge_base, title="Invalid State")
    KnowledgePage.objects.filter(pk=page.id).update(status="unexpected")
    stderr = StringIO()

    with pytest.raises(CommandError, match=f"failed_kb_ids={knowledge_base.id}"):
        call_command(
            "backfill_wiki_directory_governance",
            knowledge_base_ids=[knowledge_base.id],
            stderr=stderr,
        )

    knowledge_base.refresh_from_db()
    assert "invalid_status=unexpected" in stderr.getvalue()
    assert knowledge_base.directory_migration_state == "legacy"
    assert knowledge_base.active_generation_id is None
