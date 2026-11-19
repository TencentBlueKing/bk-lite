"""附件主题：Word 样式、PDF 用的 HTML、Excel 表头和合并。"""

from io import BytesIO

import pytest
from docx import Document
from docx.oxml.ns import qn
from openpyxl import load_workbook

from apps.opspilot.services.attachment_theme import _TABLE_GAP_PT, inline_text, iter_markdown_blocks, render_document_html
from apps.opspilot.services.workflow_attachment_service import build_attachment_bytes

pytestmark = pytest.mark.unit


def test_markdown_keeps_emphasis_and_flattens_quotes_images_and_nested_lists():
    blocks = list(iter_markdown_blocks("见图 ![架构](https://example.test/a.png)\n\n> 引用 **重点**\n\n- 父\n  - 子\n\n`命令`"))
    assert inline_text(blocks[0][1]) == "见图 架构"
    assert "https://example.test" not in inline_text(blocks[0][1])
    assert inline_text(blocks[1][1]) == "引用 重点"
    assert blocks[1][1][1].bold is True
    assert [inline_text(item) for item in blocks[2][1]] == ["父", "子"]
    assert blocks[3][1][0].code is True
    assert blocks[3][1][0].text == "命令"


def test_docx_uses_theme_styles_for_heading_table_link_and_official_indent():
    payload = build_attachment_bytes(
        "# 巡检函\n\n## 检查范围\n\n正文见 [门户](https://example.test/report)。\n\n| 项目 | 很长的说明文字 |\n| --- | --- |\n| 日期 | 2026-10-12 |\n",
        "docx",
        title="巡检函",
        genre="official",
    )
    document = Document(BytesIO(payload))
    body = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "巡检函" in body
    assert "正文见 门户" in body.replace("\n", "")
    assert document.sections[-1].header.paragraphs[0].text == "巡检函"
    assert "PAGE" in document.sections[-1].footer.paragraphs[0]._p.xml
    assert "运维分析报告" not in body
    body_paragraph = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("正文见"))
    assert body_paragraph.paragraph_format.first_line_indent.pt == 21
    assert any(rel.target_ref == "https://example.test/report" for rel in document.part.rels.values())
    header_cell = document.tables[0].rows[0].cells[0]
    shading = header_cell._tc.tcPr.find(qn("w:shd"))
    assert shading.get(qn("w:fill")) == "F5F7FA"
    assert str(header_cell.paragraphs[0].runs[0].font.color.rgb) == "1A237E"
    assert header_cell.paragraphs[0].runs[0].bold is True
    assert document.paragraphs[0].runs[0].font.name == "微软雅黑"
    assert document.paragraphs[0].runs[0].font.size.pt == 22
    assert str(document.paragraphs[0].runs[0].font.color.rgb) == "1A237E"
    assert document.paragraphs[0].alignment is not None
    title_properties = document.paragraphs[0]._p.find(qn("w:pPr"))
    assert title_properties is None or title_properties.find(qn("w:pBdr")) is None
    assert all(paragraph.text != "目录" for paragraph in document.paragraphs)
    assert len(document.sections) == 1
    assert "w:titlePg" in document.sections[0]._sectPr.xml
    assert document.sections[0].first_page_header.paragraphs[0].text == ""
    assert "PAGE" in document.sections[0].first_page_footer.paragraphs[0]._p.xml
    section_heading = next(paragraph for paragraph in document.paragraphs if paragraph.text == "检查范围" and paragraph.style.name.startswith("Heading"))
    assert section_heading.runs[0].font.size.pt == 14
    assert str(section_heading.runs[0].font.color.rgb) == "1565C0"
    section_properties = section_heading._p.find(qn("w:pPr"))
    assert section_properties is None or section_properties.find(qn("w:pBdr")) is None
    borders = document.tables[0]._tbl.tblPr.find(qn("w:tblBorders"))
    assert borders.find(qn("w:insideV")).get(qn("w:val")) == "single"
    assert borders.find(qn("w:insideV")).get(qn("w:color")) == "E0E0E0"
    assert header_cell._tc.tcPr.find(qn("w:tcBorders")) is None
    table = document.tables[0]._tbl
    gap = int(_TABLE_GAP_PT * 20)
    assert int(table.getprevious().find(qn("w:pPr")).find(qn("w:spacing")).get(qn("w:after"))) == gap
    assert int(table.getnext().find(qn("w:pPr")).find(qn("w:spacing")).get(qn("w:after"))) == gap


def test_docx_cover_and_toc_each_start_a_page_and_drop_model_copies():
    payload = build_attachment_bytes(
        "# 封面\n\n告警现状与处置缺口\n\n数据来源：告警中心\n\n查询时间：2026 年 11 月 17 日\n\n报告版本：V1.0\n\n"
        "# 目录\n\n- 摘要\n\n# 摘要\n\n正文超过四十个字，用来确认长段落留在正文，而不是被收到封面上。\n\n"
        "## 分布\n\n### 状态分布\n",
        "docx",
        title="活动告警汇总",
    )
    document = Document(BytesIO(payload))
    paragraphs = document.paragraphs
    assert paragraphs[0].text == "运维分析报告"
    assert paragraphs[0].runs[0].bold is True
    assert paragraphs[0].runs[0].font.size.pt == 12
    assert str(paragraphs[0].runs[0].font.color.rgb) == "1565C0"
    assert paragraphs[1].text == "活动告警汇总"
    assert paragraphs[1].runs[0].font.size.pt == 26
    summary = next(paragraph for paragraph in paragraphs if paragraph.text == "告警现状与处置缺口")
    assert summary.runs[0].font.size.pt == 14
    assert str(summary.runs[0].font.color.rgb) == "616161"
    source = next(paragraph for paragraph in paragraphs if paragraph.text == "数据来源：告警中心")
    assert source.runs[0].font.size.pt == 10.5
    assert len(document.sections) == 3
    assert document.sections[-1].header.paragraphs[0].text == "活动告警汇总"
    assert 'w:start="1"' in document.sections[-1]._sectPr.xml
    detail = next(paragraph for paragraph in paragraphs if paragraph.text.startswith("状态分布"))
    assert detail.paragraph_format.left_indent.pt == 21
    body_paragraph = next(paragraph for paragraph in paragraphs if paragraph.text.startswith("正文超过"))
    assert body_paragraph.paragraph_format.first_line_indent.pt == 21
    assert body_paragraph.paragraph_format.left_indent.pt == 0
    assert document.styles["Normal"].font.size.pt == 10.5
    assert body_paragraph.paragraph_format.line_spacing == 1.6
    assert "PAGEREF _Toc3" in detail._p.xml
    heading = next(paragraph for paragraph in paragraphs if paragraph.text == "摘要" and paragraph.style.name.startswith("Heading"))
    assert 'w:name="_Toc1"' in heading._p.xml
    assert all(not paragraph.text.startswith("• 摘要") for paragraph in paragraphs)
    assert sum(paragraph.text == "目录" for paragraph in paragraphs) == 1


def test_pdf_html_cover_lists_intro_and_plain_toc():
    html = render_document_html(
        "告警现状与处置缺口\n\n数据来源：告警中心\n\n# 摘要\n\n正文。\n",
        "活动告警汇总",
    )
    assert 'class="eyebrow">运维分析报告<' in html
    assert 'class="subtitle">告警现状与处置缺口<' in html
    assert 'class="meta">数据来源：告警中心<' in html
    assert 'class="toc-row">摘要<' in html
    assert ".toc-row { margin: 0; padding: 0;" in html
    assert "font-size: 10.5pt; line-height: 1.7" in html
    assert ".toc-row.sub { padding-left: 1.5em; }" in html
    assert "toc-page" not in html
    assert "toc-leader" not in html


def test_docx_list_uses_brand_marker_instead_of_default_bullet():
    payload = build_attachment_bytes("- 活动告警 5 条\n- 已关闭 4 条\n", "docx", title="统计")
    document = Document(BytesIO(payload))
    items = [paragraph for paragraph in document.paragraphs if "活动告警" in paragraph.text or "已关闭" in paragraph.text]
    assert items[0].text.startswith("• 活动告警")
    assert str(items[0].runs[0].font.color.rgb) == "212121"
    assert items[0].style.name == "Normal"


def test_docx_ignores_excel_merge_arguments():
    payload = build_attachment_bytes("一段话", "docx", title="说明", merges=["A1:Z9"], header_rows=9)
    document = Document(BytesIO(payload))
    assert any(paragraph.text == "一段话" for paragraph in document.paragraphs)


def test_invalid_genre_is_rejected():
    with pytest.raises(ValueError, match="文档种类无效"):
        build_attachment_bytes("一段话", "docx", title="说明", genre="dense")


def test_business_report_callout_emphasizes_two_bold_numbers():
    content = "## 核心结论\n\n活动告警 **5** 条，关闭 **12** 条，遗留 **99** 条，**重点**不变。\n\n## 分布\n\n正文里的 **5** 不标红。\n"
    html = render_document_html(content, "活动告警汇总")
    assert 'class="callout"' in html
    assert html.count('class="emphasis"') == 2
    assert "<strong>99</strong>" in html
    assert "<strong>重点</strong>" in html
    body = html.split('<section class="body">', 1)[1]
    assert body.index("</aside>") < body.index(">分布<")
    payload = build_attachment_bytes(content, "docx", title="活动告警汇总")
    document = Document(BytesIO(payload))
    conclusion = next(paragraph for paragraph in document.paragraphs if "关闭" in paragraph.text)
    colors = {run.text: str(run.font.color.rgb) for run in conclusion.runs if run.text.strip()}
    assert colors["5"] == "C62828"
    assert colors["12"] == "C62828"
    assert colors["99"] == "212121"
    assert colors["重点"] == "212121"
    assert conclusion.paragraph_format.first_line_indent.pt == 0
    assert "w:fill" in conclusion._p.xml and "F5F7FA" in conclusion._p.xml


def test_meeting_minutes_keep_a_compact_cover_and_decision_callout():
    content = "周例会纪要\n\n会议时间：周一\n\n# 出席人员\n\n| 姓名 | 部门 |\n| --- | --- |\n| 甲 | 运维 |\n\n# 决议\n\n通过 **5** 项。\n"
    html = render_document_html(content, "周例会", genre="meeting_minutes")
    assert 'class="eyebrow">会议纪要<' in html
    assert 'class="cover compact"' in html
    assert 'class="meta">会议时间：周一<' in html
    assert "运维分析报告" not in html
    assert ">目录<" not in html
    assert 'class="callout"' in html
    assert 'class="emphasis"' not in html
    payload = build_attachment_bytes(content, "docx", title="周例会", genre="meeting_minutes")
    document = Document(BytesIO(payload))
    assert document.paragraphs[0].text == "会议纪要"
    assert len(document.sections) == 1
    assert all(paragraph.text != "目录" for paragraph in document.paragraphs)
    decision = next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("通过"))
    assert "F5F7FA" in decision._p.xml
    assert all(str(run.font.color.rgb) != "C62828" for run in decision.runs)


def test_official_html_has_no_report_cover_or_contents():
    html = render_document_html("# 巡检函\n\n正文。\n", "巡检函", genre="official")
    assert 'class="cover"' not in html
    assert ">目录<" not in html
    assert 'class="doc-title">巡检函<' in html
    assert 'class="official"' in html
    assert "运维分析报告" not in html


def test_xlsx_styles_header_numbers_and_explicit_merges():
    payload = build_attachment_bytes(
        "总标题,总标题\nname,count\nweb,2\nnote,12%",
        "xlsx",
        header_rows=2,
        merges=["A1:B1"],
    )
    sheet = load_workbook(BytesIO(payload)).active
    assert sheet.freeze_panes == "A3"
    assert sheet["A1"].value == "总标题"
    assert sheet["A1"].fill.patternType is None
    assert sheet["A2"].fill.fgColor.rgb.endswith("E3EBFD")
    assert sheet["A2"].font.bold is True
    assert sheet["A2"].font.name == "微软雅黑"
    assert sheet["B3"].value == 2
    assert sheet["B4"].value == "12%"
    assert "A1:B1" in {str(item) for item in sheet.merged_cells.ranges}


def test_xlsx_rejects_merge_outside_the_sheet():
    with pytest.raises(ValueError, match="合并范围无效"):
        build_attachment_bytes("name,count\nweb,2", "xlsx", merges=["A1:Z9"])


def test_unsafe_link_stays_text():
    payload = build_attachment_bytes("[点我](javascript:alert(1))", "docx", title="说明")
    document = Document(BytesIO(payload))
    paragraph = next(item for item in document.paragraphs if "点我" in item.text)
    assert "javascript:" not in paragraph._p.xml
