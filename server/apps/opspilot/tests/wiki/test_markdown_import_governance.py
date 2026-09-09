import io
import zipfile
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.opspilot.models import BuildRecord, KnowledgePage, WikiImportPreflight
from apps.opspilot.services.wiki.markdown_import_governance_service import (
    MarkdownImportGovernanceError,
    execute_markdown_import,
    inspect_markdown_archive,
    preflight_markdown_import,
)
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

pytestmark = pytest.mark.django_db(transaction=True)


def _ready_kb(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    return knowledge_base


def _zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in entries:
            archive.writestr(name, body)
    return buffer.getvalue()


def test_archive_inspection_rejects_empty_and_oversized_payload():
    from apps.opspilot.services.wiki.markdown_import_governance_service import MAX_ARCHIVE_BYTES

    with pytest.raises(MarkdownImportGovernanceError) as empty:
        inspect_markdown_archive(b"", "okf.zip", import_format="okf")
    assert empty.value.code == "archive_empty"

    with pytest.raises(MarkdownImportGovernanceError) as huge:
        inspect_markdown_archive(b"x" * (MAX_ARCHIVE_BYTES + 1), "okf.zip", import_format="okf")
    assert huge.value.code == "archive_size_exceeded"
    assert huge.value.details["max_bytes"] == MAX_ARCHIVE_BYTES
    assert "200MB" in str(huge.value)


def test_archive_inspection_rejects_zip_slip_before_preflight(wiki_factory):
    content = _zip([("../escape.md", "# 越界")])

    with pytest.raises(MarkdownImportGovernanceError) as captured:
        inspect_markdown_archive(content, "unsafe.zip")

    assert captured.value.code == "zip_entry_path_invalid"
    assert WikiImportPreflight.objects.count() == 0


def test_generation_import_success_is_replayable_without_duplicate_pages(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 幂等导入\n\n这是正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="idempotent.md",
        actor="admin",
    )

    first = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="idempotent.md",
        actor="admin",
    )
    replay = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="idempotent.md",
        actor="admin",
    )

    knowledge_base.refresh_from_db()
    record = WikiImportPreflight.objects.get(knowledge_base=knowledge_base)
    assert replay == first
    assert record.status == "consumed"
    assert record.preview["_execution"]["status"] == "success"
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base).count() == 1
    assert first["generation_id"] == knowledge_base.active_generation_id
    assert BuildRecord.objects.get(pk=first["build_record_id"]).status == "success"


def test_preflight_actor_binding_mismatch_does_not_consume_token(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 绑定校验\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="binding.md",
        actor="alice",
    )

    with pytest.raises(MarkdownImportGovernanceError) as captured:
        execute_markdown_import(
            knowledge_base,
            preflight["token"],
            content,
            filename="binding.md",
            actor="bob",
        )

    record = WikiImportPreflight.objects.get(knowledge_base=knowledge_base)
    assert captured.value.code == "preflight_binding_mismatch"
    assert record.status == "active"
    assert record.consumed_at is None


def test_execute_accepts_preflight_after_recorded_expiry(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 过期仍可执行\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="still-valid.md",
        actor="admin",
    )
    WikiImportPreflight.objects.filter(knowledge_base=knowledge_base).update(
        expires_at=timezone.now() - timedelta(days=1),
    )

    result = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="still-valid.md",
        actor="admin",
    )

    assert result["counts"]["created"] == 1
    record = WikiImportPreflight.objects.get(knowledge_base=knowledge_base)
    assert record.status == "consumed"
