import hashlib
import io
import logging
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.opspilot.models import BuildRecord, KnowledgePage, WikiGeneration, WikiImportPreflight, WikiKnowledgeBase
from apps.opspilot.services.wiki.markdown_import_governance_service import (
    MarkdownImportGovernanceError,
    enqueue_markdown_import,
    execute_markdown_import,
    preflight_markdown_import,
)
from apps.opspilot.services.wiki.parsed_media_service import delete_import_archive, read_import_archive_bytes, save_import_archive_bytes
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

pytestmark = pytest.mark.django_db(transaction=True)


class _MemoryStorage:
    def __init__(self):
        self.files = {}

    def exists(self, path):
        return path in self.files

    def save(self, path, content):
        self.files[path] = content.read() if hasattr(content, "read") else content
        return path

    def open(self, path, mode="rb"):
        if path not in self.files:
            raise FileNotFoundError(path)
        return io.BytesIO(self.files[path])

    def delete(self, path):
        self.files.pop(path, None)


@pytest.fixture
def import_storage(monkeypatch):
    storage = _MemoryStorage()
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.parsed_media_service._MEDIA_STORAGE",
        storage,
    )
    return storage


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


def test_import_archive_staging_is_scoped_to_knowledge_base(import_storage):
    digest = hashlib.sha256(b"pack").hexdigest()
    locator = save_import_archive_bytes(3, digest, b"pack")
    assert locator == f"wiki/import-staging/3/{digest}.zip"
    assert read_import_archive_bytes(locator, knowledge_base_id=3) == b"pack"
    with pytest.raises(FileNotFoundError):
        read_import_archive_bytes(locator, knowledge_base_id=9)
    with pytest.raises(FileNotFoundError):
        read_import_archive_bytes("wiki/media/3/pages/ab.zip", knowledge_base_id=3)
    assert delete_import_archive(locator, knowledge_base_id=3) is True
    assert locator not in import_storage.files


def test_enqueue_markdown_import_does_not_write_pages(wiki_factory, import_storage):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 异步导入\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="async.md",
        actor="admin",
    )

    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="async.md",
        actor="admin",
    )

    assert payload["async"] is True
    assert payload["accepted"] is True
    assert payload["queued"] is True
    assert dispatch["build_record_id"] == payload["build_record_id"]
    assert not KnowledgePage.objects.filter(knowledge_base=knowledge_base).exists()
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert build.trigger == "markdown_import"
    assert build.status == "running"
    assert build.stage == "queued"
    assert dispatch["archive_locator"] in import_storage.files

    again, again_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="async.md",
        actor="admin",
    )
    assert again["build_record_id"] == payload["build_record_id"]
    assert again_dispatch is None


def test_execute_task_imports_staged_archive_and_deletes_it(wiki_factory, import_storage, monkeypatch):
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki.wiki_enrich_markdown_import_search_task.delay",
        lambda *args, **kwargs: None,
    )

    knowledge_base = _ready_kb(wiki_factory)
    content = "# 任务导入\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="task.md",
        actor="admin",
    )
    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="task.md",
        actor="admin",
    )

    result = wiki_execute_markdown_import_task.run(
        knowledge_base.id,
        dispatch["build_record_id"],
        preflight["token"],
        dispatch["archive_locator"],
        dispatch["filename"],
        "admin",
    )

    assert result["status"] == "success"
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base, title="任务导入").exists()
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert build.status == "success"
    assert dispatch["archive_locator"] not in import_storage.files


def test_import_markdown_execute_endpoint_enqueues_without_writing_pages(
    wiki_factory,
    api_client,
    import_storage,
    monkeypatch,
):
    from apps.opspilot import tasks

    knowledge_base = _ready_kb(wiki_factory)
    content = _zip([("pages/async.md", "# 接口导入\n\n正文。")])
    calls = []

    class Task:
        @staticmethod
        def delay(kb_id, build_record_id, token, archive_locator, filename, operator):
            calls.append(
                {
                    "kb_id": kb_id,
                    "build_record_id": build_record_id,
                    "token": token,
                    "archive_locator": archive_locator,
                    "filename": filename,
                    "operator": operator,
                }
            )

    monkeypatch.setattr(tasks, "wiki_execute_markdown_import_task", Task)

    preflight = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{knowledge_base.id}/import_markdown_preflight/",
        {
            "file": SimpleUploadedFile("async.zip", content, content_type="application/zip"),
            "options": "{}",
        },
        format="multipart",
    )
    assert preflight.status_code == 200, preflight.content
    token = preflight.json()["data"]["token"]

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{knowledge_base.id}/import_markdown_execute/",
        {
            "file": SimpleUploadedFile("async.zip", content, content_type="application/zip"),
            "token": token,
        },
        format="multipart",
    )
    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["async"] is True
    assert data["accepted"] is True
    assert data["build_record_id"]
    assert not KnowledgePage.objects.filter(knowledge_base=knowledge_base).exists()
    assert len(calls) == 1
    assert calls[0]["kb_id"] == knowledge_base.id
    assert calls[0]["build_record_id"] == data["build_record_id"]
    assert calls[0]["filename"] == "async.zip"
    assert WikiImportPreflight.objects.get(knowledge_base=knowledge_base).status == "active"

    repeat = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{knowledge_base.id}/import_markdown_execute/",
        {
            "file": SimpleUploadedFile("async.zip", content, content_type="application/zip"),
            "token": token,
        },
        format="multipart",
    )
    assert repeat.status_code == 200, repeat.content
    assert repeat.json()["data"]["build_record_id"] == data["build_record_id"]
    assert len(calls) == 1


def test_enqueue_rejects_when_rebuild_is_running(wiki_factory, import_storage):
    knowledge_base = _ready_kb(wiki_factory)
    BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="rebuild",
        status="running",
        stage="generating",
    )
    content = "# 冲突\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="busy.md",
        actor="admin",
    )
    with pytest.raises(MarkdownImportGovernanceError) as captured:
        enqueue_markdown_import(
            knowledge_base,
            preflight["token"],
            content,
            filename="busy.md",
            actor="admin",
        )
    assert captured.value.code == "knowledge_base_build_in_progress"


def test_direct_execute_still_imports_synchronously(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 同步回归\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="sync.md",
        actor="admin",
    )
    result = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="sync.md",
        actor="admin",
    )
    assert result["counts"]["created"] == 1
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base, title="同步回归").exists()


def test_markdown_import_runs_search_enrichment_after_activation(wiki_factory, monkeypatch):
    seen = {}

    def fake_enrich(knowledge_base_id, generation_id, page_ids):
        generation = WikiGeneration.objects.get(pk=generation_id)
        current = WikiKnowledgeBase.objects.get(pk=knowledge_base_id)
        seen["status"] = generation.status
        seen["active"] = current.active_generation_id == generation_id
        seen["pages"] = KnowledgePage.objects.filter(knowledge_base_id=knowledge_base_id).count()
        seen["page_ids"] = list(page_ids)
        return {"status": "ok", "updated": 0, "llm_called": False}

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.markdown_import_governance_service.run_markdown_import_search_enrichment",
        fake_enrich,
    )
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 先可见\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="visible.md",
        actor="admin",
    )
    result = execute_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="visible.md",
        actor="admin",
    )
    assert result["counts"]["created"] == 1
    assert seen["status"] == "active"
    assert seen["active"] is True
    assert seen["pages"] == 1
    assert seen["page_ids"] == [result["pages"][0]["page_id"]]


def test_execute_task_defers_search_enrichment_until_pages_are_visible(
    wiki_factory,
    import_storage,
    monkeypatch,
):
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    delayed = []
    enrich_calls = []

    def fake_delay(kb_id, generation_id, page_ids):
        delayed.append((kb_id, generation_id, list(page_ids)))

    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki.wiki_enrich_markdown_import_search_task.delay",
        fake_delay,
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.markdown_import_governance_service.run_markdown_import_search_enrichment",
        lambda *args: enrich_calls.append(args) or {"status": "ok"},
    )
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 后台索引\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="defer.md",
        actor="admin",
    )
    _payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="defer.md",
        actor="admin",
    )
    result = wiki_execute_markdown_import_task.run(
        knowledge_base.id,
        dispatch["build_record_id"],
        preflight["token"],
        dispatch["archive_locator"],
        dispatch["filename"],
        "admin",
    )
    knowledge_base.refresh_from_db()
    assert result["status"] == "success"
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base, title="后台索引").exists()
    assert knowledge_base.active_generation_id == result["generation_id"]
    assert enrich_calls == []
    assert delayed == [
        (knowledge_base.id, result["generation_id"], [result["pages"][0]["page_id"]]),
    ]


def test_execute_task_search_enrich_dispatch_failure_runs_inline(
    wiki_factory,
    import_storage,
    monkeypatch,
    caplog,
):
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    enrich_calls = []

    def boom(*_args, **_kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(
        "apps.opspilot.tasks.wiki.wiki_enrich_markdown_import_search_task.delay",
        boom,
    )
    monkeypatch.setattr(
        "apps.opspilot.services.wiki.markdown_import_governance_service.run_markdown_import_search_enrichment",
        lambda *args: enrich_calls.append(args) or {"status": "ok"},
    )
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 投递失败\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="fallback.md",
        actor="admin",
    )
    _payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="fallback.md",
        actor="admin",
    )
    with caplog.at_level(logging.WARNING, logger="opspilot"):
        result = wiki_execute_markdown_import_task.run(
            knowledge_base.id,
            dispatch["build_record_id"],
            preflight["token"],
            dispatch["archive_locator"],
            dispatch["filename"],
            "admin",
        )
    assert result["status"] == "success"
    assert KnowledgePage.objects.filter(knowledge_base=knowledge_base, title="投递失败").exists()
    assert enrich_calls == [
        (knowledge_base.id, result["generation_id"], [result["pages"][0]["page_id"]]),
    ]
    records = [record for record in caplog.records if record.getMessage().startswith("wiki markdown import search enrich dispatch failed")]
    assert len(records) == 1
    assert records[0].msg == ("wiki markdown import search enrich dispatch failed knowledge_base=%s generation_id=%s failed_stage=%s error_type=%s")
    assert records[0].args == (
        knowledge_base.id,
        result["generation_id"],
        "dispatch_search_enrich",
        "RuntimeError",
    )
    rendered = records[0].getMessage()
    assert str(knowledge_base.id) in rendered
    assert "dispatch_search_enrich" in rendered
    assert "RuntimeError" in rendered
    assert "broker down" not in rendered
