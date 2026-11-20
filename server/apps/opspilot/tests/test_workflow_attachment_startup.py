"""migrate / Django setup 不得加载 python-docx、reportlab；附件生成仍可用。"""

import ast
from pathlib import Path

import pytest
from urllib3.exceptions import MaxRetryError, NewConnectionError

from apps.opspilot.models import WorkflowAttachmentAsset
from apps.opspilot.services.attachment_theme import inline_text
from apps.opspilot.services.workflow_attachment_service import (
    MINIO_CONNECTION_FAILURE_MESSAGE,
    _is_minio_connection_error,
    _iter_markdown_blocks,
    _minio_http_pool,
    build_attachment_bytes,
    create_workflow_attachment_asset,
    normalize_attachment_file_type,
)

pytestmark = pytest.mark.unit

_OPSPILOT_ROOT = Path(__file__).resolve().parents[1]


def _top_level_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_nats_api_does_not_import_chat_flow_factory_at_module_level():
    names = _top_level_imported_modules(_OPSPILOT_ROOT / "nats_api.py")
    assert "apps.opspilot.utils.chat_flow_utils.engine.factory" not in names


def test_workflow_attachment_service_defers_docx_and_reportlab():
    names = _top_level_imported_modules(_OPSPILOT_ROOT / "services" / "workflow_attachment_service.py")
    theme_names = _top_level_imported_modules(_OPSPILOT_ROOT / "services" / "attachment_theme.py")
    assert "docx" not in names
    assert "openpyxl" not in names
    assert "pptx" not in names
    assert "docx" not in theme_names
    assert "openpyxl" not in theme_names
    assert "playwright" not in theme_names
    assert not any(name == "reportlab" or name.startswith("reportlab.") for name in names | theme_names)


def test_build_attachment_bytes_md_keeps_utf8():
    assert build_attachment_bytes("# 报告", "md", title="日报") == "# 报告".encode("utf-8")


def test_build_attachment_bytes_txt_keeps_plain_text():
    payload = build_attachment_bytes("广州介绍", "txt")
    assert payload == "广州介绍".encode("utf-8")
    _, filename, mime_type = normalize_attachment_file_type("txt", "广州介绍.txt")
    assert filename == "广州介绍.txt"
    assert mime_type == "text/plain"


def test_build_attachment_bytes_docx_renders_markdown_heading_and_table():
    from io import BytesIO

    from docx import Document

    payload = build_attachment_bytes(
        "# 主机磁盘资源爆满风险评估报告\n\n## 报告信息\n\n| 项目 | 内容 |\n| --- | --- |\n| 报告日期 | 2026-10-12 |\n",
        "docx",
        title="主机磁盘资源爆满风险评估报告",
    )
    document = Document(BytesIO(payload))
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert "主机磁盘资源爆满风险评估报告" in texts
    assert not any(text.startswith("#") for text in texts)
    assert not any("|" in text for text in texts)
    assert document.tables[0].rows[1].cells[0].text == "报告日期"
    assert document.tables[0].rows[1].cells[1].text == "2026-10-12"
    assert document.paragraphs[0].runs[0].font.name == "微软雅黑"


def test_build_attachment_bytes_pptx_is_a_slide_deck():
    from io import BytesIO

    from pptx import Presentation

    payload = build_attachment_bytes("# 广州旅游\n\n- 珠江\n- 早茶\n", "pptx", title="广州旅游")
    assert payload[:2] == b"PK"
    deck = Presentation(BytesIO(payload))
    assert len(deck.slides) == 1
    assert deck.slides[0].shapes.title.text == "广州旅游"
    assert "珠江" in deck.slides[0].placeholders[1].text_frame.text
    assert deck.slides[0].placeholders[1].text_frame.paragraphs[0].runs[0].font.name == "微软雅黑"


def test_build_attachment_bytes_docx_is_office_zip():
    payload = build_attachment_bytes("第一行\n第二行", "docx", title="巡检")
    assert payload[:2] == b"PK"
    assert len(payload) > 1000


def test_build_attachment_bytes_pdf_has_header(monkeypatch):
    seen = {}

    def fake_print(html, title):
        seen["html"] = html
        seen["title"] = title
        return b"%PDF-1.4 themed"

    monkeypatch.setattr("apps.opspilot.services.attachment_theme.print_html_to_pdf", fake_print)
    payload = build_attachment_bytes("hello <tag> & value", "pdf", title="Inspection")
    assert payload.startswith(b"%PDF")
    assert seen["title"] == "Inspection"
    assert "hello &lt;tag&gt; &amp; value" in seen["html"]
    assert "#F5F7FA" in seen["html"]
    assert 'class="cover"' in seen["html"]
    assert "运维分析报告" in seen["html"]
    assert 'class="subtitle"' in seen["html"]
    assert ">目录<" in seen["html"]
    assert "margin: 10pt 0" in seen["html"]


def test_build_attachment_bytes_csv_has_utf8_bom():
    payload = build_attachment_bytes("name,count\nweb,2", "csv")
    assert payload.startswith(b"\xef\xbb\xbf")
    assert payload.decode("utf-8-sig") == "name,count\nweb,2"


@pytest.mark.django_db
def test_refresh_attachment_download_urls_resigns_expired_history_link(monkeypatch):
    import json

    from django.core.files.base import ContentFile
    from django.core.signing import SignatureExpired

    from apps.opspilot.models import WorkflowAttachmentAsset
    from apps.opspilot.services import workflow_attachment_service as attachment_service

    asset = WorkflowAttachmentAsset.objects.create(
        execution_id="exec-history",
        attachment_id="att-history",
        filename="子网地址使用率.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file=ContentFile(b"xlsx", name="subnet.xlsx"),
    )
    stale = attachment_service.build_signed_attachment_download_url(asset)
    token = stale.rsplit("/download/", 1)[1].rstrip("/")
    stored = json.dumps(
        [{"type": "TOOL_CALL_RESULT", "content": json.dumps({"file_url": stale, "filename": asset.filename})}],
        ensure_ascii=False,
    )
    monkeypatch.setattr(attachment_service, "workflow_attachment_download_max_age", lambda: -1)
    with pytest.raises(SignatureExpired):
        attachment_service.resolve_signed_attachment_token(token)

    refreshed = attachment_service.refresh_attachment_download_urls(stored)
    fresh_token = refreshed.split("/download/", 1)[1].split("/", 1)[0]
    monkeypatch.setattr(attachment_service, "workflow_attachment_download_max_age", lambda: 24 * 60 * 60)
    resolved = attachment_service.resolve_signed_attachment_token(fresh_token)
    assert resolved is not None
    assert resolved.id == asset.id


def _plain_block(block):
    kind = block[0]
    if kind == "paragraph":
        return ("paragraph", inline_text(block[1]))
    if kind in {"ul", "ol"}:
        return (kind, [inline_text(item) for item in block[1]])
    if kind == "hr":
        return ("hr",)
    return block


def test_markdown_paragraph_stops_before_list_or_rule_without_blank_line():
    blocks = [_plain_block(block) for block in _iter_markdown_blocks("介绍\n- 项\n1. 序号\n---\n结尾")]
    assert blocks == [
        ("paragraph", "介绍"),
        ("ul", ["项"]),
        ("ol", ["序号"]),
        ("hr",),
        ("paragraph", "结尾"),
    ]
    assert _plain_block(next(_iter_markdown_blocks("介绍\n继续"))) == ("paragraph", "介绍 继续")


def test_build_attachment_bytes_pptx_splits_each_h1_into_a_slide():
    from io import BytesIO

    from pptx import Presentation

    payload = build_attachment_bytes("# 第一页\n\n要点\n\n# 第二页\n\n收尾", "pptx", title="第一页")
    deck = Presentation(BytesIO(payload))
    titles = [slide.shapes.title.text for slide in deck.slides]
    assert len(deck.slides) >= 2
    assert titles == ["第一页", "第二页"]


def test_normalize_attachment_file_type_rewrites_alias_extension():
    normalized_type, filename, mime_type = normalize_attachment_file_type("ppt", "deck.ppt")
    assert normalized_type == "ppt"
    assert filename == "deck.pptx"
    assert mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    _, text_name, text_mime = normalize_attachment_file_type("text", "notes.text")
    assert text_name == "notes.txt"
    assert text_mime == "text/plain"

    _, word_name, word_mime = normalize_attachment_file_type("word", "memo.doc")
    assert word_name == "memo.docx"
    assert word_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    _, kept_name, _ = normalize_attachment_file_type("pptx", "deck.pptx")
    assert kept_name == "deck.pptx"


def test_build_attachment_bytes_pdf_renders_chinese_markdown_table(monkeypatch):
    seen = {}

    def fake_print(html, title):
        seen["html"] = html
        return b"%PDF-1.4 themed"

    monkeypatch.setattr("apps.opspilot.services.attachment_theme.print_html_to_pdf", fake_print)
    content = "| 项目 | 内容 |\n| --- | --- |\n| 城市 | 广州 |\n| 备注 | A & B <C> |\n"
    first = build_attachment_bytes(content, "pdf", title="广州报告")
    second = build_attachment_bytes(content, "pdf", title="广州报告")
    assert first == second == b"%PDF-1.4 themed"
    assert "广州" in seen["html"]
    assert "城市" in seen["html"]
    assert "项目" in seen["html"]
    assert "A &amp; B &lt;C&gt;" in seen["html"]
    assert "<th>" in seen["html"]


def test_build_attachment_bytes_xlsx_keeps_header_row():
    from io import BytesIO

    from openpyxl import load_workbook

    payload = build_attachment_bytes("name,count\nweb,2", "xlsx")
    sheet = load_workbook(BytesIO(payload)).active
    assert [cell.value for cell in next(sheet.iter_rows(max_row=1))] == ["name", "count"]
    assert [cell.value for cell in next(sheet.iter_rows(min_row=2, max_row=2))] == ["web", 2]


def test_minio_connection_failure_fails_once_with_user_message(monkeypatch):
    from django_minio_backend.models import MinioBackend

    from apps.opspilot.models.bot_mgmt import RasaModel

    reason = NewConnectionError(
        None,
        "Failed to establish a new connection: [WinError 10061] 由于目标计算机积极拒绝，无法连接。",
    )
    error = MaxRetryError(None, "http://localhost:9000/munchkin-private", reason)
    assert _is_minio_connection_error(error) is True
    assert _is_minio_connection_error(RuntimeError("db down")) is False

    pool = _minio_http_pool()
    assert pool.connection_pool_kw["retries"].total is False
    with pytest.raises(ConnectionRefusedError):
        pool.connection_pool_kw["retries"].increment(
            method="HEAD",
            url="/munchkin-private",
            error=ConnectionRefusedError(10061, "refused"),
        )

    attachment_storage = WorkflowAttachmentAsset._meta.get_field("file").storage
    other_storage = RasaModel._meta.get_field("model_file").storage
    shared_http = object()
    attachment_http = object()
    other_http = object()
    class_client = type("CachedMinio", (), {"_http": shared_http})()
    attachment_client = type("CachedMinio", (), {"_http": attachment_http})()
    attachment_ext = type("CachedMinio", (), {"_http": object()})()
    other_client = type("CachedMinio", (), {"_http": other_http})()
    previous_class_client = getattr(MinioBackend, "_MinioBackend__CLIENT", None)
    had_class_client = hasattr(MinioBackend, "_MinioBackend__CLIENT")
    previous_attachment = (
        getattr(attachment_storage, "HTTP_CLIENT", None),
        getattr(attachment_storage, "_MinioBackend__CLIENT", None),
        getattr(attachment_storage, "_MinioBackend__CLIENT_EXT", None),
    )
    previous_other = (
        getattr(other_storage, "HTTP_CLIENT", None),
        getattr(other_storage, "_MinioBackend__CLIENT", None),
    )
    MinioBackend._MinioBackend__CLIENT = class_client
    attachment_storage._MinioBackend__CLIENT = attachment_client
    attachment_storage._MinioBackend__CLIENT_EXT = attachment_ext
    other_storage._MinioBackend__CLIENT = other_client
    seen = {}

    def _save(self, name, content, max_length=None):
        seen["storage"] = self
        seen["http"] = self.HTTP_CLIENT
        seen["cached_client"] = getattr(self, "_MinioBackend__CLIENT", None)
        raise error

    monkeypatch.setattr(MinioBackend, "save", _save)
    monkeypatch.setattr(WorkflowAttachmentAsset.objects, "filter", lambda *args, **kwargs: type("Query", (), {"first": lambda self: None})())
    try:
        with pytest.raises(ValueError, match="连不上 MinIO") as caught:
            create_workflow_attachment_asset(
                execution_id="exec-minio-down",
                attachment_id="file-1",
                filename="告警.docx",
                content_bytes=b"doc",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        message = str(caught.value)
        assert message == MINIO_CONNECTION_FAILURE_MESSAGE
        assert caught.value.__cause__ is error
        assert "localhost" not in message
        assert "9000" not in message
        assert "WinError" not in message
        assert "HTTPConnectionPool" not in message
        assert seen["storage"] is not attachment_storage
        assert seen["storage"] is not other_storage
        assert seen["http"] is pool
        assert seen["cached_client"] is not class_client
        assert seen["cached_client"] is not attachment_client
        assert class_client._http is shared_http
        assert attachment_client._http is attachment_http
        assert attachment_ext._http is not pool
        assert other_client._http is other_http
        assert attachment_storage.HTTP_CLIENT is previous_attachment[0]
        assert attachment_storage.HTTP_CLIENT is not pool
        assert other_storage.HTTP_CLIENT is previous_other[0]
        assert other_storage.HTTP_CLIENT is not pool
    finally:
        attachment_storage.HTTP_CLIENT = previous_attachment[0]
        attachment_storage._MinioBackend__CLIENT = previous_attachment[1]
        attachment_storage._MinioBackend__CLIENT_EXT = previous_attachment[2]
        other_storage.HTTP_CLIENT = previous_other[0]
        other_storage._MinioBackend__CLIENT = previous_other[1]
        if had_class_client:
            MinioBackend._MinioBackend__CLIENT = previous_class_client
        elif hasattr(MinioBackend, "_MinioBackend__CLIENT"):
            delattr(MinioBackend, "_MinioBackend__CLIENT")


def test_minio_connection_failure_does_not_hide_other_save_errors(monkeypatch):
    from django_minio_backend.models import MinioBackend

    monkeypatch.setattr(WorkflowAttachmentAsset.objects, "filter", lambda *args, **kwargs: type("Query", (), {"first": lambda self: None})())

    def _reject(self, name, content, max_length=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(MinioBackend, "save", _reject)
    with pytest.raises(RuntimeError, match="db down"):
        create_workflow_attachment_asset(
            execution_id="exec-minio-down",
            attachment_id="file-1",
            filename="告警.docx",
            content_bytes=b"doc",
            mime_type="application/octet-stream",
        )


def test_pdf_print_timeout_becomes_user_visible_failure(monkeypatch, caplog):
    from apps.opspilot.services.attachment_theme import _PDF_PRINT_TIMEOUT_SECONDS

    sentinel = "PDF_TIMEOUT_SENTINEL"

    class FakeFuture:
        def result(self, timeout=None):
            assert timeout == _PDF_PRINT_TIMEOUT_SECONDS
            raise TimeoutError()

    class FakePool:
        def submit(self, fn):
            return FakeFuture()

        def shutdown(self, wait=True, cancel_futures=False):
            assert wait is False

    monkeypatch.setattr("apps.opspilot.services.attachment_theme.ThreadPoolExecutor", lambda *args, **kwargs: FakePool())
    with pytest.raises(ValueError, match="PDF 生成失败"):
        build_attachment_bytes(f"# 集群健康报告\n节点 {sentinel}", "pdf", title="集群健康报告")
    record = next(record for record in caplog.records if record.msg == "attachment pdf print failed error_type=%s")
    assert record.args == ("TimeoutError",)
    assert sentinel not in record.getMessage()
    assert sentinel not in caplog.text


def test_pdf_print_failure_logs_error_type_without_document(monkeypatch, caplog):
    sentinel = "PDF_PRIVATE_SENTINEL"

    def explode(html, title):
        raise OSError("chromium missing")

    monkeypatch.setattr("apps.opspilot.services.attachment_theme._launch_chromium_pdf", explode)
    with pytest.raises(ValueError, match="PDF 生成失败"):
        build_attachment_bytes(f"# 集群健康报告\n节点 {sentinel}", "pdf", title="集群健康报告")
    record = next(record for record in caplog.records if record.msg == "attachment pdf print failed error_type=%s")
    assert record.args == ("OSError",)
    assert record.exc_info is not None
    assert "集群健康报告" not in record.getMessage()
    assert sentinel not in record.getMessage()
