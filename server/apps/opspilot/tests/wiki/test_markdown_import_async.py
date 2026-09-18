import hashlib
import io
import logging
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.opspilot.models import BuildRecord, KnowledgePage, WikiGeneration, WikiImportPreflight, WikiKnowledgeBase
from apps.opspilot.services.wiki.markdown_import_governance_service import (
    MarkdownImportGovernanceError,
    _bind_import_build,
    _preflight_execution_result,
    _touch_markdown_import_build,
    claim_markdown_import_execution,
    enqueue_markdown_import,
    execute_markdown_import,
    markdown_import_celery_task_is_live,
    persist_markdown_import_celery_task_id,
    preflight_markdown_import,
    reclaim_stale_markdown_import_builds,
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


def _age_markdown_import_build(build, *, hours=3):
    aged = timezone.now() - timedelta(hours=hours)
    BuildRecord.objects.filter(pk=build.pk).update(created_at=aged, updated_at=aged)
    build.refresh_from_db()
    return build


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
    assert dispatch["celery_task_id"]
    assert not KnowledgePage.objects.filter(knowledge_base=knowledge_base).exists()
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert build.trigger == "markdown_import"
    assert build.status == "running"
    assert build.stage == "queued"
    assert not (build.inputs or {}).get("celery_task_id")
    assert dispatch["archive_locator"] in import_storage.files

    assert persist_markdown_import_celery_task_id(build.pk, dispatch["celery_task_id"]) is True
    again, again_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="async.md",
        actor="admin",
    )
    assert again["build_record_id"] == payload["build_record_id"]
    assert again_dispatch is None
    build.refresh_from_db()
    assert build.inputs["celery_task_id"] == dispatch["celery_task_id"]


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


def test_execute_task_imports_staged_archive_and_deletes_it(wiki_factory, import_storage, monkeypatch):
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    assert wiki_execute_markdown_import_task.acks_late is True
    assert wiki_execute_markdown_import_task.reject_on_worker_lost is True

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
        operator="admin",
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
        def apply_async(args=None, kwargs=None, task_id=None):
            calls.append({"args": args, "kwargs": kwargs or {}, "task_id": task_id})

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
    assert calls[0]["kwargs"]["kb_id"] == knowledge_base.id
    assert calls[0]["kwargs"]["build_record_id"] == data["build_record_id"]
    assert calls[0]["kwargs"]["operator"]
    assert "preflight_token" not in calls[0]["kwargs"]
    assert calls[0]["args"] in (None, ())
    assert calls[0]["task_id"]
    build = BuildRecord.objects.get(pk=data["build_record_id"])
    assert build.inputs["celery_task_id"] == calls[0]["task_id"]
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


def test_enqueue_redelivers_when_delay_never_happened(wiki_factory, import_storage):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 未投递\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="undelayed.md",
        actor="admin",
    )
    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="undelayed.md",
        actor="admin",
    )
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert not (build.inputs or {}).get("celery_task_id")

    again, again_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="undelayed.md",
        actor="admin",
    )
    assert again["build_record_id"] == payload["build_record_id"]
    assert again_dispatch is not None
    assert again_dispatch["celery_task_id"]
    assert again_dispatch["celery_task_id"] != dispatch["celery_task_id"]
    build.refresh_from_db()
    assert build.status == "running"
    assert not (build.inputs or {}).get("celery_task_id")


def test_enqueue_does_not_redeliver_recorded_celery_task_id(wiki_factory, import_storage):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 已投递\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="recorded.md",
        actor="admin",
    )
    payload, first_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="recorded.md",
        actor="admin",
    )
    assert persist_markdown_import_celery_task_id(payload["build_record_id"], first_dispatch["celery_task_id"])

    again, again_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="recorded.md",
        actor="admin",
    )
    assert again["build_record_id"] == payload["build_record_id"]
    assert again_dispatch is None
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert build.status == "running"
    assert build.inputs["celery_task_id"] == first_dispatch["celery_task_id"]


def test_rebuild_rejects_live_markdown_import(wiki_factory, api_client, monkeypatch):
    from apps.opspilot import tasks
    from apps.opspilot.models import BuildRecord

    knowledge_base = _ready_kb(wiki_factory)
    BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="running",
        stage="queued",
        inputs={"celery_task_id": "live-import-task"},
    )

    class Task:
        @staticmethod
        def delay(*args, **kwargs):
            pytest.fail("live markdown import should block rebuild")

    monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)
    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{knowledge_base.id}/rebuild/",
        {},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "knowledge_base_build_in_progress"
    assert not BuildRecord.objects.filter(knowledge_base=knowledge_base, trigger="rebuild").exists()


def test_rebuild_reclaims_stale_markdown_import(wiki_factory, api_client, monkeypatch):
    from apps.opspilot import tasks
    from apps.opspilot.models import BuildRecord

    knowledge_base = _ready_kb(wiki_factory)
    stale = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="running",
        stage="queued",
        inputs={"preflight_id": None},
    )
    calls = []

    class Task:
        @staticmethod
        def delay(*args, **kwargs):
            calls.append(args)

    monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)
    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{knowledge_base.id}/rebuild/",
        {},
        format="json",
    )
    assert response.status_code == 200, response.content
    stale.refresh_from_db()
    assert stale.status == "failed"
    assert "markdown_import_stale" in stale.errors[0]
    assert stale.inputs.get("celery_task_id")
    assert len(calls) == 1
    assert BuildRecord.objects.filter(knowledge_base=knowledge_base, trigger="rebuild", status="running").exists()


def test_execute_task_skips_stale_celery_identity(wiki_factory, import_storage):
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    knowledge_base = _ready_kb(wiki_factory)
    content = "# 过期工人\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="stale-worker.md",
        actor="admin",
    )
    payload, _dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="stale-worker.md",
        actor="admin",
    )
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    inputs = dict(build.inputs or {})
    inputs["celery_task_id"] = "owner-task"
    build.inputs = inputs
    build.save(update_fields=["inputs", "updated_at"])

    wiki_execute_markdown_import_task.push_request(id="old-worker-task")
    try:
        result = wiki_execute_markdown_import_task.run(
            knowledge_base.id,
            build.pk,
            operator="admin",
        )
    finally:
        wiki_execute_markdown_import_task.pop_request()

    assert result == {"status": "skipped", "code": "stale_celery_task"}
    build.refresh_from_db()
    assert build.status == "running"
    assert not KnowledgePage.objects.filter(knowledge_base=knowledge_base).exists()


def test_recorded_celery_task_id_is_live_without_inspect():
    assert markdown_import_celery_task_is_live("recorded-task") is True
    assert markdown_import_celery_task_is_live("") is False
    assert markdown_import_celery_task_is_live(None) is False


def test_reclaim_does_not_close_fresh_recorded_id(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="running",
        stage="queued",
        inputs={"celery_task_id": "recorded-import-task"},
    )

    assert reclaim_stale_markdown_import_builds(knowledge_base.pk) == 0
    build.refresh_from_db()
    assert build.status == "running"
    assert build.inputs["celery_task_id"] == "recorded-import-task"


def test_reclaim_closes_recorded_id_after_stale_timeout(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="running",
        stage="queued",
        inputs={"celery_task_id": "aged-import-task", "preflight_id": None},
    )
    _age_markdown_import_build(build)

    assert reclaim_stale_markdown_import_builds(knowledge_base.pk) == 1
    build.refresh_from_db()
    assert build.status == "failed"
    assert "markdown_import_stale" in build.errors[0]
    assert build.inputs.get("celery_task_id")
    assert build.inputs["celery_task_id"] != "aged-import-task"


def test_enqueue_retries_after_recorded_id_goes_stale(wiki_factory, import_storage):
    knowledge_base = _ready_kb(wiki_factory)
    content = "# 超时重投\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="aged.md",
        actor="admin",
    )
    payload, first_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="aged.md",
        actor="admin",
    )
    assert persist_markdown_import_celery_task_id(payload["build_record_id"], first_dispatch["celery_task_id"])
    stale = BuildRecord.objects.get(pk=payload["build_record_id"])
    _age_markdown_import_build(stale)

    again, again_dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="aged.md",
        actor="admin",
    )
    stale.refresh_from_db()
    assert stale.status == "failed"
    assert again_dispatch is not None
    assert again["build_record_id"] != payload["build_record_id"]
    fresh = BuildRecord.objects.get(pk=again["build_record_id"])
    assert fresh.status == "running"
    assert not (fresh.inputs or {}).get("celery_task_id")


def test_rebuild_reclaims_stale_recorded_markdown_import(wiki_factory, api_client, monkeypatch):
    from apps.opspilot import tasks

    knowledge_base = _ready_kb(wiki_factory)
    stale = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="running",
        stage="queued",
        inputs={"celery_task_id": "aged-import-task"},
    )
    _age_markdown_import_build(stale)
    calls = []

    class Task:
        @staticmethod
        def delay(*args, **kwargs):
            calls.append(args)

    monkeypatch.setattr(tasks, "wiki_rebuild_kb_task", Task)
    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{knowledge_base.id}/rebuild/",
        {},
        format="json",
    )
    assert response.status_code == 200, response.content
    stale.refresh_from_db()
    assert stale.status == "failed"
    assert "markdown_import_stale" in stale.errors[0]
    assert len(calls) == 1


def test_heartbeat_keeps_recorded_import_from_ttl_reclaim(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="running",
        stage="generating",
        inputs={"celery_task_id": "heartbeat-keeps-live"},
    )
    _age_markdown_import_build(build)
    _touch_markdown_import_build(build)
    assert reclaim_stale_markdown_import_builds(knowledge_base.pk) == 0
    build.refresh_from_db()
    assert build.status == "running"
    assert build.inputs["celery_task_id"] == "heartbeat-keeps-live"


def test_claimed_worker_ttl_reclaim_does_not_activate_or_write_preflight(wiki_factory, import_storage, monkeypatch):
    from django.db import transaction

    from apps.opspilot.services.wiki.build_generation_service import finalize_build_generation as original_finalize
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    knowledge_base = _ready_kb(wiki_factory)
    bootstrap_generation_id = knowledge_base.active_generation_id
    content = "# 超时回收不得激活\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="ttl-fence.md",
        actor="admin",
    )
    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="ttl-fence.md",
        actor="admin",
    )
    assert persist_markdown_import_celery_task_id(payload["build_record_id"], dispatch["celery_task_id"])

    def reclaim_then_finalize(*args, **kwargs):
        build = BuildRecord.objects.get(pk=payload["build_record_id"])
        _age_markdown_import_build(build)
        with transaction.atomic():
            WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base.pk)
            assert reclaim_stale_markdown_import_builds(knowledge_base.pk) == 1
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.markdown_import_governance_service.finalize_build_generation",
        reclaim_then_finalize,
    )

    wiki_execute_markdown_import_task.push_request(id=dispatch["celery_task_id"])
    try:
        result = wiki_execute_markdown_import_task.run(
            knowledge_base.id,
            dispatch["build_record_id"],
            operator="admin",
        )
    finally:
        wiki_execute_markdown_import_task.pop_request()

    assert result == {"status": "skipped", "code": "markdown_import_fenced"}
    knowledge_base.refresh_from_db()
    assert knowledge_base.active_generation_id == bootstrap_generation_id
    assert not WikiGeneration.objects.filter(
        knowledge_base=knowledge_base,
        pipeline_version="wiki-markdown-import-v1",
        status="active",
    ).exists()
    record = WikiImportPreflight.objects.get(knowledge_base=knowledge_base)
    assert _preflight_execution_result(record) is None
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert build.status == "failed"
    assert "markdown_import_stale" in build.errors[0]


def test_fenced_worker_does_not_delete_restaged_archive(wiki_factory, import_storage, monkeypatch):
    from django.db import transaction

    from apps.opspilot.services.wiki.build_generation_service import finalize_build_generation as original_finalize
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    knowledge_base = _ready_kb(wiki_factory)
    content = "# 回收后重投不得删归档\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="ttl-keep-staging.md",
        actor="admin",
    )
    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="ttl-keep-staging.md",
        actor="admin",
    )
    assert persist_markdown_import_celery_task_id(payload["build_record_id"], dispatch["celery_task_id"])
    locator = dispatch["archive_locator"]

    def reclaim_reenqueue_then_finalize(*args, **kwargs):
        build = BuildRecord.objects.get(pk=payload["build_record_id"])
        _age_markdown_import_build(build)
        with transaction.atomic():
            WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base.pk)
            assert reclaim_stale_markdown_import_builds(knowledge_base.pk) == 1
        again, again_dispatch = enqueue_markdown_import(
            knowledge_base,
            preflight["token"],
            content,
            filename="ttl-keep-staging.md",
            actor="admin",
        )
        assert again_dispatch is not None
        assert again["build_record_id"] != payload["build_record_id"]
        assert locator in import_storage.files
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.markdown_import_governance_service.finalize_build_generation",
        reclaim_reenqueue_then_finalize,
    )

    wiki_execute_markdown_import_task.push_request(id=dispatch["celery_task_id"])
    try:
        result = wiki_execute_markdown_import_task.run(
            knowledge_base.id,
            dispatch["build_record_id"],
            operator="admin",
        )
    finally:
        wiki_execute_markdown_import_task.pop_request()

    assert result == {"status": "skipped", "code": "markdown_import_fenced"}
    assert locator in import_storage.files
    assert read_import_archive_bytes(locator, knowledge_base_id=knowledge_base.id) == content


def test_claim_missing_build_returns_import_build_not_found(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    build, early = claim_markdown_import_execution(knowledge_base.pk, 9_999_999, "task-id")
    assert build is None
    assert early == {
        "status": "failed",
        "code": "markdown_import_build_not_found",
        "retryable": False,
    }


def test_reclaim_then_old_worker_skips(wiki_factory, import_storage):
    from django.db import transaction

    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    knowledge_base = _ready_kb(wiki_factory)
    content = "# 回收工人\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="reclaim-worker.md",
        actor="admin",
    )
    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="reclaim-worker.md",
        actor="admin",
    )
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    assert not (build.inputs or {}).get("celery_task_id")

    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base.pk)
        assert reclaim_stale_markdown_import_builds(knowledge_base.pk) == 1

    build.refresh_from_db()
    fencing_token = build.inputs["celery_task_id"]
    assert fencing_token
    assert fencing_token != dispatch["celery_task_id"]
    assert build.status == "failed"

    wiki_execute_markdown_import_task.push_request(id=dispatch["celery_task_id"])
    try:
        result = wiki_execute_markdown_import_task.run(
            knowledge_base.id,
            build.pk,
            operator="admin",
        )
    finally:
        wiki_execute_markdown_import_task.pop_request()

    assert result == {"status": "skipped", "code": "stale_celery_task"}
    build.refresh_from_db()
    assert build.status == "failed"
    assert build.inputs["celery_task_id"] == fencing_token
    assert not KnowledgePage.objects.filter(knowledge_base=knowledge_base).exists()


def test_bind_import_build_does_not_revive_failed(wiki_factory):
    knowledge_base = _ready_kb(wiki_factory)
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="failed",
        stage="failed",
        inputs={"archive_sha256": "abc", "archive_kind": "md"},
    )

    class Inspected:
        archive_sha256 = "abc"
        archive_kind = "md"

    with pytest.raises(MarkdownImportGovernanceError) as captured:
        _bind_import_build(knowledge_base, Inspected(), existing_build_record_id=build.pk)
    assert captured.value.code == "markdown_import_build_terminal"
    build.refresh_from_db()
    assert build.status == "failed"


def test_complete_import_build_does_not_overwrite_failed(wiki_factory):
    from apps.opspilot.services.wiki.markdown_import_governance_service import _complete_import_build

    knowledge_base = _ready_kb(wiki_factory)
    build = BuildRecord.objects.create(
        knowledge_base=knowledge_base,
        trigger="markdown_import",
        status="failed",
        stage="failed",
        progress=100,
    )
    _complete_import_build(
        build,
        counts={"created": 1},
        affected_page_ids=[1],
        generation_id=1,
        relation_result={},
        import_build_id=build.pk,
    )
    build.refresh_from_db()
    assert build.status == "failed"
    assert build.stage == "failed"


def test_execute_task_skips_failed_build(wiki_factory, import_storage):
    from apps.opspilot.tasks.wiki import wiki_execute_markdown_import_task

    knowledge_base = _ready_kb(wiki_factory)
    content = "# 失败不可复活\n\n正文。".encode("utf-8")
    preflight = preflight_markdown_import(
        knowledge_base,
        content,
        filename="failed-bind.md",
        actor="admin",
    )
    payload, dispatch = enqueue_markdown_import(
        knowledge_base,
        preflight["token"],
        content,
        filename="failed-bind.md",
        actor="admin",
    )
    build = BuildRecord.objects.get(pk=payload["build_record_id"])
    build.status = "failed"
    build.stage = "failed"
    build.save(update_fields=["status", "stage", "updated_at"])

    wiki_execute_markdown_import_task.push_request(id=dispatch["celery_task_id"])
    try:
        result = wiki_execute_markdown_import_task.run(
            knowledge_base.id,
            build.pk,
            operator="admin",
        )
    finally:
        wiki_execute_markdown_import_task.pop_request()

    assert result == {"status": "skipped", "code": "markdown_import_build_terminal"}
    build.refresh_from_db()
    assert build.status == "failed"
    assert not KnowledgePage.objects.filter(knowledge_base=knowledge_base).exists()


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
        operator="admin",
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
            operator="admin",
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
