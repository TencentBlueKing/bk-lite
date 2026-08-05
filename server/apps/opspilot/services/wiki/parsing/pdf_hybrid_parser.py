"""PDF hybrid parse: MarkItDown per page; rasterize pages with fragmented tables.

Uses pymupdf for single-page export + PNG render. Images are persisted via
`save_media_bytes` so Markdown references stable `wiki/media/...` locators.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from typing import Callable, Optional

import fitz

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.wiki.parsed_media_service import save_media_bytes
from apps.opspilot.services.wiki.parsing.architecture_normalize import normalize_architecture_feature_maps_in_markdown
from apps.opspilot.services.wiki.parsing.flow_table_normalize import normalize_numbered_flow_tables_in_markdown
from apps.opspilot.services.wiki.parsing.fragmented_table import (
    analyze_table_fragmentation,
    extract_markdown_tables,
    salvage_sparse_layout_tables_in_markdown,
    should_rasterize_pdf_page,
)
from apps.opspilot.services.wiki.parsing.markitdown_parser import MarkItDownParser

# ~144 DPI (2x default 72)
_RENDER_MATRIX = fitz.Matrix(2, 2)

_DescribePage = Callable[[bytes, int], Optional[str]]

# Log at most this many chars of MarkItDown page text for diagnosis.
_PAGE_MD_LOG_CHARS = 400


def _snippet(text: str, limit: int = _PAGE_MD_LOG_CHARS) -> str:
    raw = (text or "").replace("\r\n", "\n").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit] + f"…(+{len(raw) - limit} chars)"


def _page_table_metrics(page_md: str) -> list[dict]:
    out: list[dict] = []
    for i, table in enumerate(extract_markdown_tables(page_md or "")):
        m = analyze_table_fragmentation(table)
        out.append(
            {
                "index": i,
                "chars": len(table),
                "col_count": m["col_count"],
                "nonempty": m["nonempty_count"],
                "empty_ratio": round(m["empty_ratio"], 3),
                "avg_len": round(m["avg_len"], 2),
                "short_ratio": round(m["short_ratio"], 3),
                "leaked_sep": m["leaked_sep_rows"],
                "wrap_count": m["wrap_count"],
            }
        )
    return out


def _safe_alt(text: str) -> str:
    cleaned = re.sub(r"[\r\n\[\]]", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip() or "page"


def _default_page_alt(page_number: int) -> str:
    return f"第 {page_number} 页"


def _convert_single_page_pdf(
    parser: MarkItDownParser,
    page_pdf_bytes: bytes,
    *,
    vision_client=None,
    vision_model=None,
) -> str:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(page_pdf_bytes)
            tmp_path = tmp.name
        return parser._convert(
            tmp_path,
            vision_client=vision_client,
            vision_model=vision_model,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _export_single_page_pdf(src: fitz.Document, page_index: int) -> bytes:
    out = fitz.open()
    try:
        out.insert_pdf(src, from_page=page_index, to_page=page_index)
        return out.tobytes()
    finally:
        out.close()


def _render_page_png(page: fitz.Page) -> bytes:
    pix = page.get_pixmap(matrix=_RENDER_MATRIX, alpha=False)
    return pix.tobytes("png")


def _page_image_markdown(
    material,
    page: fitz.Page,
    page_number: int,
    *,
    describe_page: _DescribePage | None = None,
) -> str:
    png = _render_page_png(page)
    locator = save_media_bytes(material, png, "image/png")
    alt = _default_page_alt(page_number)
    if describe_page is not None:
        try:
            described = describe_page(png, page_number)
            if described:
                alt = _safe_alt(described)
        except Exception:
            logger.exception(
                "material %s page %s vision alt failed; using default",
                getattr(material, "id", None),
                page_number,
            )
    return f"![{alt}]({locator})"


def describe_page_with_vision(
    vision_client,
    vision_model: str,
    png_bytes: bytes,
    page_number: int,
) -> str | None:
    """Ask vision model for a short alt text of a page PNG. Returns None on failure."""
    if vision_client is None or not vision_model:
        return None
    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    try:
        resp = vision_client.chat.completions.create(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (f"用一两句中文概括这张 PDF 第 {page_number} 页的主要内容，" "作为图片 alt 文本。不要使用方括号或换行。"),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
            max_tokens=200,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content or None
    except Exception:
        logger.exception("vision page describe failed page=%s", page_number)
        return None


def convert_pdf_hybrid(
    material,
    data: bytes,
    *,
    vision_client=None,
    vision_model=None,
    parser: MarkItDownParser | None = None,
    describe_page: _DescribePage | None = None,
) -> str:
    """Convert PDF bytes to markdown with fragmented pages replaced by page images.

    When MarkItDown fails for a page, that page is rasterized (plan default).
    """
    if not data:
        return ""
    material_id = getattr(material, "id", None)
    parser = parser or MarkItDownParser()
    doc = fitz.open(stream=data, filetype="pdf")
    parts: list[str] = []
    try:
        page_count = doc.page_count
        logger.info(
            "material %s PDF hybrid start pages=%s bytes=%s vision=%s",
            material_id,
            page_count,
            len(data),
            bool(describe_page),
        )
        for page_index in range(page_count):
            page_number = page_index + 1
            page = doc.load_page(page_index)
            marker = f"<!-- Page number: {page_number} -->"
            page_md = ""
            convert_failed = False
            try:
                page_pdf = _export_single_page_pdf(doc, page_index)
                page_md = _convert_single_page_pdf(
                    parser,
                    page_pdf,
                    vision_client=vision_client,
                    vision_model=vision_model,
                )
            except Exception:
                convert_failed = True
                logger.warning(
                    "material %s PDF page %s MarkItDown failed; rasterizing",
                    material_id,
                    page_number,
                    exc_info=True,
                )

            raw_len = len(page_md or "")
            raw_tables = _page_table_metrics(page_md) if page_md else []
            flow_changed = False
            arch_changed = False
            if page_md and not convert_failed:
                before_flow = page_md
                # 流程图稀疏表 → 规整「步骤|名称|说明」
                page_md = normalize_numbered_flow_tables_in_markdown(page_md)
                flow_changed = page_md != before_flow
                before_arch = page_md
                # 产品架构功能块稀疏表 → 规整「模块|功能」；仍碎的再出图
                page_md = normalize_architecture_feature_maps_in_markdown(page_md)
                arch_changed = page_md != before_arch

            use_image = convert_failed or should_rasterize_pdf_page(page_md)
            disposition = "keep_text"
            if use_image:
                try:
                    body = _page_image_markdown(
                        material,
                        page,
                        page_number,
                        describe_page=describe_page,
                    )
                    disposition = "rasterize"
                except Exception:
                    logger.exception(
                        "material %s PDF page %s rasterize failed; salvaging text",
                        material_id,
                        page_number,
                    )
                    # Prefer label list over empty-cell architecture grids
                    body = salvage_sparse_layout_tables_in_markdown(page_md or "")
                    disposition = "salvage"
            else:
                body = page_md or ""

            logger.info(
                "material %s PDF page %s disposition=%s convert_failed=%s "
                "raw_chars=%s raw_tables=%s flow_normalized=%s arch_normalized=%s "
                "after_chars=%s rasterize=%s snippet=%r",
                material_id,
                page_number,
                disposition,
                convert_failed,
                raw_len,
                raw_tables,
                flow_changed,
                arch_changed,
                len(page_md or ""),
                use_image,
                _snippet(page_md if not convert_failed else ""),
            )

            chunk = f"{marker}\n{body}".strip()
            if chunk:
                parts.append(chunk)
    finally:
        doc.close()

    result = "\n\n".join(parts).strip()
    logger.info(
        "material %s PDF hybrid done pages=%s out_chars=%s",
        material_id,
        page_count,
        len(result),
    )
    return result
