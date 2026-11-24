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


def _pptx_slide_text(slide) -> str:
    return "\n".join(shape.text_frame.text for shape in slide.shapes if shape.has_text_frame)


def test_build_attachment_bytes_pptx_is_a_slide_deck():
    from io import BytesIO

    from pptx import Presentation
    from pptx.util import Inches

    payload = build_attachment_bytes("# 广州旅游\n\n- 珠江\n- 早茶\n", "pptx", title="广州旅游")
    assert payload[:2] == b"PK"
    deck = Presentation(BytesIO(payload))
    assert len(deck.slides) == 1
    assert deck.slide_width == Inches(13.333)
    text = _pptx_slide_text(deck.slides[0])
    assert "广州旅游" in text
    assert "珠江" in text
    assert "•" not in text
    runs = [run for shape in deck.slides[0].shapes if shape.has_text_frame for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
    assert runs[0].font.name == "微软雅黑"


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
    texts = [_pptx_slide_text(slide) for slide in deck.slides]
    assert len(deck.slides) >= 2
    assert "第一页" in texts[0]
    assert "第二页" in texts[1]
    assert "2 / 2" in texts[1]


def test_build_attachment_bytes_pptx_uses_cover_callout_and_point_pages():
    from io import BytesIO

    from pptx import Presentation

    content = "# 巡检\n\n本周范围\n\n# 核心结论\n\n- 磁盘满\n- 需扩容\n\n# 明细\n\n- 一\n- 二\n- 三\n- 四\n- 五\n"
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="巡检")))
    texts = [_pptx_slide_text(slide) for slide in deck.slides]
    assert "巡检" in texts[0]
    assert "•" not in texts[0]
    assert any("核心结论" in text and "磁盘满" in text and "•" not in text for text in texts)
    assert any("明细" in text and "• 五" in text for text in texts)
    assert sum("明细" in text for text in texts) == 2


def test_build_attachment_bytes_pptx_renders_markdown_tables():
    from io import BytesIO

    from pptx import Presentation

    content = "# 告警明细\n\n| 编号 | 标题 | 状态 |\n| --- | --- | --- |\n| SEED-AC-02 | CPU 使用率过高 | processing |\n| SEED-AC-01 | 磁盘使用率过高 | pending |\n"
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="告警明细")))
    tables = [shape.table for slide in deck.slides for shape in slide.shapes if shape.has_table]
    assert len(tables) == 1
    assert tables[0].cell(0, 0).text == "编号"
    assert tables[0].cell(1, 0).text == "SEED-AC-02"
    assert tables[0].cell(2, 1).text == "磁盘使用率过高"
    assert "编号：标题" not in _pptx_slide_text(deck.slides[-1])

    pipes = "# 告警明细\n\n| SEED-AC-02 | CPU 使用率过高 | processing | admin |\n| SEED-AC-01 | 磁盘使用率过高 | pending | admin |\n"
    piped = Presentation(BytesIO(build_attachment_bytes(pipes, "pptx", title="告警明细")))
    piped_tables = [shape.table for slide in piped.slides for shape in slide.shapes if shape.has_table]
    assert len(piped_tables) == 1
    assert piped_tables[0].cell(0, 0).text == "SEED-AC-02"
    assert piped_tables[0].cell(1, 3).text == "admin"
    assert "•" not in piped_tables[0].cell(0, 0).text


def test_build_attachment_bytes_pptx_renders_metric_cards_not_markdown():
    from io import BytesIO

    from pptx import Presentation

    content = """# 活动告警汇总

告警中心现状、处置缺口与改进建议

## 现状

7 条告警中，3 条仍未闭环

- **3** 条活动告警，占全部 7 条的 42.9%
- **7** 告警总数，当前授权组织下的全部记录
- **4** 已闭环告警，人工关闭与自动恢复都有
"""
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="活动告警汇总")))
    texts = [_pptx_slide_text(slide) for slide in deck.slides]
    blob = "\n".join(texts)
    assert "**" not in blob
    assert "#" not in blob
    assert "|" not in blob
    assert any("活动告警汇总" in text and "处置缺口" in text and "•" not in text for text in texts)
    metric = next(text for text in texts if "42.9%" in text)
    assert "•" not in metric
    assert "3 条" in metric
    assert "告警总数" in metric
    assert "7 条告警中，3 条仍未闭环" in metric


def test_build_attachment_bytes_pptx_puts_h3_and_actions_side_by_side():
    from io import BytesIO

    from pptx import Presentation

    content = """# 汇总

## 环节

三个环节各卡一条

### 待响应
SEED-AC-01 无人开始处置

### 处理中
SEED-AC-02 未推进到闭环

### 未分派
SEED-AC-03 尚未进入流程

## 动作

1. **逐条核实**：已恢复的直接关闭
2. **认领未分派**：先指定责任人
"""
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="汇总")))
    texts = [_pptx_slide_text(slide) for slide in deck.slides]
    blob = "\n".join(texts)
    assert "**" not in blob
    status = next(text for text in texts if "待响应" in text and "未分派" in text)
    assert "•" not in status
    assert "01" in status
    assert "SEED-AC-03" in status
    action = next(text for text in texts if "逐条核实" in text)
    assert "已恢复的直接关闭" in action
    assert "02" in action
    assert "•" not in action
    body = next(
        paragraph
        for slide in deck.slides
        for shape in slide.shapes
        if shape.has_text_frame
        for paragraph in shape.text_frame.paragraphs
        if "无人开始处置" in paragraph.text
    )
    assert body.line_spacing == 1.45
    assert body.space_before.pt == 6


def test_build_attachment_bytes_pptx_splits_packed_action_labels():
    from io import BytesIO

    from pptx import Presentation

    content = """# 汇总

## 后续建议

- **优先指派**：将未分派的 SEED-AC-03 明确处理人，避免遗漏 **关注重复**：noperm-host-10.10.70.21 同时存在磁盘过高与磁盘使用率过高两条告警 **推进处理**：2 条 pending 告警需尽快响应，2 条 processing 告警需跟进闭环
"""
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="汇总")))
    text = _pptx_slide_text(deck.slides[-1])
    assert "后续建议" in text
    assert "•" not in text
    assert "01" in text and "优先指派" in text
    assert "02" in text and "关注重复" in text
    assert "03" in text and "推进处理" in text


def test_build_attachment_bytes_pptx_lays_out_briefing_bullets():
    from io import BytesIO

    from pptx import Presentation

    content = """# 活动告警统计汇总

统计范围：当前全部未关闭活动告警工单 告警总数：5 条 涉及资源：4 个 数据来源：统一告警中心工单 报告版本：v1.0

## 统计概览

- 告警总数 5 条，全部为未关闭的活动告警
- 处理中 2 条，待响应 2 条，未分派 1 条
- 等级均为 0，来源均为「本地验收」
- 资源类型均为主机（host），涉及 4 个不同资源

## 按状态分布

- 处理中：2 条（SEED-OG-02、SEED-AC-02）
- 待响应：2 条（SEED-OG-01、SEED-AC-01）
- 未分派：1 条（SEED-AC-03）

## 告警明细

- SEED-OG-02：Guest组CPU过高，资源 noperm-opaque-01，处理中，处理人 admin
- SEED-AC-01：磁盘使用率过高，资源 noperm-host-10.10.70.21，待响应，处理人 admin

## 核心结论

- SEED-AC-03 内存不足告警处于未分派状态，建议尽快指派处理人
- noperm-host 出现 2 条磁盘类告警，建议优先核查磁盘容量
"""
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="活动告警统计汇总")))
    texts = [_pptx_slide_text(slide) for slide in deck.slides]
    blob = "\n".join(texts)
    cover = texts[0].replace("\n", "")
    assert "•" not in texts[0]
    assert "统计范围：当前全部未关闭活动告警工单" in cover
    assert "告警总数：5" not in cover
    assert "5 条" in cover
    assert "报告版本：v1.0" in cover
    overview = next(text for text in texts if "统计概览" in text)
    assert "•" not in overview
    assert "处理中" in overview and "待响应" in overview
    detail = next(slide for slide in deck.slides if any(shape.has_table for shape in slide.shapes))
    table = next(shape.table for shape in detail.shapes if shape.has_table)
    assert table.cell(0, 0).text == "编号"
    assert table.cell(1, 0).text == "SEED-OG-02"
    assert "处理人" in table.cell(0, 1).text or any(cell.text == "处理人" for cell in table.rows[0].cells)
    conclusion = next(text for text in texts if "核心结论" in text)
    assert "•" not in conclusion
    assert "指派处理人" in conclusion
    assert "SEED-OG-02：" not in blob


def test_build_attachment_bytes_pptx_keeps_table_intro_on_the_table_slide():
    from io import BytesIO

    from pptx import Presentation

    content = "# 汇总\n\n副标题\n\n## 活动告警\n\n三条活动告警：磁盘、CPU、内存各一条\n\n| 告警 ID | 告警内容 | 状态 |\n| --- | --- | --- |\n| SEED-AC-01 | 磁盘使用率过高 | 待响应 |\n"
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="汇总")))
    assert len(deck.slides) == 2
    text = _pptx_slide_text(deck.slides[1])
    assert "三条活动告警" in text
    assert "•" not in text
    tables = [shape.table for shape in deck.slides[1].shapes if shape.has_table]
    assert tables[0].cell(1, 0).text == "SEED-AC-01"


def test_build_attachment_bytes_pptx_unescapes_literal_newlines():
    from io import BytesIO

    from pptx import Presentation

    content = "# 第一页\\n\\n要点\\n\\n# 第二页\\n\\n收尾"
    deck = Presentation(BytesIO(build_attachment_bytes(content, "pptx", title="第一页")))
    texts = [_pptx_slide_text(slide) for slide in deck.slides]
    blob = "\n".join(texts)
    assert len(deck.slides) >= 2
    assert "第一页" in texts[0]
    assert "第二页" in texts[1]
    assert "# " not in blob
    assert "\\n" not in blob


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
