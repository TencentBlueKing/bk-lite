"""Detect MarkItDown-produced fragmented / fake markdown tables.

Layout PDFs often become GFM tables where Chinese words/phrases are split
across rows, or separator rules leak as body rows. Frontend cannot repair
that; callers should rasterize the page instead.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

_TABLE_BLOCK_RE = re.compile(
    r"(?:^|\n)((?:\|[^\n]*\|(?:\n|$))+)",
    re.MULTILINE,
)
_SEP_CELL_RE = re.compile(r"^:?-{3,}:?$")
_DASH_CONTENT_RE = re.compile(r"^-{3,}$")
# Phrase likely cut mid-thought (no terminal punctuation).
_TERMINAL_PUNCT_RE = re.compile(r"[。！？；…：.!?;:）\)】」』]$")
# Common “dangling” Chinese endings when line-wrapped by PDF extractors.
_DANGLING_END_RE = re.compile(r"(?:分|配|收|查|获|操|将|的|与|及|和|或|给|把|被|从|向|对|按|以)$")


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|"):
        return []
    inner = line.strip("|")
    return [c.strip() for c in inner.split("|")]


def _is_separator_row(cells: Sequence[str]) -> bool:
    if not cells:
        return False
    return all(_SEP_CELL_RE.match(c or "") or c == "" for c in cells) and any(_SEP_CELL_RE.match(c or "") for c in cells)


def extract_markdown_tables(markdown: str) -> list[str]:
    """Return raw GFM table blocks found in markdown."""
    if not markdown:
        return []
    return [m.group(1).strip() for m in _TABLE_BLOCK_RE.finditer(markdown) if m.group(1).strip()]


def _table_rows(table_md: str) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    for line in table_md.splitlines():
        raw = line.strip()
        if not raw.startswith("|"):
            continue
        cells = _split_row(raw)
        if cells:
            rows.append((raw, cells))
    return rows


def _iter_content_cells(table_md: str) -> Iterable[str]:
    for _, cells in _table_rows(table_md):
        if _is_separator_row(cells):
            continue
        for cell in cells:
            yield cell


def _content_rows(table_md: str) -> list[list[str]]:
    out: list[list[str]] = []
    for _, cells in _table_rows(table_md):
        if _is_separator_row(cells):
            continue
        out.append(cells)
    return out


def _count_leaked_separator_rows(table_md: str) -> int:
    """GFM only needs one separator after the header; later dash-only rows are leaks."""
    seen_first_sep = False
    leaked = 0
    for _, cells in _table_rows(table_md):
        if not _is_separator_row(cells):
            continue
        if not seen_first_sep:
            seen_first_sep = True
            continue
        leaked += 1
    return leaked


def _count_hard_wraps(content_rows: Sequence[Sequence[str]]) -> tuple[int, int]:
    """Count cells that look line-wrapped into the next row (same column)."""
    wraps = 0
    candidates = 0
    for i in range(len(content_rows) - 1):
        cur = content_rows[i]
        nxt = content_rows[i + 1]
        width = max(len(cur), len(nxt))
        for col in range(width):
            a = cur[col].strip() if col < len(cur) else ""
            b = nxt[col].strip() if col < len(nxt) else ""
            if not a or not b:
                continue
            if _DASH_CONTENT_RE.match(a) or _DASH_CONTENT_RE.match(b):
                continue
            candidates += 1
            if _TERMINAL_PUNCT_RE.search(a):
                continue
            # Dangling function/cut word, or short stump continued by typical wrap head
            continued = bool(_DANGLING_END_RE.search(a) or (len(a) <= 10 and b[:1] in "作得回限员录权制护用防全志操"))
            if continued:
                wraps += 1
    return wraps, candidates


def analyze_table_fragmentation(table_md: str) -> dict:
    """Return metrics used by the heuristic (useful for tests/debugging)."""
    cells = list(_iter_content_cells(table_md))
    nonempty = [c for c in cells if c]
    content_rows = _content_rows(table_md)
    leaked_sep = _count_leaked_separator_rows(table_md)
    wrap_count, wrap_candidates = _count_hard_wraps(content_rows)

    if not nonempty:
        return {
            "cell_count": 0,
            "nonempty_count": 0,
            "avg_len": 0.0,
            "short_ratio": 0.0,
            "dash_ratio": 0.0,
            "col_count": 0,
            "leaked_sep_rows": leaked_sep,
            "wrap_count": wrap_count,
            "wrap_candidates": wrap_candidates,
            "wrap_ratio": 0.0,
            "empty_ratio": 0.0,
        }

    lengths = [len(c) for c in nonempty]
    short = sum(1 for n in lengths if n <= 2)
    dash = sum(1 for c in nonempty if _DASH_CONTENT_RE.match(c))
    col_count = max((len(r) for r in content_rows), default=0)
    empty_ratio = (len(cells) - len(nonempty)) / len(cells) if cells else 0.0
    wrap_ratio = wrap_count / wrap_candidates if wrap_candidates else 0.0

    return {
        "cell_count": len(cells),
        "nonempty_count": len(nonempty),
        "avg_len": sum(lengths) / len(lengths),
        "short_ratio": short / len(nonempty),
        "dash_ratio": dash / len(nonempty),
        "col_count": col_count,
        "leaked_sep_rows": leaked_sep,
        "wrap_count": wrap_count,
        "wrap_candidates": wrap_candidates,
        "wrap_ratio": wrap_ratio,
        "empty_ratio": empty_ratio,
    }


_SEP_LINE_RE = re.compile(r"^\|\s*[:\-]+(?:\s*\|\s*[:\-]+)+\s*\|\s*$", re.MULTILINE)
_SINGLE_CJK_LINE_RE = re.compile(r"^[\u4e00-\u9fff]$", re.MULTILINE)


def is_fragmented_table(table_md: str) -> bool:
    """True if a single GFM table looks like layout-extraction garbage."""
    m = analyze_table_fragmentation(table_md)
    if m["nonempty_count"] < 4:
        return False
    # Extra dash-only rows after the header separator (rules drawn as text)
    if m["leaked_sep_rows"] >= 1 and m["nonempty_count"] >= 4:
        return True
    # separator lines leaked as body cells
    if m["dash_ratio"] >= 0.15 and m["nonempty_count"] >= 6:
        return True
    # many columns + very short cells (vertical Chinese split)
    if m["col_count"] >= 4 and m["avg_len"] < 2.5 and m["short_ratio"] > 0.4:
        return True
    # extreme short-cell dominance even with fewer columns
    if m["col_count"] >= 3 and m["short_ratio"] > 0.5 and m["avg_len"] < 2.5:
        return True
    # Medium-bad: sentences hard-wrapped across rows (permission/flow diagrams)
    if m["col_count"] >= 3 and m["wrap_candidates"] >= 4 and m["wrap_ratio"] >= 0.35 and m["wrap_count"] >= 3:
        return True
    # Sparse grid + many wraps (empty spacer columns from layout PDF)
    if m["col_count"] >= 4 and m["empty_ratio"] >= 0.35 and m["wrap_count"] >= 2 and m["wrap_ratio"] >= 0.25:
        return True
    # Architecture / feature-map: many empty spacer cells, labels intact
    # (e.g. 节点管理产品架构) — not a data table, just a layout grid.
    if m["col_count"] >= 4 and m["empty_ratio"] >= 0.45 and m["nonempty_count"] >= 8 and m["avg_len"] >= 3 and m["short_ratio"] <= 0.2:
        return True
    return False


def is_fragmented_table_markdown(page_md: str) -> bool:
    """True if the page has fragmented tables (single block or many shards)."""
    if not (page_md or "").strip():
        return False
    tables = extract_markdown_tables(page_md)
    if not tables:
        return False
    if any(is_fragmented_table(t) for t in tables):
        return True

    # Page-level: MarkItDown often splits one layout into many tiny tables
    # interleaved with single-character lines and repeated dash rules.
    sep_lines = len(_SEP_LINE_RE.findall(page_md))
    single_cjk_lines = len(_SINGLE_CJK_LINE_RE.findall(page_md))
    nonempty: list[str] = []
    for table in tables:
        nonempty.extend(c for c in _iter_content_cells(table) if c)

    if len(tables) >= 4 and sep_lines >= 4:
        return True
    if sep_lines >= 5 and single_cjk_lines >= 3:
        return True
    if len(tables) >= 3 and single_cjk_lines >= 4:
        return True
    if len(nonempty) >= 8 and sep_lines >= 3:
        short = sum(1 for c in nonempty if len(c) <= 2)
        if short / len(nonempty) >= 0.3:
            return True
    return False


# Multi-column brochure text jammed onto one line: "…心 服务器性能 数据链路"
_JAMMED_COLUMNS_RE = re.compile(r"[\u4e00-\u9fff]{3,}\s+[\u4e00-\u9fffA-Za-z0-9/%．.]{2,}" r"(?:\s+[\u4e00-\u9fffA-Za-z0-9/%．.]{2,})+")


def _prose_content_lines(page_md: str) -> list[str]:
    """Non-table, non-heading text lines used for layout-prose quality checks."""
    lines: list[str] = []
    for raw in (page_md or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(("<!--", "|", "![", "```", ">", "- ", "* ", "+ ")):
            continue
        if s.startswith("#"):
            continue
        # skip pure markdown separators
        if re.fullmatch(r"[:\-|]+", s):
            continue
        lines.append(s)
    return lines


def is_fragmented_prose_markdown(page_md: str) -> bool:
    """True when multi-column layout text was extracted as broken prose shards."""
    lines = _prose_content_lines(page_md)
    if len(lines) < 8:
        return False

    single_cjk = sum(1 for line in lines if len(line) == 1 and "\u4e00" <= line <= "\u9fff")
    short = sum(1 for line in lines if len(line) <= 8)
    jammed = sum(1 for line in lines if _JAMMED_COLUMNS_RE.search(line))
    soft_wraps = 0
    for i in range(len(lines) - 1):
        a, b = lines[i], lines[i + 1]
        if _TERMINAL_PUNCT_RE.search(a):
            continue
        if _DASH_CONTENT_RE.match(a) or _DASH_CONTENT_RE.match(b):
            continue
        # Mid-phrase wrap / cut word across lines (代\\n理, 保\\n护)
        if _DANGLING_END_RE.search(a) and len(b) <= 40:
            soft_wraps += 1
            continue
        if len(a) <= 24 and len(b) <= 24 and not _TERMINAL_PUNCT_RE.search(b):
            if len(a) >= 4 and (b[:1] in "作得回限员录权制护用防全志操理升高机制" or len(b) <= 6):
                soft_wraps += 1

    short_ratio = short / len(lines)
    if single_cjk >= 2 and short_ratio >= 0.35:
        return True
    if jammed >= 2 and (short_ratio >= 0.25 or soft_wraps >= 2):
        return True
    if soft_wraps >= 3 and short_ratio >= 0.3:
        return True
    if len(lines) >= 12 and short_ratio >= 0.55 and (single_cjk + short) >= 8:
        return True
    return False


def should_rasterize_pdf_page(page_md: str) -> bool:
    """Whether a MarkItDown page should be replaced by a full-page image."""
    return is_fragmented_table_markdown(page_md) or is_fragmented_prose_markdown(page_md)


def salvage_sparse_layout_table(table_md: str) -> str | None:
    """Flatten a sparse architecture/feature-map table into a label list.

    Used when rasterize fails: readable labels beat an empty-cell grid.
    Character-split garbage is left untouched (caller should keep rasterize).
    """
    m = analyze_table_fragmentation(table_md)
    if m["col_count"] < 4 or m["empty_ratio"] < 0.4 or m["nonempty_count"] < 6:
        return None
    if m["avg_len"] < 3 or m["short_ratio"] > 0.25:
        return None

    labels: list[str] = []
    seen = set()
    for row in _content_rows(table_md):
        for cell in row:
            text = (cell or "").strip()
            if not text or _DASH_CONTENT_RE.match(text):
                continue
            if text in seen:
                continue
            seen.add(text)
            labels.append(text)
    if len(labels) < 4:
        return None
    return "\n".join(f"- {lab}" for lab in labels)


def salvage_sparse_layout_tables_in_markdown(page_md: str) -> str:
    """Replace sparse layout tables with label lists; leave other content as-is."""
    if not (page_md or "").strip():
        return page_md or ""
    tables = extract_markdown_tables(page_md)
    if not tables:
        return page_md
    result = page_md
    for table in sorted(tables, key=len, reverse=True):
        salvaged = salvage_sparse_layout_table(table)
        if not salvaged:
            continue
        result = result.replace(table, salvaged, 1)
    return result
