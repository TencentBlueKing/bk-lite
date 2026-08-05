"""Normalize MarkItDown zigzag flowcharts into a clean step table.

PDF process diagrams often become sparse multi-column tables with numbered
steps (`1. 版本打包`) scattered across columns. Rebuild as:

| 步骤 | 名称 | 说明 |
"""

from __future__ import annotations

import re

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.wiki.parsing.fragmented_table import _content_rows, analyze_table_fragmentation, extract_markdown_tables

_STEP_CELL_RE = re.compile(r"^(\d+)\.\s*(.+)$")
_PIPE_ESCAPE_RE = re.compile(r"\|")


def _escape_cell(text: str) -> str:
    return _PIPE_ESCAPE_RE.sub("\\|", (text or "").replace("\n", " ").strip())


def _join_cjk_chunks(parts: list[str]) -> str:
    text = "".join(parts)
    # Soft-join PDF mid-line cuts between CJK without inserting spaces
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)


def _looks_like_numbered_flow_table(table_md: str) -> bool:
    rows = _content_rows(table_md)
    step_cells = 0
    for row in rows:
        for cell in row:
            if _STEP_CELL_RE.match((cell or "").strip()):
                step_cells += 1
    if step_cells < 3:
        return False
    metrics = analyze_table_fragmentation(table_md)
    if metrics["col_count"] >= 5 and metrics["empty_ratio"] >= 0.25:
        return True
    if metrics["leaked_sep_rows"] >= 1:
        return True
    if metrics["wrap_count"] >= 2:
        return True
    if metrics["col_count"] >= 4 and step_cells >= 3:
        return True
    return False


def _find_steps(
    rows: list[list[str]],
) -> list[tuple[int, int, int, str]]:
    """Return (row_idx, col_idx, step_num, title)."""
    found: list[tuple[int, int, int, str]] = []
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            matched = _STEP_CELL_RE.match((cell or "").strip())
            if matched:
                found.append((ri, ci, int(matched.group(1)), matched.group(2).strip()))
    return found


def _next_step_row(rows: list[list[str]], start_row: int) -> int:
    for rj in range(start_row + 1, len(rows)):
        for cell in rows[rj]:
            if _STEP_CELL_RE.match((cell or "").strip()):
                return rj
    return len(rows)


def _extract_steps(table_md: str) -> dict[int, dict[str, object]]:
    rows = _content_rows(table_md)
    found = _find_steps(rows)
    steps: dict[int, dict[str, object]] = {}
    for ri, ci, num, title in found:
        end = _next_step_row(rows, ri)
        descs: list[str] = []
        for rj in range(ri + 1, end):
            row = rows[rj]
            taken = False
            if ci < len(row):
                cell = (row[ci] or "").strip()
                if cell and not _STEP_CELL_RE.match(cell):
                    descs.append(cell)
                    taken = True
            # Zigzag wraps often spill one column right when primary col empty
            if not taken and ci + 1 < len(row):
                cell = (row[ci + 1] or "").strip()
                if cell and not _STEP_CELL_RE.match(cell):
                    descs.append(cell)
                    taken = True
            if not taken and ci - 1 >= 0 and ci - 1 < len(row):
                cell = (row[ci - 1] or "").strip()
                if cell and not _STEP_CELL_RE.match(cell):
                    descs.append(cell)
        entry = steps.setdefault(num, {"title": title, "desc": []})
        if len(title) > len(str(entry.get("title") or "")):
            entry["title"] = title
        existing: list[str] = entry["desc"]  # type: ignore[assignment]
        for part in descs:
            if part not in existing and part != title:
                existing.append(part)
    return steps


def normalize_numbered_flow_table(table_md: str) -> str | None:
    """Return a clean step table, or None if the block is not a flow chart."""
    if not _looks_like_numbered_flow_table(table_md):
        return None
    steps = _extract_steps(table_md)
    if len(steps) < 3:
        return None
    lines = [
        "| 步骤 | 名称 | 说明 |",
        "| --- | --- | --- |",
    ]
    for num in sorted(steps):
        entry = steps[num]
        title = _escape_cell(str(entry.get("title") or ""))
        desc = _escape_cell(_join_cjk_chunks(list(entry.get("desc") or [])))  # type: ignore[arg-type]
        lines.append(f"| {num} | {title} | {desc or '--'} |")
    return "\n".join(lines)


def normalize_numbered_flow_tables_in_markdown(page_md: str) -> str:
    """Replace zigzag numbered flow tables on a page with clean step tables."""
    if not (page_md or "").strip():
        return page_md or ""

    tables = extract_markdown_tables(page_md)
    if not tables:
        return page_md

    result = page_md
    replaced = 0
    for table in sorted(tables, key=len, reverse=True):
        normalized = normalize_numbered_flow_table(table)
        if not normalized:
            continue
        result = result.replace(table, normalized, 1)
        replaced += 1
    if replaced:
        logger.info("flow normalize page replaced_tables=%s of %s", replaced, len(tables))
    return result
