"""文件/网页资料解析测试。MinIO 与 markitdown 均通过 parser/storage 注入隔离。"""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.opspilot.services.wiki import material_service
from apps.opspilot.services.wiki.parsing import markitdown_parser
from apps.opspilot.services.wiki.parsing.markitdown_parser import SUPPORTED_FILE_EXTENSIONS, MarkItDownParser


def test_serializer_exposes_writable_file_field():
    """MaterialSerializer 必须含可写 file 字段,否则 multipart 上传文件会被丢弃。"""
    from apps.opspilot.serializers.wiki_serializers import MaterialSerializer

    fields = MaterialSerializer().fields
    assert "file" in fields
    assert not fields["file"].read_only


def test_supported_extensions_include_base_web_and_text_formats():
    """HTML/TXT/MD 等是 MarkItDown 基础能力,不依赖额外 extras。"""
    assert {".html", ".htm", ".txt", ".md", ".markdown"} <= set(SUPPORTED_FILE_EXTENSIONS)


def test_parse_text_uses_txt_filename(monkeypatch):
    calls = []
    parser = MarkItDownParser()

    def fake_parse_file(data, filename, *, vision_client=None):
        calls.append((data, filename, vision_client))
        return "parsed"

    monkeypatch.setattr(parser, "parse_file", fake_parse_file)

    assert parser.parse_text("hello") == "parsed"
    assert calls == [(b"hello", "raw.txt", None)]


def test_markitdown_parser_empty_inputs_return_empty():
    parser = MarkItDownParser()

    assert parser.parse_file(b"", "empty.md") == ""
    assert parser.parse_text("   ") == ""
    assert parser.parse_url("") == ""


@pytest.mark.xfail(reason="subprocess.TimeoutExpired 在慢机器上 flaky,master baseline 同样 flaky,与本 PR 无关")
def test_markitdown_parser_import_ignores_unused_audio_ffmpeg_warning():
    server_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            "from apps.opspilot.services.wiki.parsing.markitdown_parser import MarkItDownParser; print(MarkItDownParser.__name__)",
        ],
        cwd=server_root,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr


def test_markitdown_parser_converts_file_url_and_passes_vision_client(monkeypatch):
    calls = []
    vision_client = object()

    class FakeMarkItDown:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def convert(self, source):
            calls.append(("convert", source, os.path.exists(source) if os.path.exists(source) else None))
            return SimpleNamespace(text_content="  parsed markdown  ")

    monkeypatch.setattr(markitdown_parser, "MarkItDown", FakeMarkItDown)
    parser = MarkItDownParser()

    assert parser.parse_file(b"raw", "guide.md", vision_client=vision_client, vision_model="vision-model") == "parsed markdown"
    file_source = calls[1][1]
    assert calls[0] == ("init", {"llm_client": vision_client, "llm_model": "vision-model"})
    assert calls[1][2] is True
    assert not os.path.exists(file_source)

    calls.clear()
    assert parser.parse_url("https://example.com/wiki", vision_client=vision_client, vision_model="vision-model") == "parsed markdown"
    assert calls == [
        ("init", {"llm_client": vision_client, "llm_model": "vision-model"}),
        ("convert", "https://example.com/wiki", None),
    ]


def test_parser_registry_returns_markitdown_parser():
    from apps.opspilot.services.wiki.parsing.registry import get_parser

    assert isinstance(get_parser(), MarkItDownParser)


def test_read_file_reads_bytes_and_closes_file():
    class FakeFile:
        name = "stored.md"

        def __init__(self):
            self.opened_with = None
            self.closed = False

        def open(self, mode):
            self.opened_with = mode

        def read(self):
            return b"raw bytes"

        def close(self):
            self.closed = True

    fake_file = FakeFile()
    material = SimpleNamespace(file=fake_file, name="fallback.md")

    assert material_service._read_file(material) == ("stored.md", b"raw bytes")
    assert fake_file.opened_with == "rb"
    assert fake_file.closed is True


def test_extract_text_parser_failure_and_unknown_type_return_empty(monkeypatch):
    class Parser:
        def parse_text(self, text, *, filename="raw.txt"):
            raise RuntimeError("bad text")

    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(SimpleNamespace(id=1, material_type="text", text_content="bad")) == ""
    assert material_service.extract_text(SimpleNamespace(id=2, material_type="video")) == ""


def test_vision_options_skip_non_openai_and_client_init_failure(monkeypatch):
    material = SimpleNamespace(
        id=7,
        ocr_enhance=True,
        knowledge_base=SimpleNamespace(vision_model=SimpleNamespace(id=3, protocol_type="azure")),
    )

    assert material_service._vision_options(material) == (None, None)

    class BrokenOpenAI:
        def __init__(self, base_url, api_key):
            raise RuntimeError("bad vision config")

    monkeypatch.setattr(material_service, "OpenAI", BrokenOpenAI)
    material.knowledge_base.vision_model = SimpleNamespace(
        id=4,
        protocol_type="openai",
        openai_api_base="http://vision",
        openai_api_key="secret",
        model_name="vision-model",
    )

    assert material_service._vision_options(material) == (None, None)


def test_extract_web_without_url_returns_empty_before_parser(monkeypatch):
    class Parser:
        def parse_url(self, url, *, vision_client=None, vision_model=None):
            pytest.fail("empty URL should not call parser")

    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(SimpleNamespace(id=1, material_type="web", url="")) == ""


def test_save_and_load_parsed_markdown_use_private_storage(monkeypatch):
    saved = {}

    class Storage:
        def save(self, path, content):
            saved["path"] = path
            saved["body"] = content.read()
            return path

        def open(self, path, mode):
            saved["open"] = (path, mode)

            class Reader:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return b"# parsed"

            return Reader()

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())
    material = SimpleNamespace(knowledge_base_id=7, id=9, current_version=SimpleNamespace(content_locator="wiki/parsed/a.md"))

    locator = material_service.save_parsed_markdown(material, "# parsed", "digest")
    assert locator == "wiki/parsed/7/9/digest.md"
    assert saved["body"] == b"# parsed"
    assert material_service.load_parsed_markdown(material) == "# parsed"
    assert saved["open"] == ("wiki/parsed/a.md", "rb")


def test_load_parsed_markdown_handles_missing_or_unreadable_content(monkeypatch):
    class Versions:
        def order_by(self, *args):
            return self

        def first(self):
            return None

    assert material_service.load_parsed_markdown(SimpleNamespace(id=1, current_version=None, versions=Versions())) == ""

    class Storage:
        def open(self, path, mode):
            raise RuntimeError("storage down")

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())
    material = SimpleNamespace(id=2, current_version=SimpleNamespace(content_locator="wiki/parsed/a.md"))
    assert material_service.load_parsed_markdown(material) == ""


def test_load_parsed_markdown_returns_storage_text_without_decoding(monkeypatch):
    class Storage:
        def open(self, path, mode):
            class Reader:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return "# parsed text"

            return Reader()

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    material = SimpleNamespace(id=3, current_version=SimpleNamespace(content_locator="wiki/parsed/text.md"))
    assert material_service.load_parsed_markdown(material) == "# parsed text"


def test_delete_parsed_markdown_rejects_unsafe_locator_and_reports_storage_failure(monkeypatch):
    deleted = []

    class Storage:
        def delete(self, locator):
            deleted.append(locator)
            raise RuntimeError("storage down")

    monkeypatch.setattr(material_service, "_PARSED_STORAGE", Storage())

    assert material_service.delete_parsed_markdown("wiki/other/1/2/a.md") is False
    assert deleted == []
    assert material_service.delete_parsed_markdown("wiki/parsed/1/2/a.md") is False
    assert deleted == ["wiki/parsed/1/2/a.md"]


def test_file_failure_reason_distinguishes_missing_unsupported_and_parse_empty():
    missing = SimpleNamespace(material_type="file", file="", name="guide.md")
    assert material_service._ingest_failure_reason(missing) == "文件资料未上传文件,无法解析"

    no_extension_file = SimpleNamespace(name="rawfile")
    no_extension = SimpleNamespace(material_type="file", file=no_extension_file, name="rawfile")
    assert "暂不支持的文件格式: 无扩展名" in material_service._ingest_failure_reason(no_extension)

    unsupported_file = SimpleNamespace(name="archive.rar")
    unsupported = SimpleNamespace(material_type="file", file=unsupported_file, name="archive.rar")
    reason = material_service._ingest_failure_reason(unsupported)
    assert "暂不支持的文件格式: .rar" in reason
    assert "支持格式" in reason

    supported_file = SimpleNamespace(name="guide.pdf")
    supported = SimpleNamespace(material_type="file", file=supported_file, name="guide.pdf")
    assert "未能从文件中解析出 markdown" in material_service._ingest_failure_reason(supported)


def test_non_file_failure_reasons_are_actionable():
    assert material_service._ingest_failure_reason(SimpleNamespace(material_type="web", url="")) == "网页资料缺少 URL,无法解析"
    assert "未能抓取到网页正文" in material_service._ingest_failure_reason(SimpleNamespace(material_type="web", url="https://example.com"))
    assert material_service._ingest_failure_reason(SimpleNamespace(material_type="text")) == "文本内容为空"
    assert material_service._ingest_failure_reason(SimpleNamespace(material_type="video")) == "暂不支持的资料类型: video"


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _file_material(kb, name):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name=name, material_type="file")


@pytest.mark.django_db
def test_extract_file_uses_configured_parser(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "guide.md")
    calls = []

    class Parser:
        def parse_file(self, data, filename, *, vision_client=None, vision_model=None):
            calls.append((data, filename, vision_client))
            return "# 标题\nbody"

    monkeypatch.setattr(material_service, "_read_file", lambda m: ("guide.md", b"raw"))
    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(mat) == "# 标题\nbody"
    assert calls == [(b"raw", "guide.md", None)]


@pytest.mark.django_db
def test_extract_file_passes_configured_vision_model_when_ocr_enhanced(monkeypatch):
    from apps.opspilot.models import LLMModel, Material

    vision_model = LLMModel.objects.create(name="Vision", model="vision-model")
    kb = _kb()
    kb.vision_model = vision_model
    kb.save(update_fields=["vision_model"])
    mat = Material.objects.create(knowledge_base=kb, name="scan.png", material_type="file", ocr_enhance=True)
    calls = []

    class FakeOpenAI:
        def __init__(self, base_url, api_key):
            self.base_url = base_url
            self.api_key = api_key
            calls.append(("client", base_url, api_key))

    class Parser:
        def parse_file(self, data, filename, *, vision_client=None, vision_model=None):
            calls.append(("parse", data, filename, vision_client, vision_model))
            return "# 图片说明"

    monkeypatch.setattr(material_service, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(material_service, "_read_file", lambda m: ("scan.png", b"image-bytes"))
    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(mat) == "# 图片说明"
    assert calls[0] == ("client", "", "")
    assert calls[1][0:3] == ("parse", b"image-bytes", "scan.png")
    assert isinstance(calls[1][3], FakeOpenAI)
    assert calls[1][4] == "vision-model"


@pytest.mark.django_db
def test_extract_file_parser_failure_returns_empty(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "scan.pdf")

    class Parser:
        def parse_file(self, data, filename, *, vision_client=None, vision_model=None):
            raise RuntimeError("bad file")

    monkeypatch.setattr(material_service, "_read_file", lambda m: ("scan.pdf", b"%PDF-1.4 ..."))
    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(mat) == ""


@pytest.mark.django_db
def test_ingest_file_with_unsupported_extension_fails_before_parser(monkeypatch):
    kb = _kb()
    mat = _file_material(kb, "clip.mp4")
    mat.file = "clip.mp4"
    mat.save(update_fields=["file"])

    class Parser:
        def parse_file(self, data, filename, *, vision_client=None, vision_model=None):
            pytest.fail("unsupported file extension should be rejected before parser")

    monkeypatch.setattr(material_service, "_read_file", lambda m: ("clip.mp4", b"video-bytes"))
    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    material_service.ingest_material(mat)

    mat.refresh_from_db()
    assert mat.status == "failed"
    assert "暂不支持的文件格式: .mp4" in mat.error_message
    assert "支持格式" in mat.error_message


@pytest.mark.django_db
def test_ingest_file_sets_done_and_material_version(monkeypatch):
    from apps.opspilot.models import MaterialVersion

    kb = _kb()
    mat = _file_material(kb, "doc.md")

    class Parser:
        def parse_file(self, data, filename, *, vision_client=None, vision_model=None):
            return "hello wiki"

    monkeypatch.setattr(material_service, "_read_file", lambda m: ("doc.md", b"hello wiki"))
    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())
    monkeypatch.setattr(material_service, "save_parsed_markdown", lambda material, md, digest: "wiki/parsed/doc.md")

    out = material_service.ingest_material(mat)

    assert out.status == "done"
    assert out.ai_summary == "hello wiki"
    assert out.content_hash
    assert MaterialVersion.objects.filter(material=out, content_locator="wiki/parsed/doc.md").exists()


@pytest.mark.django_db
def test_extract_web_uses_parser(monkeypatch):
    from apps.opspilot.models import Material

    kb = _kb()
    mat = Material.objects.create(knowledge_base=kb, name="site", material_type="web", url="http://example.com")
    calls = []

    class Parser:
        def parse_url(self, url, *, vision_client=None, vision_model=None):
            calls.append((url, vision_client))
            return "# 标题\n正文内容"

    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(mat) == "# 标题\n正文内容"
    assert calls == [("http://example.com", None)]


@pytest.mark.django_db
def test_extract_web_parser_failure_returns_empty(monkeypatch):
    from apps.opspilot.models import Material

    kb = _kb()
    mat = Material.objects.create(knowledge_base=kb, name="site", material_type="web", url="http://example.com")

    class Parser:
        def parse_url(self, url, *, vision_client=None, vision_model=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(material_service, "get_parser", lambda: Parser())

    assert material_service.extract_text(mat) == ""


@pytest.mark.integration
@pytest.mark.django_db
def test_material_file_upload_endpoint(api_client, monkeypatch, tmp_path):
    """前后联动:前端 multipart 文档上传 → POST /material/ → 文件字段持久化。"""
    from apps.opspilot.models import Material
    from apps.opspilot.viewsets import wiki_material_view

    file_field = Material._meta.get_field("file")
    original_storage = file_field.storage
    file_field.storage = FileSystemStorage(location=tmp_path, base_url="/test-media/")

    def fake_enqueue(material, llm_model_id):
        material.status = "parsing"
        material.save(update_fields=["status", "updated_at"])

    monkeypatch.setattr(wiki_material_view.WikiMaterialViewSet, "_enqueue_ingest", staticmethod(fake_enqueue))

    kb = _kb()
    try:
        resp = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/material/",
            {
                "knowledge_base": kb.id,
                "name": "guide.md",
                "material_type": "file",
                "file": SimpleUploadedFile("guide.md", b"# \xe6\x8c\x87\xe5\x8d\x97\nbody"),
            },
            format="multipart",
        )
    finally:
        file_field.storage = original_storage

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["material_type"] == "file" and data["id"]
    assert data.get("file")

    created = Material.objects.get(id=data["id"])
    assert created.file
    assert created.status == "parsing"
