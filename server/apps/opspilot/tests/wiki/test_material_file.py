"""文件资料解析(.txt/.md)测试。MinIO 读取经 _read_file 注入,避免依赖对象存储。"""

import pytest

from apps.opspilot.services.wiki import material_service


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _file_material(kb, name):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="file")


@pytest.mark.django_db
def test_extract_markdown_file(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "guide.md")
    monkeypatch.setattr(material_service, "_read_file", lambda m: ("guide.md", b"# \xe6\xa0\x87\xe9\xa2\x98\nbody"))
    text = material_service.extract_text(mat)
    assert "标题" in text and "body" in text


@pytest.mark.django_db
def test_extract_txt_file(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "notes.txt")
    monkeypatch.setattr(material_service, "_read_file", lambda m: ("notes.txt", b"plain text content"))
    assert material_service.extract_text(mat) == "plain text content"


@pytest.mark.django_db
def test_unsupported_extension_returns_empty(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "scan.pdf")
    monkeypatch.setattr(material_service, "_read_file", lambda m: ("scan.pdf", b"%PDF-1.4 ..."))
    assert material_service.extract_text(mat) == ""


@pytest.mark.django_db
def test_ingest_markdown_file_sets_done(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "doc.md")
    monkeypatch.setattr(material_service, "_read_file", lambda m: ("doc.md", b"hello wiki"))
    out = material_service.ingest_material(mat)
    assert out.status == "done"
    assert out.ai_summary == "hello wiki"  # 无模型回退为截断正文
    assert out.content_hash
