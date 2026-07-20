"""WikiMaterialViewSet.batch_create 批量创建资料端点测试。

覆盖:
- 校验 knowledge_base 必填
- 校验 files 必填
- 正常路径:多文件一次性入库并投递解析任务
- 失败隔离:个别文件保存失败不影响其他文件
- 解析任务投递失败不阻塞记录创建
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.opspilot.models import Material, WikiKnowledgeBase


def _kb():
    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


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
def test_batch_create_creates_materials_and_enqueues_ingest(api_client, monkeypatch):
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
    assert sorted(dispatched) == sorted(m.id for m in Material.objects.all())
    for material in Material.objects.all():
        assert material.material_type == "file"
        assert material.status == "parsing"
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
