"""Normalize sparse product-architecture grids into a clean module table.

Layout PDFs (e.g. 节点管理产品架构) become multi-column empty-cell tables,
often split by MarkItDown into several small tables interleaved with module
labels as plain text. Rebuild as:

| 模块 | 功能 |
"""

from __future__ import annotations

import re

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.wiki.parsing.fragmented_table import _DASH_CONTENT_RE, _content_rows, analyze_table_fragmentation, extract_markdown_tables

_CATEGORY_SUFFIX_RE = re.compile(r"(?:管理|历史|配置|中心|平台|服务)$")
# Action / qualifier tokens that mark a feature under a module, not the module title.
_FEATURE_INFIX_RE = re.compile(r"(状态|安装|查看|添加|维护|创建|详情|环境|普通|批量|Proxy|GSE|任务配置)")
_PIPE_ESCAPE_RE = re.compile(r"\|")
_ARCH_TITLE_RE = re.compile(r"产品架构|功能架构|模块架构")


def _escape_cell(text: str) -> str:
    return _PIPE_ESCAPE_RE.sub("\\|", (text or "").replace("\n", " ").strip())


def _is_category_label(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 12 or len(t) < 2:
        return False
    if _DASH_CONTENT_RE.match(t):
        return False
    if _FEATURE_INFIX_RE.search(t):
        return False
    return bool(_CATEGORY_SUFFIX_RE.search(t))


def _is_feature_label(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 24 or _is_category_label(t):
        return False
    if _DASH_CONTENT_RE.match(t):
        return False
    return True


def _looks_like_architecture_table(table_md: str) -> tuple[bool, str, dict]:
    """Return (ok, reject_reason, metrics). reject_reason empty when ok."""
    m = analyze_table_fragmentation(table_md)
    if m["col_count"] < 4 or m["nonempty_count"] < 6:
        return False, "too_few_cols_or_cells", m
    # Header+feature rows of architecture grids are often only mildly sparse.
    if m["empty_ratio"] < 0.3:
        return False, "empty_ratio_low", m
    if m["avg_len"] < 3 or m["short_ratio"] > 0.25:
        return False, "labels_look_fragmented", m
    categories = 0
    for row in _content_rows(table_md):
        for cell in row:
            if _is_category_label((cell or "").strip()):
                categories += 1
    if categories < 2:
        return False, f"category_count={categories}", m
    return True, "", m


def _row_cells(row: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for ci, cell in enumerate(row):
        text = (cell or "").strip()
        if not text or _DASH_CONTENT_RE.match(text):
            continue
        out.append((ci, text))
    return out


def _split_cats_feats(
    cells: list[tuple[int, str]],
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Dense rows are feature rows even if a label ends with 管理."""
    if len(cells) >= 4:
        return [], cells
    cats = [(ci, t) for ci, t in cells if _is_category_label(t)]
    feats = [(ci, t) for ci, t in cells if not _is_category_label(t)]
    return cats, feats


def _extract_modules(table_md: str) -> list[tuple[str, list[str]]]:
    """Return ordered (module, features) with best-effort spatial grouping."""
    rows = _content_rows(table_md)
    col_count = max((len(r) for r in rows), default=1)
    pending: list[list[object]] = []  # [col, name, features]
    finished: list[tuple[str, list[str]]] = []

    def flush_pending() -> None:
        nonlocal pending
        for _col, name, feats in pending:
            finished.append((str(name), list(feats)))  # type: ignore[arg-type]
        pending = []

    for row in rows:
        cells = _row_cells(row)
        if not cells:
            continue
        cats, feats = _split_cats_feats(cells)

        if cats and not feats:
            if pending and any(p[2] for p in pending):
                flush_pending()
            for ci, name in cats:
                if any(p[1] == name for p in pending):
                    continue
                pending.append([ci, name, []])
            continue

        if feats and not pending:
            continue

        if feats:
            if len(pending) == 1:
                pending[0][2].extend([n for _, n in feats])  # type: ignore[union-attr]
            else:
                cat_cols = [int(p[0]) for p in pending]
                col_span = max(cat_cols) - min(cat_cols)
                if col_span <= 1:
                    n = len(pending)
                    width = max(col_count, max((fi for fi, _ in feats), default=0) + 1)
                    for fi, fname in feats:
                        bucket = min(n - 1, (fi * n) // max(width, 1))
                        pending[bucket][2].append(fname)  # type: ignore[union-attr]
                else:
                    for fi, fname in feats:
                        best = min(pending, key=lambda p: abs(int(p[0]) - fi))
                        best[2].append(fname)  # type: ignore[union-attr]

    flush_pending()

    modules: list[tuple[str, list[str]]] = []
    for name, feats in finished:
        seen = set()
        uniq: list[str] = []
        for f in feats:
            if f == name or f in seen:
                continue
            seen.add(f)
            uniq.append(f)
        if uniq:
            modules.append((name, uniq))
    return modules


def _format_modules(modules: list[tuple[str, list[str]]]) -> str | None:
    if len(modules) < 2:
        return None
    lines = [
        "| 模块 | 功能 |",
        "| --- | --- |",
    ]
    for name, feats in modules:
        if not feats:
            continue
        lines.append(f"| {_escape_cell(name)} | {_escape_cell('、'.join(feats))} |")
    if len(lines) < 4:
        return None
    return "\n".join(lines)


def normalize_architecture_feature_map(table_md: str) -> str | None:
    """Return a clean module table, or None if not an architecture feature-map."""
    ok, reason, metrics = _looks_like_architecture_table(table_md)
    if not ok:
        if metrics.get("col_count", 0) >= 4 and metrics.get("empty_ratio", 0) >= 0.3 and metrics.get("nonempty_count", 0) >= 4:
            logger.info(
                "architecture normalize skip reason=%s metrics=%s",
                reason,
                {
                    "col_count": metrics.get("col_count"),
                    "nonempty": metrics.get("nonempty_count"),
                    "empty_ratio": round(float(metrics.get("empty_ratio") or 0), 3),
                    "avg_len": round(float(metrics.get("avg_len") or 0), 2),
                    "short_ratio": round(float(metrics.get("short_ratio") or 0), 3),
                },
            )
        return None
    modules = _extract_modules(table_md)
    out = _format_modules(modules)
    if not out:
        logger.info(
            "architecture normalize skip reason=modules_lt_2 extracted=%s",
            [n for n, _ in modules],
        )
        return None
    logger.info(
        "architecture normalize ok modules=%s",
        [(n, len(f)) for n, f in modules],
    )
    return out


def _iter_page_segments(page_md: str) -> list[tuple[str, str]]:
    """Split page into ('text', line) / ('table', table_md) in document order."""
    tables = extract_markdown_tables(page_md)
    if not tables:
        return [("text", line) for line in page_md.splitlines() if line.strip()]

    segments: list[tuple[str, str]] = []
    remaining = page_md
    # Replace tables with placeholders in order of appearance
    ordered = sorted(tables, key=lambda t: page_md.find(t))
    for table in ordered:
        pos = remaining.find(table)
        if pos < 0:
            continue
        before = remaining[:pos]
        for line in before.splitlines():
            if line.strip():
                segments.append(("text", line.strip()))
        segments.append(("table", table))
        remaining = remaining[pos + len(table) :]
    for line in remaining.splitlines():
        if line.strip():
            segments.append(("text", line.strip()))
    return segments


def _table_feature_labels(table_md: str) -> list[str]:
    labels: list[str] = []
    for row in _content_rows(table_md):
        for _ci, text in _row_cells(row):
            if _is_category_label(text):
                continue
            if text not in labels:
                labels.append(text)
    return labels


def _normalize_split_architecture_page(page_md: str) -> str | None:  # noqa: C901
    """Rebuild architecture pages that MarkItDown split into tables + label lines."""
    tables = extract_markdown_tables(page_md)
    if len(tables) < 2:
        return None

    segments = _iter_page_segments(page_md)
    prose_cats = [text for kind, text in segments if kind == "text" and _is_category_label(text)]
    has_title = bool(_ARCH_TITLE_RE.search(page_md or ""))
    if len(prose_cats) < 2 and not has_title:
        return None

    modules: list[tuple[str, list[str]]] = []
    pending: list[list[object]] = []  # [name, feats]

    def flush_pending() -> None:
        nonlocal pending
        for name, feats in pending:
            feat_list = list(feats)  # type: ignore[arg-type]
            if feat_list:
                modules.append((str(name), feat_list))
        pending = []

    def add_features(feats: list[str]) -> None:
        if not pending or not feats:
            return
        if len(pending) == 1:
            bucket: list[str] = pending[0][1]  # type: ignore[assignment]
            for f in feats:
                if f not in bucket:
                    bucket.append(f)
            return
        # Side-by-side modules declared as stacked labels — split features in order
        n = len(pending)
        chunk = (len(feats) + n - 1) // n
        for bi, p in enumerate(pending):
            bucket = p[1]  # type: ignore[assignment]
            for f in feats[bi * chunk : (bi + 1) * chunk]:
                if f not in bucket:
                    bucket.append(f)

    for kind, payload in segments:
        if kind == "text":
            if _ARCH_TITLE_RE.search(payload) and len(payload) <= 24:
                continue
            if _is_category_label(payload):
                if pending and any(p[1] for p in pending):
                    flush_pending()
                if any(p[0] == payload for p in pending):
                    continue
                pending.append([payload, []])
                continue
            if pending and _is_feature_label(payload):
                add_features([payload])
            continue

        extracted = _extract_modules(payload)
        if extracted and not pending:
            flush_pending()
            modules.extend(extracted)
            continue

        feats = _table_feature_labels(payload)
        if pending:
            add_features(feats)
            continue

        if extracted:
            modules.extend(extracted)
            continue

        if feats and modules:
            if len(modules) >= 2 and len(feats) >= 2:
                left, right = modules[-2], modules[-1]
                mid = (len(feats) + 1) // 2
                modules[-2] = (left[0], list(left[1]) + feats[:mid])
                modules[-1] = (right[0], list(right[1]) + feats[mid:])
            else:
                last_name, last_feats = modules[-1]
                modules[-1] = (last_name, list(last_feats) + feats)

    flush_pending()

    merged: list[tuple[str, list[str]]] = []
    index: dict = {}
    for name, feats in modules:
        if name in index:
            existing = merged[index[name]][1]
            for f in feats:
                if f not in existing:
                    existing.append(f)
        else:
            index[name] = len(merged)
            merged.append((name, list(feats)))

    out = _format_modules(merged)
    if out:
        logger.info(
            "architecture normalize split-page ok modules=%s",
            [(n, len(f)) for n, f in merged],
        )
    return out


def normalize_architecture_feature_maps_in_markdown(page_md: str) -> str:
    """Replace sparse architecture tables / split architecture pages."""
    if not (page_md or "").strip():
        return page_md or ""

    tables = extract_markdown_tables(page_md)

    # Prefer whole-page rebuild when MarkItDown shattered one architecture slide.
    if len(tables) >= 2:
        split = _normalize_split_architecture_page(page_md)
        if split:
            title_line = ""
            for line in page_md.splitlines():
                s = line.strip()
                if s and not s.startswith("|") and _ARCH_TITLE_RE.search(s):
                    title_line = s
                    break
            if title_line:
                return f"{title_line}\n\n{split}"
            return split

    result = page_md
    replaced = 0
    for table in sorted(tables, key=len, reverse=True):
        normalized = normalize_architecture_feature_map(table)
        if not normalized:
            continue
        result = result.replace(table, normalized, 1)
        replaced += 1
    if replaced:
        logger.info(
            "architecture normalize page replaced_tables=%s of %s",
            replaced,
            len(tables),
        )
    return result
