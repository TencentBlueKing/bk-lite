"""把 Markdown / CSV 收成带主题的 Word、PDF 和 Excel。

Word 与 PDF 共用一份文档结构。PDF 先排成 HTML，再由服务器里的 Chromium 打印。
Excel 是一张表，表头样式和合并范围在写入时套上。python-docx、openpyxl、Playwright
只在真正生成时导入，避免拖慢 Django 启动。
"""

from __future__ import annotations

import csv
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO

from apps.core.logger import opspilot_logger as logger

TITLE = "1A237E"
SECTION = "1565C0"
HEADER_FILL = "E3EBFD"
TABLE_HEADER = "F5F7FA"
TEXT = "212121"
MUTED = "616161"
CODE_FILL = "F2F3F5"
LINE = "D9DEE7"
RULE = "E0E0E0"
EMPHASIS = "C62828"
_BODY_HEADING_PT = {1: 16, 2: 14, 3: 12, 4: 12}
_BODY_HEADING_COLOR = {1: TITLE, 2: SECTION, 3: TEXT, 4: TEXT}
_TOC_LABELS = frozenset({"目录", "目 录"})
_COVER_LABELS = frozenset({"封面"})
_COVER_LINE_LIMIT = 80
_EMPHASIS_LIMIT = 2
_EMPHASIS_RE = re.compile(r"^\d+(?:\.\d+)?%?$")
_PAGE_BODY_PT = 640
_TOC_TAB_TWIPS = "8306"
_TABLE_GAP_PT = 10
FONT = "微软雅黑"
CODE_FONT = "Consolas"
_USABLE_MM = 146

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_UL_RE = re.compile(r"^(?:[ \t]*)[-*]\s+(.*)$")
_OL_RE = re.compile(r"^(?:[ \t]*)\d+[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SAFE_HREF_RE = re.compile(r"^(https?://|mailto:)\S+$", re.IGNORECASE)
_INTEGER_RE = re.compile(r"-?\d+")
_DECIMAL_RE = re.compile(r"-?\d+\.\d+")


class TextRun:
    def __init__(self, text: str, *, bold: bool = False, code: bool = False, href: str = "", emphasis: bool = False):
        self.text = text
        self.bold = bold
        self.code = code
        self.href = href
        self.emphasis = emphasis


class DocumentGenre:
    def __init__(
        self,
        name: str,
        *,
        rhythm: str,
        eyebrow: str,
        cover: bool,
        toc: bool,
        callout_titles: frozenset[str],
        meta_prefixes: tuple[str, ...],
        emphasize_numbers: bool,
    ):
        self.name = name
        self.rhythm = rhythm
        self.eyebrow = eyebrow
        self.cover = cover
        self.toc = toc
        self.callout_titles = callout_titles
        self.meta_prefixes = meta_prefixes
        self.emphasize_numbers = emphasize_numbers


_GENRES = {
    "business_report": DocumentGenre(
        "business_report",
        rhythm="spaced",
        eyebrow="运维分析报告",
        cover=True,
        toc=True,
        callout_titles=frozenset({"核心结论", "执行摘要"}),
        meta_prefixes=("数据来源", "查询时间", "报告版本"),
        emphasize_numbers=True,
    ),
    "official": DocumentGenre(
        "official",
        rhythm="official",
        eyebrow="",
        cover=False,
        toc=False,
        callout_titles=frozenset(),
        meta_prefixes=(),
        emphasize_numbers=False,
    ),
    "meeting_minutes": DocumentGenre(
        "meeting_minutes",
        rhythm="spaced",
        eyebrow="会议纪要",
        cover=True,
        toc=False,
        callout_titles=frozenset({"决议"}),
        meta_prefixes=("会议时间", "会议地点", "主持人", "记录人"),
        emphasize_numbers=False,
    ),
}


def inline_text(runs: list[TextRun]) -> str:
    return "".join(run.text for run in runs).strip()


def document_genre(value: str) -> DocumentGenre:
    name = str(value or "business_report").strip().lower()
    genre = _GENRES.get(name)
    if genre is None:
        raise ValueError("文档种类无效")
    return genre


def header_row_count(value) -> int:
    if isinstance(value, bool):
        raise ValueError("表头行数无效")
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise ValueError("表头行数无效") from None
    if count < 1:
        raise ValueError("表头行数无效")
    return count


def merge_ranges(value) -> list[str]:
    if value is None or value == "":
        return []
    items = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                items = json.loads(text)
            except json.JSONDecodeError:
                raise ValueError("合并范围无效") from None
        else:
            items = [part.strip() for part in text.split(",")]
    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise ValueError("合并范围无效")
    ranges = [str(item).strip() for item in items if str(item).strip()]
    return ranges


def iter_markdown_blocks(content: str):
    """标题、段落、列表、表格、代码。图片留下说明，引用收成段落，嵌套列表并进同一层。"""
    lines = (content or "").splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            yield ("code", "\n".join(body))
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            yield ("heading", len(heading.group(1)), _parse_inlines(heading.group(2)))
            index += 1
            continue
        if stripped in {"---", "***", "___"}:
            yield ("hr",)
            index += 1
            continue
        if stripped.startswith(">"):
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(_strip_quote(lines[index]))
                index += 1
            yield ("paragraph", _parse_inlines(" ".join(part for part in quote if part)))
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and _TABLE_SEP_RE.match(lines[index + 1].strip()):
            header = _split_row(stripped)
            index += 2
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_split_row(lines[index]))
                index += 1
            yield ("table", header, rows)
            continue
        if _UL_RE.match(lines[index]):
            items = []
            while index < len(lines) and _UL_RE.match(lines[index]):
                items.append(_parse_inlines(_UL_RE.match(lines[index]).group(1)))
                index += 1
            yield ("ul", items)
            continue
        if _OL_RE.match(lines[index]):
            items = []
            while index < len(lines) and _OL_RE.match(lines[index]):
                items.append(_parse_inlines(_OL_RE.match(lines[index]).group(1)))
                index += 1
            yield ("ol", items)
            continue
        paragraph = [stripped]
        index += 1
        while index < len(lines) and not _breaks_paragraph(lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        yield ("paragraph", _parse_inlines(" ".join(paragraph)))


def should_prefix_title(content: str, title: str) -> bool:
    for block in iter_markdown_blocks(content):
        if block[0] == "heading":
            return inline_text(block[2]) != (title or "").strip()
        return bool((title or "").strip())
    return bool((title or "").strip())


def _document_front(content: str, title: str, genre: DocumentGenre) -> tuple[list, list]:
    """有封面的成稿把正文前的简介和来源行留在封面。模型自写的封面和目录不进正文。"""
    cover: list = []
    body: list = []
    phase = "cover" if genre.cover else "body"
    title_text = (title or "").strip()
    skipped_title = False
    for block in iter_markdown_blocks(content):
        if block[0] == "heading":
            text = inline_text(block[2]).strip()
            if text in _COVER_LABELS or (phase == "cover" and text == title_text):
                continue
            if not genre.cover and not skipped_title and not body and text == title_text:
                skipped_title = True
                continue
            if text in _TOC_LABELS:
                phase = "toc"
                continue
            phase = "body"
            body.append(block)
            continue
        if phase == "toc":
            continue
        if phase == "cover" and block[0] == "paragraph" and _stays_on_cover(inline_text(block[1]), genre):
            cover.append(block)
            continue
        phase = "body"
        body.append(block)
    return cover, body


def _stays_on_cover(text: str, genre: DocumentGenre) -> bool:
    stripped = text.strip()
    if genre.meta_prefixes and stripped.startswith(genre.meta_prefixes):
        return True
    return 0 < len(stripped) <= _COVER_LINE_LIMIT


def _cover_notes(blocks: list, genre: DocumentGenre) -> tuple[list, list]:
    subtitle = []
    meta = []
    for block in blocks:
        if block[0] != "paragraph":
            continue
        text = inline_text(block[1]).strip()
        if not text or text == genre.eyebrow:
            continue
        if genre.meta_prefixes and text.startswith(genre.meta_prefixes):
            meta.append(block[1])
        else:
            subtitle.append(block[1])
    return subtitle, meta


def _toc_targets(body: list) -> list[tuple[int, str, int]]:
    """目录条目的级别、标题和正文页码。页码从正文第 1 页起算。"""
    used = 0
    page = 1
    targets = []
    for block in body:
        height = _block_height(block)
        if used and height > _PAGE_BODY_PT - used:
            page += 1
            used = 0
        if block[0] == "heading" and block[1] <= 3:
            text = inline_text(block[2]).strip()
            if text:
                targets.append((block[1], text, page))
        if height >= _PAGE_BODY_PT:
            extra, remainder = divmod(int(height), _PAGE_BODY_PT)
            page += extra
            used = remainder
        else:
            used += height
    return targets


def _block_height(block) -> int:
    kind = block[0]
    if kind == "heading":
        return {1: 40, 2: 34, 3: 28}.get(min(block[1], 4), 28)
    if kind in {"ul", "ol"}:
        return 22 * max(1, len(block[1]))
    if kind == "paragraph":
        lines = max(1, (len(inline_text(block[1])) + 31) // 32)
        return 8 + lines * 20
    if kind == "code":
        return 16 + max(1, str(block[1]).count("\n") + 1) * 16
    if kind == "table":
        return 8 + (1 + len(block[2])) * 22
    return 20


def render_document_html(content: str, title: str, genre: str = "business_report") -> str:
    kind = document_genre(genre)
    cover, body = _document_front(content, title, kind)
    parts = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
        f"<title>{_escape(title)}</title><style>{_DOCUMENT_CSS}</style></head>",
        f'<body class="{kind.rhythm}">',
    ]
    if kind.cover:
        parts.append(_html_cover(title, cover, kind))
    if kind.toc:
        parts.append(_html_toc(_toc_targets(body)))
    parts.append('<section class="body">')
    if not kind.cover:
        parts.append(f"<p class=\"doc-title\">{_escape(title or ' ')}</p>")
    parts.append(_html_body(body, kind))
    if not body and kind.cover:
        parts.append(f"<p>{_escape(title or content or ' ')}</p>")
    parts.append("</section></body></html>")
    return "".join(parts)


def _html_body(body: list, genre: DocumentGenre) -> str:
    parts = []
    open_level = 0
    for block in body:
        emphasize = False
        if block[0] == "heading":
            level = block[1]
            text = inline_text(block[2]).strip()
            if open_level and level <= open_level:
                parts.append("</aside>")
                open_level = 0
            if text in genre.callout_titles:
                parts.append('<aside class="callout">')
                open_level = level
        elif open_level and genre.emphasize_numbers:
            emphasize = True
        parts.append(_html_block(block, emphasize=emphasize))
    if open_level:
        parts.append("</aside>")
    return "".join(parts)


def _html_cover(title: str, blocks: list, genre: DocumentGenre) -> str:
    subtitle, meta = _cover_notes(blocks, genre)
    compact = "" if genre.toc else " compact"
    parts = [f'<section class="cover{compact}">']
    if genre.eyebrow:
        parts.append(f'<p class="eyebrow">{_escape(genre.eyebrow)}</p>')
    parts.append(f"<h1>{_escape(title or ' ')}</h1>")
    for runs in subtitle:
        parts.append(f'<p class="subtitle">{_html_runs(runs)}</p>')
    for runs in meta:
        parts.append(f'<p class="meta">{_html_runs(runs)}</p>')
    parts.append("</section>")
    return "".join(parts)


def _html_toc(targets: list[tuple[int, str, int]]) -> str:
    parts = ['<section class="toc"><h1>目录</h1>']
    for level, text, _page in targets:
        marker = " sub" if level >= 3 else ""
        parts.append(f'<p class="toc-row{marker}">{_escape(text)}</p>')
    parts.append("</section>")
    return "".join(parts)


def build_pdf_bytes(content: str, title: str, *, genre: str = "business_report") -> bytes:
    html = render_document_html(content, title, genre)
    return print_html_to_pdf(html, title)


def print_html_to_pdf(html: str, title: str) -> bytes:
    try:
        return _launch_chromium_pdf(html, title)
    except Exception as exc:
        logger.error(
            "attachment pdf print failed error_type=%s",
            type(exc).__name__,
            exc_info=True,
        )
        raise ValueError("PDF 生成失败") from exc


def build_docx_bytes(content: str, title: str, *, genre: str = "business_report") -> bytes:
    # 显著启动成本：python-docx 仅在生成 Word 时导入。
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor

    kind = document_genre(genre)
    document = Document()
    _prepare_docx(document, title, OxmlElement, qn, Mm, Pt, RGBColor)
    cover, body = _document_front(content, title, kind)
    if kind.toc:
        _add_docx_cover(document, title, cover, kind, qn, OxmlElement, Pt, RGBColor)
        toc_section = document.add_section(WD_SECTION.NEW_PAGE)
        _prepare_page(toc_section, Mm)
        _add_docx_toc(document, _toc_targets(body), qn, OxmlElement, Pt, RGBColor)
        body_section = document.add_section(WD_SECTION.NEW_PAGE)
        _prepare_page(body_section, Mm)
        _show_body_chrome(body_section, title, OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor)
        _restart_page_numbers(document.sections[-1], qn, OxmlElement)
    else:
        _show_body_chrome(
            document.sections[0],
            title,
            OxmlElement,
            qn,
            WD_ALIGN_PARAGRAPH,
            RGBColor,
            blank_first_header=True,
        )
        _restart_page_numbers(document.sections[0], qn, OxmlElement)
        if kind.cover:
            _add_docx_cover(document, title, cover, kind, qn, OxmlElement, Pt, RGBColor)
        else:
            _add_docx_official_title(document, title, qn, Pt, RGBColor, WD_ALIGN_PARAGRAPH)
    _add_docx_body(document, body, kind, qn, OxmlElement, Pt, Mm, RGBColor)
    if not body and kind.cover:
        _add_docx_paragraph(document, [TextRun(title or content or " ")], kind.rhythm, qn, OxmlElement, Pt, RGBColor)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_docx_body(document, body, genre: DocumentGenre, qn, OxmlElement, Pt, Mm, RGBColor) -> None:
    open_level = 0
    bookmark = 0
    for block in body:
        callout = bool(open_level)
        if block[0] == "heading":
            level = block[1]
            text = inline_text(block[2]).strip()
            if open_level and level <= open_level:
                open_level = 0
                callout = False
            if text in genre.callout_titles:
                callout = True
                open_level = level
        bookmark_name = ""
        if block[0] == "heading" and block[1] <= 3 and inline_text(block[2]).strip():
            bookmark += 1
            bookmark_name = f"_Toc{bookmark}"
        _add_docx_block(
            document,
            block,
            genre.rhythm,
            qn,
            OxmlElement,
            Pt,
            Mm,
            RGBColor,
            bookmark=bookmark_name,
            bookmark_id=bookmark,
            callout=callout,
            emphasize=callout and genre.emphasize_numbers and block[0] != "heading",
        )


def build_xlsx_bytes(content: str, *, header_rows: int = 1, merges: list[str] | None = None) -> bytes:
    # 显著启动成本：openpyxl 仅在生成表格时导入。
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter, range_boundaries

    count = header_row_count(header_rows)
    ranges = merge_ranges(merges)
    rows = _csv_rows(content)
    if count > len(rows):
        raise ValueError("表头行数无效")
    width = max(len(row) for row in rows)
    workbook = Workbook()
    sheet = workbook.active
    thin = Border(
        left=Side(style="thin", color=LINE),
        right=Side(style="thin", color=LINE),
        top=Side(style="thin", color=LINE),
        bottom=Side(style="thin", color=LINE),
    )
    header_fill = PatternFill("solid", fgColor=HEADER_FILL)
    for row_index, row in enumerate(rows, start=1):
        padded = list(row) + [""] * (width - len(row))
        for column_index, cell_text in enumerate(padded, start=1):
            value = _excel_value(cell_text)
            cell = sheet.cell(row_index, column_index, value)
            cell.border = thin
            cell.alignment = Alignment(
                vertical="center",
                wrap_text=True,
                horizontal="right" if isinstance(value, (int, float)) else "left",
            )
            if row_index < count:
                cell.font = Font(name=FONT, bold=True, size=14, color=TEXT)
            elif row_index == count:
                cell.font = Font(name=FONT, bold=True, color=TEXT)
                cell.fill = header_fill
            else:
                cell.font = Font(name=FONT, color=TEXT)
    for ref in ranges:
        _merge_sheet(sheet, ref, row_count=len(rows), column_count=width, range_boundaries=range_boundaries)
    for column_index in range(1, width + 1):
        longest = 0
        for row in rows:
            if column_index - 1 < len(row):
                longest = max(longest, len(str(row[column_index - 1])))
        sheet.column_dimensions[get_column_letter(column_index)].width = min(48, max(10, longest + 2))
    sheet.freeze_panes = f"A{count + 1}"
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


_DOCUMENT_CSS = """
@page { size: A4; margin: 25.4mm 31.8mm 25.4mm 31.8mm; }
body { margin: 0; color: #212121; font-family: "微软雅黑", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; font-size: 10.5pt; line-height: 1.7; }
.cover, .toc { page-break-after: always; }
.cover.compact { page-break-after: auto; }
.cover .eyebrow { margin: 0 0 10px; color: #1565C0; font-size: 12pt; font-weight: 700; text-indent: 0; }
.cover h1 { margin: 0 0 6px; font-size: 26pt; line-height: 1.25; color: #1A237E; }
.cover .subtitle { margin: 4px 0 22px; color: #616161; font-size: 14pt; text-indent: 0; }
.cover .meta { margin: 0 0 2px; color: #616161; font-size: 10.5pt; text-indent: 0; }
.toc h1 { margin: 0 0 12px; font-size: 16pt; color: #1565C0; }
.toc-row { margin: 0; padding: 0; font-size: 12pt; line-height: 2; text-indent: 0; }
.toc-row.sub { padding-left: 1.5em; }
h1, h2, h3, h4 { margin: 14px 0 6px; line-height: 1.35; }
h1 { font-size: 16pt; color: #1A237E; }
h2 { font-size: 14pt; color: #1565C0; }
h3, h4 { font-size: 12pt; color: #212121; }
body .body p { text-indent: 2em; line-height: 1.6; }
body.spaced .body p { margin: 0 0 7.2pt; }
body.official .body p { margin: 0 0 2px; }
body .body p.doc-title { margin: 0 0 16pt; text-align: center; text-indent: 0; font-size: 22pt; font-weight: 700; color: #1A237E; }
.callout { margin: 10pt 0; padding: 10pt 12pt; background: #F5F7FA; border-left: 3pt solid #1565C0; }
body .body .callout p { text-indent: 0; }
.emphasis { color: #C62828; font-weight: 700; }
ul, ol { margin: 0 0 10px; padding-left: 1.2em; }
li { margin: 0 0 3px; }
table { width: 100%; border-collapse: collapse; margin: 10pt 0; table-layout: fixed; }
th, td { border: 1px solid #E0E0E0; padding: 6px 8px; vertical-align: middle; word-wrap: break-word; }
th { background: #F5F7FA; color: #1A237E; font-weight: 700; }
code { font-family: Consolas, "Courier New", monospace; background: #F2F3F5; padding: 0 3px; }
pre { margin: 0 0 12px; padding: 8px 10px; background: #F2F3F5; white-space: pre-wrap; }
pre code { background: transparent; padding: 0; }
a { color: #1565C0; text-decoration: underline; }
hr { border: 0; border-top: 1px solid #E0E0E0; margin: 12px 0; }
"""


def _parse_inlines(text: str) -> list[TextRun]:
    runs: list[TextRun] = []
    plain: list[str] = []
    index = 0

    def flush() -> None:
        if plain:
            runs.append(TextRun("".join(plain)))
            plain.clear()

    while index < len(text):
        if text.startswith("![", index):
            image = _IMAGE_RE.match(text, index)
            if image:
                flush()
                if image.group(1):
                    runs.append(TextRun(image.group(1)))
                index = image.end()
                continue
        if text.startswith("[", index):
            link = _LINK_RE.match(text, index)
            if link:
                flush()
                href = _safe_href(link.group(2))
                for run in _parse_inlines(link.group(1)):
                    run.href = href
                    runs.append(run)
                index = link.end()
                continue
        if text.startswith("**", index) or text.startswith("__", index):
            marker = text[index : index + 2]
            end = text.find(marker, index + 2)
            if end != -1:
                flush()
                for run in _parse_inlines(text[index + 2 : end]):
                    run.bold = True
                    runs.append(run)
                index = end + 2
                continue
        if text.startswith("`", index):
            end = text.find("`", index + 1)
            if end != -1:
                flush()
                runs.append(TextRun(text[index + 1 : end], code=True))
                index = end + 1
                continue
        plain.append(text[index])
        index += 1
    flush()
    return runs


def _safe_href(href: str) -> str:
    candidate = (href or "").strip()
    if _SAFE_HREF_RE.match(candidate):
        return candidate
    return ""


def _strip_quote(line: str) -> str:
    text = line.strip()
    while text.startswith(">"):
        text = text[1:].lstrip()
    return text


def _split_row(line: str) -> list[list[TextRun]]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return [_parse_inlines(cell) for cell in cells]


def _breaks_paragraph(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped in {"---", "***", "___"} or stripped.startswith(("|", ">", "```")):
        return True
    return bool(_HEADING_RE.match(stripped) or _UL_RE.match(line) or _OL_RE.match(line))


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _with_emphasis(runs: list[TextRun]) -> list[TextRun]:
    """核心结论里的加粗数字才标红，普通加粗保持正文色。一段最多两个。"""
    remaining = _EMPHASIS_LIMIT
    marked: list[TextRun] = []
    for run in runs:
        emphasis = False
        if remaining and run.bold and not run.code and not run.href and _EMPHASIS_RE.match(run.text.strip()):
            emphasis = True
            remaining -= 1
        marked.append(TextRun(run.text, bold=run.bold, code=run.code, href=run.href, emphasis=emphasis))
    return marked


def _html_runs(runs: list[TextRun]) -> str:
    chunks = []
    for run in runs:
        piece = _escape(run.text)
        if run.code:
            piece = f"<code>{piece}</code>"
        if run.bold:
            piece = f"<strong>{piece}</strong>"
        if run.emphasis:
            piece = f'<span class="emphasis">{piece}</span>'
        href = _safe_href(run.href)
        if href:
            piece = f'<a href="{_escape(href)}">{piece}</a>'
        chunks.append(piece)
    return "".join(chunks)


def _html_block(block, *, emphasize: bool = False) -> str:
    kind = block[0]
    if kind == "heading":
        level = min(block[1], 4)
        return f"<h{level}>{_html_runs(block[2])}</h{level}>"
    if kind == "paragraph":
        runs = _with_emphasis(block[1]) if emphasize else block[1]
        return f"<p>{_html_runs(runs)}</p>"
    if kind == "ul":
        items = "".join(f"<li>{_html_runs(_with_emphasis(item) if emphasize else item)}</li>" for item in block[1])
        return f"<ul>{items}</ul>"
    if kind == "ol":
        items = "".join(f"<li>{_html_runs(_with_emphasis(item) if emphasize else item)}</li>" for item in block[1])
        return f"<ol>{items}</ol>"
    if kind == "code":
        return f"<pre><code>{_escape(block[1])}</code></pre>"
    if kind == "hr":
        return "<hr>"
    if kind == "table":
        return _html_table(block[1], block[2])
    return ""


def _column_weights(header: list, rows: list) -> list[int]:
    count = max([len(header), *[len(row) for row in rows], 1])
    weights = []
    for index in range(count):
        texts = []
        if index < len(header):
            texts.append(inline_text(header[index]))
        for row in rows:
            if index < len(row):
                texts.append(inline_text(row[index]))
        weights.append(max(4, max((len(text) for text in texts), default=4)))
    return weights


def _html_table(header: list, rows: list) -> str:
    weights = _column_weights(header, rows)
    total = sum(weights) or 1
    columns = "".join(f'<col style="width:{round(100 * weight / total)}%">' for weight in weights)
    head = "".join(f"<th>{_html_runs(header[index] if index < len(header) else [])}</th>" for index in range(len(weights)))
    body = []
    width = len(weights)
    for row in rows:
        cells = []
        for index in range(width):
            runs = row[index] if index < len(row) else []
            cells.append(f"<td>{_html_runs(runs)}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><colgroup>{columns}</colgroup><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _launch_chromium_pdf(html: str, title: str) -> bytes:
    from playwright.sync_api import sync_playwright

    header = '<div style="font-family:Microsoft YaHei,sans-serif;font-size:10px;width:100%;' f'padding:0 8px;color:#{MUTED};">{_escape(title)}</div>'
    footer = (
        '<div style="font-family:Microsoft YaHei,sans-serif;font-size:10px;width:100%;'
        f'text-align:center;color:#{MUTED};">第 <span class="pageNumber"></span> 页</div>'
    )

    def _print() -> bytes:
        with sync_playwright() as playwright:
            options = {"headless": True}
            executable = os.environ.get("EXECUTABLE_PATH")
            if executable:
                options["executable_path"] = executable
            browser = playwright.chromium.launch(**options)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                return page.pdf(
                    format="A4",
                    print_background=True,
                    display_header_footer=True,
                    header_template=header,
                    footer_template=footer,
                    margin={"top": "25.4mm", "bottom": "25.4mm", "left": "31.8mm", "right": "31.8mm"},
                )
            finally:
                browser.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_print).result()


def _prepare_docx(document, title, OxmlElement, qn, Mm, Pt, RGBColor) -> None:
    _prepare_page(document.sections[0], Mm)
    normal = document.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(TEXT)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    for level, size in _BODY_HEADING_PT.items():
        heading_style = document.styles[f"Heading {level}"]
        heading_style.font.name = FONT
        heading_style.font.size = Pt(size)
        heading_style.font.bold = True
        heading_style.font.color.rgb = RGBColor.from_string(_BODY_HEADING_COLOR[level])
        heading_style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    document.core_properties.title = title or ""


def _prepare_page(section, Mm) -> None:
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(31.8)
    section.right_margin = Mm(31.8)
    section.top_margin = Mm(25.4)
    section.bottom_margin = Mm(25.4)
    section.header_distance = Mm(8)
    section.footer_distance = Mm(8)


def _show_body_chrome(section, title, OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor, *, blank_first_header: bool = False) -> None:
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    if blank_first_header:
        section.different_first_page_header_footer = True
        section.first_page_header.is_linked_to_previous = False
        section.first_page_footer.is_linked_to_previous = False
        _write_page_footer(section.first_page_footer.paragraphs[0], OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor)
    _write_running_header(section.header.paragraphs[0], title, OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor)
    _write_page_footer(section.footer.paragraphs[0], OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor)


def _write_running_header(header, title, OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor) -> None:
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_run = header.add_run(title or "")
    _paint_docx_run(header_run, qn, RGBColor, size=9, color=MUTED)
    _mark_edge(header, qn, OxmlElement, edge="bottom", size="6", space="1", color=LINE)


def _write_page_footer(footer, OxmlElement, qn, WD_ALIGN_PARAGRAPH, RGBColor) -> None:
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    prefix = footer.add_run("第 ")
    _paint_docx_run(prefix, qn, RGBColor, size=9, color=MUTED)
    field = footer.add_run()
    _paint_docx_run(field, qn, RGBColor, size=9, color=MUTED)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    field._r.append(begin)
    field._r.append(instruction)
    field._r.append(end)
    suffix = footer.add_run(" 页")
    _paint_docx_run(suffix, qn, RGBColor, size=9, color=MUTED)


def _restart_page_numbers(section, qn, OxmlElement) -> None:
    numbering = OxmlElement("w:pgNumType")
    numbering.set(qn("w:start"), "1")
    section._sectPr.append(numbering)


def _paint_docx_run(run, qn, RGBColor, *, code: bool = False, bold: bool = False, size: int | float | None = None, color: str = TEXT) -> None:
    from docx.shared import Pt

    font_name = CODE_FONT if code else FONT
    run.font.name = font_name
    run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    if size:
        run.font.size = Pt(size)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)


def _fill_docx_runs(
    paragraph,
    runs: list[TextRun],
    qn,
    OxmlElement,
    RGBColor,
    *,
    bold: bool = False,
    size: int | float | None = None,
    color: str = TEXT,
) -> None:
    # 显著启动成本：超链接关系类型属于 python-docx，不能在模块顶层导入。
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    for run in runs:
        href = _safe_href(run.href)
        if href:
            _add_docx_hyperlink(paragraph, run, href, qn, OxmlElement, RGBColor, RT, bold=bold or run.bold)
            continue
        text_run = paragraph.add_run(run.text)
        run_color = EMPHASIS if run.emphasis else color
        _paint_docx_run(text_run, qn, RGBColor, code=run.code, bold=bold or run.bold or run.emphasis, size=size, color=run_color)
        if run.code:
            shading = OxmlElement("w:shd")
            shading.set(qn("w:val"), "clear")
            shading.set(qn("w:fill"), CODE_FILL)
            text_run._element.get_or_add_rPr().append(shading)


def _add_docx_hyperlink(paragraph, run: TextRun, href: str, qn, OxmlElement, RGBColor, RT, *, bold: bool) -> None:
    relation_id = paragraph.part.relate_to(href, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relation_id)
    text_run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    font_name = CODE_FONT if run.code else FONT
    fonts.set(qn("w:ascii"), font_name)
    fonts.set(qn("w:hAnsi"), font_name)
    fonts.set(qn("w:eastAsia"), font_name)
    properties.append(fonts)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), SECTION)
    properties.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)
    if bold:
        properties.append(OxmlElement("w:b"))
    text_run.append(properties)
    text = OxmlElement("w:t")
    text.set(qn("xml:space"), "preserve")
    text.text = run.text
    text_run.append(text)
    hyperlink.append(text_run)
    paragraph._p.append(hyperlink)


def _mark_edge(paragraph, qn, OxmlElement, *, edge: str, size: str, space: str, color: str) -> None:
    properties = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    line = OxmlElement(f"w:{edge}")
    line.set(qn("w:val"), "single")
    line.set(qn("w:sz"), size)
    line.set(qn("w:space"), space)
    line.set(qn("w:color"), color)
    borders.append(line)
    properties.append(borders)


def _add_docx_official_title(document, title, qn, Pt, RGBColor, WD_ALIGN_PARAGRAPH) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_after = Pt(16)
    run = paragraph.add_run((title or "").strip() or " ")
    _paint_docx_run(run, qn, RGBColor, bold=True, size=22, color=TITLE)


def _add_docx_cover(document, title, blocks, genre: DocumentGenre, qn, OxmlElement, Pt, RGBColor) -> None:
    subtitle, meta = _cover_notes(blocks, genre)
    if genre.eyebrow:
        eyebrow = document.add_paragraph()
        eyebrow.paragraph_format.space_after = Pt(10)
        run = eyebrow.add_run(genre.eyebrow)
        _paint_docx_run(run, qn, RGBColor, bold=True, size=12, color=SECTION)
    title_paragraph = document.add_paragraph()
    title_paragraph.paragraph_format.space_after = Pt(6 if subtitle else 22)
    run = title_paragraph.add_run((title or "").strip() or " ")
    _paint_docx_run(run, qn, RGBColor, bold=True, size=26, color=TITLE)
    for index, runs in enumerate(subtitle):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(22 if index == len(subtitle) - 1 else 4)
        _fill_docx_runs(paragraph, runs, qn, OxmlElement, RGBColor, size=14, color=MUTED)
    for runs in meta:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        _fill_docx_runs(paragraph, runs, qn, OxmlElement, RGBColor, size=10.5, color=MUTED)


def _add_docx_toc(document, targets, qn, OxmlElement, Pt, RGBColor) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(12)
    run = paragraph.add_run("目录")
    _paint_docx_run(run, qn, RGBColor, bold=True, size=16, color=TITLE)
    for index, (level, text, page) in enumerate(targets, start=1):
        item = document.add_paragraph()
        item.paragraph_format.line_spacing = 1.5
        if level >= 3:
            item.paragraph_format.left_indent = Pt(21)
            item.paragraph_format.space_before = Pt(0)
            item.paragraph_format.space_after = Pt(3)
        else:
            item.paragraph_format.space_before = Pt(6)
            item.paragraph_format.space_after = Pt(6)
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "right")
        tab.set(qn("w:leader"), "dot")
        tab.set(qn("w:pos"), _TOC_TAB_TWIPS)
        tabs.append(tab)
        item._p.get_or_add_pPr().append(tabs)
        entry = item.add_run(text)
        _paint_docx_run(entry, qn, RGBColor, size=12, color=TEXT)
        _append_pageref(item, f"_Toc{index}", page, qn, OxmlElement, RGBColor)


def _append_pageref(paragraph, bookmark: str, page: int, qn, OxmlElement, RGBColor) -> None:
    tab_run = paragraph.add_run()
    _paint_docx_run(tab_run, qn, RGBColor, size=12, color=TEXT)
    tab_run._r.append(OxmlElement("w:tab"))

    def _field_run() -> object:
        run = paragraph.add_run()
        _paint_docx_run(run, qn, RGBColor, size=12, color=TEXT)
        return run

    begin = _field_run()
    begin_char = OxmlElement("w:fldChar")
    begin_char.set(qn("w:fldCharType"), "begin")
    begin._r.append(begin_char)
    instruction_run = _field_run()
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = f" PAGEREF {bookmark} \\h "
    instruction_run._r.append(instruction)
    separate = _field_run()
    separate_char = OxmlElement("w:fldChar")
    separate_char.set(qn("w:fldCharType"), "separate")
    separate._r.append(separate_char)
    shown = paragraph.add_run(str(page))
    _paint_docx_run(shown, qn, RGBColor, size=12, color=TEXT)
    end = _field_run()
    end_char = OxmlElement("w:fldChar")
    end_char.set(qn("w:fldCharType"), "end")
    end._r.append(end_char)


def _bookmark_heading(paragraph, name: str, bookmark_id: int, qn, OxmlElement) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    properties = paragraph._p.find(qn("w:pPr"))
    if properties is None:
        paragraph._p.insert(0, start)
    else:
        properties.addnext(start)
    paragraph._p.append(end)


def _add_docx_heading(
    document, runs, level, qn, OxmlElement, Pt, RGBColor, *, bookmark: str = "", bookmark_id: int = 0, callout: bool = False
) -> None:
    level = min(level, 4)
    paragraph = document.add_heading("", level=level)
    paragraph.paragraph_format.space_before = Pt(12 if level == 1 else 10)
    paragraph.paragraph_format.space_after = Pt(6)
    _fill_docx_runs(
        paragraph,
        runs,
        qn,
        OxmlElement,
        RGBColor,
        bold=True,
        size=_BODY_HEADING_PT[level],
        color=_BODY_HEADING_COLOR[level],
    )
    if bookmark:
        _bookmark_heading(paragraph, bookmark, bookmark_id, qn, OxmlElement)
    if callout:
        _shade_callout(paragraph, qn, OxmlElement)


def _add_docx_paragraph(document, runs, style, qn, OxmlElement, Pt, RGBColor, *, callout: bool = False, emphasize: bool = False) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Pt(6 if callout else 0)
    paragraph.paragraph_format.first_line_indent = Pt(0 if callout else 21)
    paragraph.paragraph_format.line_spacing = 1.6
    paragraph.paragraph_format.space_after = Pt(2 if style == "official" else 7.2)
    _fill_docx_runs(paragraph, _with_emphasis(runs) if emphasize else runs, qn, OxmlElement, RGBColor)
    if callout:
        _shade_callout(paragraph, qn, OxmlElement)


def _add_docx_block(
    document,
    block,
    style,
    qn,
    OxmlElement,
    Pt,
    Mm,
    RGBColor,
    *,
    bookmark: str = "",
    bookmark_id: int = 0,
    callout: bool = False,
    emphasize: bool = False,
) -> None:
    kind = block[0]
    if kind == "heading":
        _add_docx_heading(
            document,
            block[2],
            block[1],
            qn,
            OxmlElement,
            Pt,
            RGBColor,
            bookmark=bookmark,
            bookmark_id=bookmark_id,
            callout=callout,
        )
    elif kind == "ul":
        _add_docx_list(
            document, block[1], ordered=False, qn=qn, OxmlElement=OxmlElement, Pt=Pt, RGBColor=RGBColor, callout=callout, emphasize=emphasize
        )
    elif kind == "ol":
        _add_docx_list(
            document, block[1], ordered=True, qn=qn, OxmlElement=OxmlElement, Pt=Pt, RGBColor=RGBColor, callout=callout, emphasize=emphasize
        )
    elif kind == "paragraph":
        _add_docx_paragraph(document, block[1], style, qn, OxmlElement, Pt, RGBColor, callout=callout, emphasize=emphasize)
    elif kind == "code":
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(8)
        text_run = paragraph.add_run(block[1])
        _paint_docx_run(text_run, qn, RGBColor, code=True)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:fill"), CODE_FILL)
        paragraph._p.get_or_add_pPr().append(shading)
        if callout:
            _shade_callout(paragraph, qn, OxmlElement)
    elif kind == "hr":
        paragraph = document.add_paragraph()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), LINE)
        borders.append(bottom)
        paragraph._p.get_or_add_pPr().append(borders)
    elif kind == "table":
        _add_table_gap(document, Pt, qn, RGBColor)
        _add_docx_table(document, block[1], block[2], qn, OxmlElement, Mm, RGBColor)
        _add_table_gap(document, Pt, qn, RGBColor)


def _add_docx_list(document, items, *, ordered: bool, qn, OxmlElement, Pt, RGBColor, callout: bool = False, emphasize: bool = False) -> None:
    for index, item in enumerate(items, start=1):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Pt(18)
        paragraph.paragraph_format.first_line_indent = Pt(-14)
        paragraph.paragraph_format.space_after = Pt(3)
        marker = paragraph.add_run(f"{index}. " if ordered else "• ")
        _paint_docx_run(marker, qn, RGBColor, size=10.5)
        runs = _with_emphasis(item) if emphasize else item
        _fill_docx_runs(paragraph, runs, qn, OxmlElement, RGBColor, size=10.5)
        if callout:
            _shade_callout(paragraph, qn, OxmlElement)


def _shade_callout(paragraph, qn, OxmlElement) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), TABLE_HEADER)
    paragraph._p.get_or_add_pPr().append(shading)
    _mark_edge(paragraph, qn, OxmlElement, edge="left", size="12", space="4", color=SECTION)


def _add_table_gap(document, Pt, qn, RGBColor) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(_TABLE_GAP_PT)
    paragraph.paragraph_format.line_spacing = Pt(1)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.left_indent = Pt(0)
    _paint_docx_run(paragraph.add_run(), qn, RGBColor, size=1)


def _add_docx_table(document, header, rows, qn, OxmlElement, Mm, RGBColor) -> None:
    weights = _column_weights(header, rows)
    table = document.add_table(rows=1 + len(rows), cols=len(weights))
    table.autofit = False
    widths = [_USABLE_MM * weight / (sum(weights) or 1) for weight in weights]
    _set_docx_table_borders(table, qn, OxmlElement)
    _write_docx_row(table.rows[0], header, weights, qn, OxmlElement, RGBColor, header=True)
    for row_index, row in enumerate(rows, start=1):
        padded = list(row) + [[] for _ in range(len(weights) - len(row))]
        _write_docx_row(table.rows[row_index], padded, weights, qn, OxmlElement, RGBColor, header=False)
    _set_docx_widths(table, widths, qn, OxmlElement, Mm)


def _set_docx_table_borders(table, qn, OxmlElement) -> None:
    properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        line = OxmlElement(f"w:{edge}")
        line.set(qn("w:val"), "single")
        line.set(qn("w:sz"), "4")
        line.set(qn("w:space"), "0")
        line.set(qn("w:color"), RULE)
        borders.append(line)
    cell_margin = OxmlElement("w:tblCellMar")
    for edge, width in (("top", "60"), ("left", "100"), ("bottom", "60"), ("right", "100")):
        side = OxmlElement(f"w:{edge}")
        side.set(qn("w:w"), width)
        side.set(qn("w:type"), "dxa")
        cell_margin.append(side)
    properties.append(borders)
    properties.append(cell_margin)


def _write_docx_row(row, cells, weights, qn, OxmlElement, RGBColor, *, header: bool) -> None:
    for index in range(len(weights)):
        runs = cells[index] if index < len(cells) else []
        cell = row.cells[index]
        from docx.shared import Pt

        paragraph = cell.paragraphs[0]
        for existing in list(paragraph.runs):
            paragraph._p.remove(existing._r)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        _fill_docx_runs(paragraph, runs, qn, OxmlElement, RGBColor, bold=header, size=10, color=TITLE if header else TEXT)
        if header:
            shading = OxmlElement("w:shd")
            shading.set(qn("w:val"), "clear")
            shading.set(qn("w:fill"), TABLE_HEADER)
            cell._tc.get_or_add_tcPr().append(shading)


def _set_docx_widths(table, widths, qn, OxmlElement, Mm) -> None:
    grid = OxmlElement("w:tblGrid")
    for width in widths:
        column = OxmlElement("w:gridCol")
        column.set(qn("w:w"), str(int(width * 56.7)))
        grid.append(column)
    existing = table._tbl.find(qn("w:tblGrid"))
    if existing is not None:
        table._tbl.remove(existing)
    table._tbl.tblPr.addnext(grid)
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            cell.width = Mm(widths[index])


def _csv_rows(content: str) -> list[list[str]]:
    rows = []
    for row in csv.reader(StringIO((content or "").lstrip("\ufeff"))):
        if any(cell.strip() for cell in row):
            rows.append(row)
    return rows or [[""]]


def _excel_value(cell: str):
    text = (cell or "").strip()
    if _INTEGER_RE.fullmatch(text):
        return int(text)
    if _DECIMAL_RE.fullmatch(text):
        return float(text)
    return cell


def _merge_sheet(sheet, ref: str, *, row_count: int, column_count: int, range_boundaries) -> None:
    try:
        min_col, min_row, max_col, max_row = range_boundaries(str(ref).replace("$", ""))
    except ValueError:
        raise ValueError(f"合并范围无效: {ref}") from None
    if min_col < 1 or min_row < 1 or max_row > row_count or max_col > column_count or (min_row == max_row and min_col == max_col):
        raise ValueError(f"合并范围无效: {ref}")
    try:
        sheet.merge_cells(ref)
    except ValueError:
        raise ValueError(f"合并范围无效: {ref}") from None
