"""WikiMaterialViewSet.batch_create 批量创建资料端点测试。

覆盖:
- 校验 knowledge_base 必填
- 校验 files 必填
- 正常路径:多文件一次性入库并投递解析任务
- 失败隔离:个别文件保存失败不影响其他文件
- 对象存储不可用时提示用户并停止后续文件
- 解析任务投递失败不阻塞记录创建
"""

import logging

import pytest
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.opspilot.models import Material, WikiKnowledgeBase
from apps.opspilot.services.wiki.material_file_persist import STORAGE_UNAVAILABLE_MESSAGE


def _kb():
    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


@pytest.fixture(autouse=True)
def _local_material_storage():
    file_field = Material._meta.get_field("file")
    original_storage = file_field.storage
    file_field.storage = InMemoryStorage(base_url="/test-media/")
    try:
        yield
    finally:
        file_field.storage = original_storage


@pytest.mark.django_db
def test_batch_create_requires_knowledge_base(api_client):
    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        {},
        format="multipart",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["result"] is False
    assert "knowledge_base" in body["message"]


@pytest.mark.django_db
def test_batch_create_requires_files(api_client):
    kb = _kb()
    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        {"knowledge_base": kb.id},
        format="multipart",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "files" in body["message"]


@pytest.mark.django_db
def test_batch_create_creates_unbuilt_materials_without_ingest(api_client, monkeypatch):
    kb = _kb()
    dispatched = []

    def fake_delay(material_id, llm_model_id=None):
        dispatched.append(material_id)

    monkeypatch.setattr("apps.opspilot.tasks.wiki_ingest_material_task.delay", fake_delay)

    payload = {
        "knowledge_base": kb.id,
        "ocr_enhance": "false",
        "files": [
            SimpleUploadedFile("a.md", b"# A", content_type="text/markdown"),
            SimpleUploadedFile("b.md", b"# B", content_type="text/markdown"),
            SimpleUploadedFile("c.md", b"# C", content_type="text/markdown"),
        ],
    }
    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        payload,
        format="multipart",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["data"]["items"]) == 3
    assert body["data"]["errors"] == []
    created_names = sorted(item["name"] for item in body["data"]["items"])
    assert created_names == ["a.md", "b.md", "c.md"]
    assert Material.objects.filter(knowledge_base=kb).count() == 3
    assert dispatched == []
    for material in Material.objects.all():
        assert material.material_type == "file"
        assert material.status == "pending"
        assert material.ocr_enhance is False


@pytest.mark.django_db
def test_batch_create_isolates_save_failures(api_client, monkeypatch):
    """个别 Material.objects.create 抛错时,其他文件应继续创建并汇总到 errors。"""
    kb = _kb()
    real_create = Material.objects.create

    def maybe_failing_create(*args, **kwargs):
        if kwargs.get("name") == "boom.md":
            raise RuntimeError("disk full")
        return real_create(*args, **kwargs)

    monkeypatch.setattr(Material.objects, "create", staticmethod(maybe_failing_create))
    monkeypatch.setattr("apps.opspilot.tasks.wiki_ingest_material_task.delay", lambda *a, **kw: None)

    payload = {
        "knowledge_base": kb.id,
        "files": [
            SimpleUploadedFile("ok.md", b"# OK", content_type="text/markdown"),
            SimpleUploadedFile("boom.md", b"data", content_type="text/markdown"),
            SimpleUploadedFile("ok2.md", b"# OK2", content_type="text/markdown"),
        ],
    }
    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        payload,
        format="multipart",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]["items"]) == 2
    assert len(body["data"]["errors"]) == 1
    assert body["data"]["errors"][0]["name"] == "boom.md"
    assert "disk full" in body["data"]["errors"][0]["error"]


@pytest.mark.django_db
def test_batch_create_continues_when_ingest_dispatch_fails(api_client, monkeypatch):
    """任务投递失败时,资料记录应仍创建,只记日志不抛错。"""
    kb = _kb()

    def explode(*a, **kw):
        raise RuntimeError("broker down")

    monkeypatch.setattr("apps.opspilot.tasks.wiki_ingest_material_task.delay", explode)

    payload = {
        "knowledge_base": kb.id,
        "files": [SimpleUploadedFile("x.md", b"# X", content_type="text/markdown")],
    }
    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        payload,
        format="multipart",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["data"]["items"]) == 1
    assert body["data"]["errors"] == []
    assert Material.objects.filter(knowledge_base=kb, name="x.md").exists()


@pytest.mark.django_db
def test_batch_create_rolls_back_when_object_storage_save_fails(api_client, monkeypatch, caplog):
    """对象存储写入抛错时不得留下资料行,并提示用户 MinIO 不可用。"""
    kb = _kb()
    file_field = Material._meta.get_field("file")
    save_calls = []

    def boom(name, content, max_length=None):
        save_calls.append(name)
        raise ConnectionError("minio down")

    monkeypatch.setattr(file_field.storage, "save", boom)
    caplog.set_level(logging.WARNING, logger="opspilot")

    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        {
            "knowledge_base": kb.id,
            "files": [
                SimpleUploadedFile("lost.md", b"# lost", content_type="text/markdown"),
                SimpleUploadedFile("later.md", b"# later", content_type="text/markdown"),
                SimpleUploadedFile("skipped.md", b"# skipped", content_type="text/markdown"),
            ],
        },
        format="multipart",
    )

    assert resp.status_code == 503
    body = resp.json()
    assert body["result"] is False
    assert body["message"] == STORAGE_UNAVAILABLE_MESSAGE
    assert "MinIO" in body["message"]
    assert body["data"]["items"] == []
    assert len(body["data"]["errors"]) == 1
    assert body["data"]["errors"][0]["name"] == "lost.md"
    assert "对象存储不可用" in body["data"]["errors"][0]["error"]
    assert "后续文件已停止上传" in body["data"]["errors"][0]["error"]
    assert not Material.objects.filter(knowledge_base=kb).exists()
    assert len(save_calls) == 1
    records = [
        record for record in caplog.records if record.name == "opspilot" and record.msg == "wiki batch_create 对象存储失败 file=%s kb=%s error_type=%s"
    ]
    assert len(records) == 1
    assert records[0].args == ("lost.md", str(kb.id), "MaterialStorageError")
    assert "minio down" not in records[0].getMessage()


@pytest.mark.django_db
def test_batch_create_rolls_back_when_stored_object_is_missing(api_client, monkeypatch):
    """存储声称写入成功但对象不存在时,回滚资料行并停止后续文件。"""
    kb = _kb()
    file_field = Material._meta.get_field("file")
    save_calls = []
    real_save = file_field.storage.save

    def counting_save(name, content, max_length=None):
        save_calls.append(name)
        return real_save(name, content, max_length=max_length)

    monkeypatch.setattr(file_field.storage, "save", counting_save)
    monkeypatch.setattr(file_field.storage, "exists", lambda name: False)

    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        {
            "knowledge_base": kb.id,
            "files": [
                SimpleUploadedFile("ghost.md", b"# ghost", content_type="text/markdown"),
                SimpleUploadedFile("later.md", b"# later", content_type="text/markdown"),
            ],
        },
        format="multipart",
    )

    assert resp.status_code == 503
    body = resp.json()
    assert body["result"] is False
    assert body["message"] == STORAGE_UNAVAILABLE_MESSAGE
    assert body["data"]["items"] == []
    assert len(body["data"]["errors"]) == 1
    assert "对象存储不可用" in body["data"]["errors"][0]["error"]
    assert not Material.objects.filter(knowledge_base=kb).exists()
    assert len(save_calls) == 1


@pytest.mark.django_db
def test_batch_create_stops_remaining_files_after_later_object_storage_failure(api_client, monkeypatch):
    """已有成功条目后对象存储挂掉时,停止后续文件并保留已成功资料。"""
    kb = _kb()
    file_field = Material._meta.get_field("file")
    save_calls = []
    real_save = file_field.storage.save

    def maybe_fail(name, content, max_length=None):
        save_calls.append(name)
        if len(save_calls) >= 2:
            raise ConnectionError("minio down")
        return real_save(name, content, max_length=max_length)

    monkeypatch.setattr(file_field.storage, "save", maybe_fail)

    resp = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
        {
            "knowledge_base": kb.id,
            "files": [
                SimpleUploadedFile("ok.md", b"# OK", content_type="text/markdown"),
                SimpleUploadedFile("lost.md", b"# lost", content_type="text/markdown"),
                SimpleUploadedFile("skipped.md", b"# skipped", content_type="text/markdown"),
            ],
        },
        format="multipart",
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] is True
    assert [item["name"] for item in body["data"]["items"]] == ["ok.md"]
    assert len(body["data"]["errors"]) == 1
    assert body["data"]["errors"][0]["name"] == "lost.md"
    assert "对象存储不可用" in body["data"]["errors"][0]["error"]
    assert "后续文件已停止上传" in body["data"]["errors"][0]["error"]
    assert Material.objects.filter(knowledge_base=kb).count() == 1
    assert Material.objects.filter(knowledge_base=kb, name="ok.md").exists()
    assert len(save_calls) == 2
