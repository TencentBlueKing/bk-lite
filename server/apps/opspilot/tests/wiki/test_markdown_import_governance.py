import io
import zipfile
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.opspilot.models import BuildRecord, KnowledgePage, WikiImportPreflight
from apps.opspilot.services.wiki.markdown_import_governance_service import (
    TOKEN_TTL_MINUTES,
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


def test_execute_rejects_preflight_after_recorded_expiry(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 过期应失败\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="expired.md",
        actor="admin",
    )
    assert preflight["expires_in_seconds"] == TOKEN_TTL_MINUTES * 60
    WikiImportPreflight.objects.filter(knowledge_base=knowledge_base).update(
        expires_at=timezone.now() - timedelta(days=1),
    )

    with pytest.raises(MarkdownImportGovernanceError) as captured:
        execute_markdown_import(
            knowledge_base,
            preflight["token"],
            content,
            filename="expired.md",
            actor="admin",
        )

    assert captured.value.code == "preflight_token_expired"
    assert captured.value.status_code == 409
    record = WikiImportPreflight.objects.get(knowledge_base=knowledge_base)
    assert record.status == "active"
    assert record.consumed_at is None


def _okf_concept(title, body="正文"):
    return f"---\ntype: concept\ntitle: {title}\n---\n\n{body}\n"


def test_create_folders_preflight_rejects_markdown_and_accepts_zip_kinds(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)

    with pytest.raises(MarkdownImportGovernanceError) as markdown_error:
        preflight_markdown_import(
            knowledge_base,
            "# 单页\n\n正文。".encode("utf-8"),
            filename="page.md",
            actor="admin",
            options={"create_directories_from_folders": True},
        )
    assert markdown_error.value.code == "folder_structure_requires_third_party"

    markdown_default = preflight_markdown_import(
        knowledge_base,
        "# 单页默认\n\n正文。".encode("utf-8"),
        filename="page.md",
        actor="admin",
    )
    assert markdown_default["preview"]["archive_kind"] == "markdown"
    assert not (markdown_default["preview"].get("structure_preview") or {}).get("create_directories_from_folders")

    third_party = preflight_markdown_import(
        knowledge_base,
        _zip([("guides/intro.md", "# Intro\n\nbody")]),
        filename="pack.zip",
        actor="admin",
        options={"create_directories_from_folders": True},
    )
    assert third_party["preview"]["archive_kind"] == "third_party"
    assert third_party["preview"]["structure_preview"]["create_directories_from_folders"] is True
    assert third_party["preview"]["structure_preview"]["create_directory_count"] >= 1

    okf_zip = _zip(
        [
            ("guides/intro.md", _okf_concept("Intro")),
            ("refs/note.md", _okf_concept("Note")),
        ]
    )
    okf_off = preflight_markdown_import(
        knowledge_base,
        okf_zip,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf", "create_directories_from_folders": False},
    )
    assert okf_off["preview"]["archive_kind"] == "okf"
    assert not (okf_off["preview"].get("structure_preview") or {}).get("create_directories_from_folders")

    okf_on = preflight_markdown_import(
        knowledge_base,
        okf_zip,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf", "create_directories_from_folders": True},
    )
    assert okf_on["preview"]["archive_kind"] == "okf"
    assert okf_on["preview"]["structure_preview"]["create_directories_from_folders"] is True
    assert okf_on["preview"]["structure_preview"]["create_directory_count"] >= 1
