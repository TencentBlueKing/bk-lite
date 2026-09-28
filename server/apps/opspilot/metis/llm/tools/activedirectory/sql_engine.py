"""只读 SQL 引擎（对齐 CData RunQuery 声明的子句子集）。

支持: SELECT / FROM / INNER JOIN / LEFT JOIN / WHERE / GROUP BY / ORDER BY / LIMIT / OFFSET
标识符可用反引号 ` 引用。拒绝非 SELECT 与写操作。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Sequence

from apps.opspilot.metis.llm.tools.activedirectory.schema import TableDef, get_table

_IDENT = r"(?:`[^`]+`|\"[^\"]+\"|\[[^\]]+\]|[A-Za-z_][A-Za-z0-9_]*)"
_SELECT_RE = re.compile(r"^\s*SELECT\s+", re.IGNORECASE | re.DOTALL)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|REPLACE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)


@dataclass
class JoinClause:
    join_type: str  # INNER | LEFT
    table: str
    alias: str | None
    left: str
    right: str


@dataclass
class ParsedSelect:
    columns: list[str]  # raw select list items; may be * or table.col or expressions
    from_table: str
    from_alias: str | None = None
    joins: list[JoinClause] = field(default_factory=list)
    where: str | None = None
    group_by: list[str] = field(default_factory=list)
    order_by: list[tuple[str, str]] = field(default_factory=list)  # (expr, ASC|DESC)
    limit: int | None = None
    offset: int = 0


def _strip_ident(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and ((token[0] == token[-1] == "`") or (token[0] == token[-1] == '"') or (token[0] == "[" and token[-1] == "]")):
        return token[1:-1]
    return token


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quote:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            in_quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and text.startswith(sep, i):
            parts.append("".join(buf).strip())
            buf = []
            i += len(sep)
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _find_keyword(sql: str, keyword: str) -> int:
    """在顶层查找关键字位置（忽略引号/括号内）。"""
    pattern = re.compile(rf"\b{keyword}\b", re.IGNORECASE)
    depth = 0
    in_quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            in_quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0:
            m = pattern.match(sql, i)
            if m:
                return m.start()
        i += 1
    return -1


def _split_clauses(sql: str) -> dict[str, str]:
    """按顶层关键字切分 SELECT 子句。JOIN 留在 FROM 段内。"""
    markers = [
        ("SELECT", re.compile(r"\bSELECT\b", re.IGNORECASE)),
        ("FROM", re.compile(r"\bFROM\b", re.IGNORECASE)),
        ("WHERE", re.compile(r"\bWHERE\b", re.IGNORECASE)),
        ("GROUP BY", re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)),
        ("ORDER BY", re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)),
        ("LIMIT", re.compile(r"\bLIMIT\b", re.IGNORECASE)),
        ("OFFSET", re.compile(r"\bOFFSET\b", re.IGNORECASE)),
    ]
    found: list[tuple[str, int, int]] = []
    for key, cre in markers:
        for m in cre.finditer(sql):
            # 跳过括号/引号内：用简单深度扫描确认
            if _is_top_level_index(sql, m.start()):
                found.append((key, m.start(), m.end()))
                break
    found.sort(key=lambda x: x[1])
    clauses: dict[str, str] = {}
    for idx, (key, _start, content_start) in enumerate(found):
        stop = found[idx + 1][1] if idx + 1 < len(found) else len(sql)
        clauses[key] = sql[content_start:stop].strip()
    return clauses


def _is_top_level_index(sql: str, index: int) -> bool:
    depth = 0
    in_quote: str | None = None
    i = 0
    while i < index:
        ch = sql[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            in_quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    return depth == 0 and in_quote is None


def _parse_table_ref(text: str) -> tuple[str, str | None]:
    text = text.strip()
    # t AS a / t a
    m = re.match(rf"^({_IDENT})(?:\s+(?:AS\s+)?({_IDENT}))?$", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid table reference: {text}")
    return _strip_ident(m.group(1)), _strip_ident(m.group(2)) if m.group(2) else None


def _parse_joins(from_segment: str) -> tuple[str, str | None, list[JoinClause]]:
    """解析 FROM t [JOIN ...]"""
    join_pat = re.compile(r"\b((?:INNER|LEFT(?:\s+OUTER)?)\s+JOIN)\b", re.IGNORECASE)
    parts = []
    last = 0
    for m in join_pat.finditer(from_segment):
        parts.append(("BASE" if last == 0 else "PREV", from_segment[last : m.start()].strip()))
        parts.append(("JOINTYPE", m.group(1)))
        last = m.end()
    parts.append(("TAIL", from_segment[last:].strip()))

    if not parts:
        table, alias = _parse_table_ref(from_segment)
        return table, alias, []

    # Rebuild: BASE table, then sequences of JOINTYPE + "table ON a = b"
    base_text = parts[0][1]
    table, alias = _parse_table_ref(base_text)
    joins: list[JoinClause] = []
    i = 1
    while i < len(parts):
        if parts[i][0] != "JOINTYPE":
            i += 1
            continue
        jtype_raw = parts[i][1].upper()
        jtype = "LEFT" if jtype_raw.startswith("LEFT") else "INNER"
        i += 1
        if i >= len(parts):
            raise ValueError("JOIN missing table")
        chunk = parts[i][1]
        on_m = re.search(r"\bON\b", chunk, re.IGNORECASE)
        if not on_m:
            raise ValueError("JOIN requires ON condition")
        right_ref = chunk[: on_m.start()].strip()
        on_expr = chunk[on_m.end() :].strip()
        rt, ra = _parse_table_ref(right_ref)
        eq = re.match(rf"^({_IDENT}(?:\.{_IDENT})?)\s*=\s*({_IDENT}(?:\.{_IDENT})?)$", on_expr, re.IGNORECASE)
        if not eq:
            raise ValueError(f"Only equality JOIN ON supported: {on_expr}")
        joins.append(
            JoinClause(
                join_type=jtype,
                table=rt,
                alias=ra,
                left=_strip_ident_path(eq.group(1)),
                right=_strip_ident_path(eq.group(2)),
            )
        )
        i += 1
    return table, alias, joins


def _strip_ident_path(path: str) -> str:
    return ".".join(_strip_ident(p) for p in path.split("."))


def parse_select(sql: str) -> ParsedSelect:
    raw = (sql or "").strip().rstrip(";")
    if not raw:
        raise ValueError("Empty SQL")
    if not _SELECT_RE.match(raw):
        raise ValueError("Only SELECT statements are supported")
    if _FORBIDDEN.search(raw):
        raise ValueError("Write/DDL statements are not allowed")

    clauses = _split_clauses(raw)
    if "SELECT" not in clauses or "FROM" not in clauses:
        raise ValueError("SELECT ... FROM is required")

    select_list = _split_top_level(clauses["SELECT"])
    from_table, from_alias, joins = _parse_joins(clauses["FROM"])

    order_by: list[tuple[str, str]] = []
    if "ORDER BY" in clauses:
        for item in _split_top_level(clauses["ORDER BY"]):
            m = re.match(r"^(.+?)(?:\s+(ASC|DESC))?$", item.strip(), re.IGNORECASE)
            if not m:
                raise ValueError(f"Invalid ORDER BY: {item}")
            order_by.append((_strip_ident_path(m.group(1).strip()), (m.group(2) or "ASC").upper()))

    group_by = [_strip_ident_path(x) for x in _split_top_level(clauses["GROUP BY"])] if "GROUP BY" in clauses else []

    limit = None
    offset = 0
    if "LIMIT" in clauses:
        lim = clauses["LIMIT"].strip()
        # LIMIT n / LIMIT n OFFSET m / LIMIT m, n (mysql style)
        m = re.match(r"^(\d+)\s*(?:,\s*(\d+))?$", lim)
        if m and m.group(2) is not None:
            offset = int(m.group(1))
            limit = int(m.group(2))
        elif m:
            limit = int(m.group(1))
        else:
            m2 = re.match(r"^(\d+)\s+OFFSET\s+(\d+)$", lim, re.IGNORECASE)
            if not m2:
                raise ValueError(f"Invalid LIMIT: {lim}")
            limit = int(m2.group(1))
            offset = int(m2.group(2))
    if "OFFSET" in clauses:
        offset = int(clauses["OFFSET"].strip())

    return ParsedSelect(
        columns=select_list,
        from_table=from_table,
        from_alias=from_alias,
        joins=joins,
        where=clauses.get("WHERE"),
        group_by=group_by,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )


Row = Dict[str, Any]


def _flatten_ldap_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        if len(value) == 1:
            return _flatten_ldap_value(value[0])
        return [_flatten_ldap_value(v) for v in value]
    if hasattr(value, "value"):
        return _flatten_ldap_value(value.value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def fetch_table_rows(
    *,
    table: TableDef,
    base_dn: str,
    searcher: Callable[[str, str, Sequence[str], int], list[Any]],
    size_limit: int = 1000,
) -> list[Row]:
    attrs = [c.ldap_attr for c in table.columns]
    entries = searcher(base_dn, table.object_filter, attrs, size_limit)
    rows: list[Row] = []
    for entry in entries:
        attrs_dict: dict[str, Any] = {}
        if isinstance(entry, dict):
            attrs_dict = entry
        else:
            raw_attrs = getattr(entry, "entry_attributes_as_dict", None)
            if callable(raw_attrs):
                try:
                    raw_attrs = raw_attrs()
                except TypeError:
                    raw_attrs = None
            if isinstance(raw_attrs, dict):
                attrs_dict = raw_attrs
            else:
                # 兼容简单 stub：直接读实例属性
                attrs_dict = {c.ldap_attr: getattr(entry, c.ldap_attr, None) for c in table.columns}
        row: Row = {}
        for col in table.columns:
            row[col.name] = _flatten_ldap_value(attrs_dict.get(col.ldap_attr))
        rows.append(row)
    return rows


def _qualify_rows(rows: list[Row], table_name: str, alias: str | None) -> list[Row]:
    prefix = alias or table_name
    out = []
    for row in rows:
        q: Row = {}
        for k, v in row.items():
            q[k] = v
            q[f"{prefix}.{k}"] = v
            q[f"{table_name}.{k}"] = v
        out.append(q)
    return out


def _resolve_path_value(row: Row, path: str) -> Any:
    key = _strip_ident_path(path)
    if key in row:
        return row[key]
    # bare column
    bare = key.split(".")[-1]
    if bare in row:
        return row[bare]
    # case-insensitive
    lower_map = {str(k).lower(): v for k, v in row.items()}
    if key.lower() in lower_map:
        return lower_map[key.lower()]
    if bare.lower() in lower_map:
        return lower_map[bare.lower()]
    return None


def _cmp(left: Any, op: str, right: Any) -> bool:
    if op in {"=", "=="}:
        return str(left) == str(right) if left is not None and right is not None else left == right
    if op in {"<>", "!="}:
        return not _cmp(left, "=", right)
    try:
        lf, rf = float(left), float(right)
        if op == "<":
            return lf < rf
        if op == "<=":
            return lf <= rf
        if op == ">":
            return lf > rf
        if op == ">=":
            return lf >= rf
    except (TypeError, ValueError):
        ls, rs = str(left), str(right)
        if op == "<":
            return ls < rs
        if op == "<=":
            return ls <= rs
        if op == ">":
            return ls > rs
        if op == ">=":
            return ls >= rs
    return False


def _like(value: Any, pattern: str) -> bool:
    text = "" if value is None else str(value)
    # SQL LIKE: % → .*, _ → . ; re.escape 不会转义 %/_，须逐字符处理
    parts: list[str] = []
    for ch in pattern:
        if ch == "%":
            parts.append(".*")
        elif ch == "_":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.fullmatch("".join(parts), text, re.IGNORECASE) is not None


def _eval_where(expr: str, row: Row) -> bool:
    expr = expr.strip()
    # handle parentheses recursively
    while True:
        m = re.search(r"\(([^()]+)\)", expr)
        if not m:
            break
        inner = _eval_where(m.group(1), row)
        expr = expr[: m.start()] + ("TRUE" if inner else "FALSE") + expr[m.end() :]

    # OR
    or_parts = _split_top_level(expr, " OR ")
    if len(or_parts) == 1:
        or_parts = _split_top_level(expr, " or ")
    if len(or_parts) > 1:
        return any(_eval_where(p, row) for p in or_parts)

    and_parts = _split_top_level(expr, " AND ")
    if len(and_parts) == 1:
        and_parts = _split_top_level(expr, " and ")
    if len(and_parts) > 1:
        return all(_eval_where(p, row) for p in and_parts)

    atom = expr.strip()
    if atom.upper() == "TRUE":
        return True
    if atom.upper() == "FALSE":
        return False

    m = re.match(rf"^({_IDENT}(?:\.{_IDENT})?)\s+IS\s+(NOT\s+)?NULL$", atom, re.IGNORECASE)
    if m:
        val = _resolve_path_value(row, m.group(1))
        is_null = val is None or val == ""
        return (not is_null) if m.group(2) else is_null

    m = re.match(rf"^({_IDENT}(?:\.{_IDENT})?)\s+LIKE\s+('([^']*)'|\"([^\"]*)\")$", atom, re.IGNORECASE)
    if m:
        return _like(_resolve_path_value(row, m.group(1)), m.group(3) if m.group(3) is not None else m.group(4))

    m = re.match(rf"^({_IDENT}(?:\.{_IDENT})?)\s*(=|<>|!=|<=|>=|<|>)\s*(.+)$", atom, re.IGNORECASE)
    if not m:
        raise ValueError(f"Unsupported WHERE expression: {atom}")
    left = _resolve_path_value(row, m.group(1))
    op = m.group(2)
    right_raw = m.group(3).strip()
    if (right_raw.startswith("'") and right_raw.endswith("'")) or (right_raw.startswith('"') and right_raw.endswith('"')):
        right: Any = right_raw[1:-1]
    elif re.match(rf"^{_IDENT}(?:\.{_IDENT})?$", right_raw):
        right = _resolve_path_value(row, right_raw)
    else:
        try:
            right = float(right_raw) if "." in right_raw else int(right_raw)
        except ValueError:
            right = right_raw
    return _cmp(left, op, right)


def _join_rows(left_rows: list[Row], right_rows: list[Row], join: JoinClause) -> list[Row]:
    out: list[Row] = []
    for lrow in left_rows:
        lval = _resolve_path_value(lrow, join.left)
        matched = False
        for rrow in right_rows:
            rval = _resolve_path_value(rrow, join.right)
            # also try swapped if aliases differ
            if lval is None and rval is None:
                ok = False
            else:
                ok = str(lval) == str(rval)
            if ok:
                merged = dict(lrow)
                merged.update(rrow)
                out.append(merged)
                matched = True
        if not matched and join.join_type == "LEFT":
            out.append(dict(lrow))
    return out


def _aggregate_rows(rows: list[Row], group_by: list[str], select_cols: list[str]) -> tuple[list[str], list[Row]]:
    if not group_by:
        return select_cols, rows

    buckets: dict[tuple[Any, ...], list[Row]] = {}
    for row in rows:
        key = tuple(_resolve_path_value(row, g) for g in group_by)
        buckets.setdefault(key, []).append(row)

    out_cols: list[str] = []
    for col in select_cols:
        out_cols.append(_output_col_name(col))

    result: list[Row] = []
    for key, group_rows in buckets.items():
        sample = group_rows[0]
        row_out: Row = {}
        for col in select_cols:
            name = _output_col_name(col)
            expr = re.sub(r"\s+AS\s+(`[^`]+`|\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)$", "", col.strip(), flags=re.IGNORECASE).strip()
            agg = re.match(r"^(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(.+?)\s*\)$", expr, re.IGNORECASE)
            if agg:
                func = agg.group(1).upper()
                arg = agg.group(2).strip()
                if arg == "*":
                    if func == "COUNT":
                        row_out[name] = len(group_rows)
                    else:
                        raise ValueError(f"{func}(*) is not supported")
                else:
                    vals = [_resolve_path_value(r, arg) for r in group_rows]
                    nums = []
                    for v in vals:
                        if v is None or v == "":
                            continue
                        try:
                            nums.append(float(v))
                        except (TypeError, ValueError):
                            nums.append(v)
                    if func == "COUNT":
                        row_out[name] = len([v for v in vals if v is not None and v != ""])
                    elif func == "SUM":
                        row_out[name] = sum(x for x in nums if isinstance(x, (int, float)))
                    elif func == "AVG":
                        nums_f = [x for x in nums if isinstance(x, (int, float))]
                        row_out[name] = (sum(nums_f) / len(nums_f)) if nums_f else None
                    elif func == "MIN":
                        row_out[name] = min(nums) if nums else None
                    elif func == "MAX":
                        row_out[name] = max(nums) if nums else None
            else:
                row_out[name] = _resolve_path_value(sample, expr)
        result.append(row_out)
    return out_cols, result


def _output_col_name(col: str) -> str:
    col = col.strip()
    m = re.match(r"^.+\s+AS\s+(`[^`]+`|\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)$", col, re.IGNORECASE)
    if m:
        return _strip_ident(m.group(1))
    agg = re.match(r"^(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(.+?)\s*\)$", col, re.IGNORECASE)
    if agg:
        return f"{agg.group(1).upper()}({agg.group(2).strip()})"
    return _strip_ident_path(col)


def _project(rows: list[Row], select_cols: list[str], available_tables: dict[str, TableDef]) -> tuple[list[str], list[Row]]:
    # expand *
    expanded: list[str] = []
    for col in select_cols:
        c = col.strip()
        if c == "*":
            # prefer unqualified unique columns from first table defs order
            seen = set()
            for table in available_tables.values():
                for cdef in table.columns:
                    if cdef.name not in seen:
                        expanded.append(cdef.name)
                        seen.add(cdef.name)
            continue
        m = re.match(rf"^({_IDENT})\.\*$", c)
        if m:
            tname = _strip_ident(m.group(1))
            table = None
            for name, tdef in available_tables.items():
                if name.lower() == tname.lower():
                    table = tdef
                    break
            if table is None:
                # alias?
                expanded.append(c)
            else:
                expanded.extend([f"{tname}.{cdef.name}" for cdef in table.columns])
            continue
        expanded.append(c)

    if any(re.match(r"^(COUNT|SUM|AVG|MIN|MAX)\s*\(", c.strip(), re.IGNORECASE) for c in expanded):
        # aggregation without GROUP BY → one bucket
        return _aggregate_rows(rows, [], expanded)

    out_cols = [_output_col_name(c) for c in expanded]
    projected: list[Row] = []
    for row in rows:
        item: Row = {}
        for raw_col, out_name in zip(expanded, out_cols):
            # strip AS
            expr = re.sub(r"\s+AS\s+(`[^`]+`|\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)$", "", raw_col.strip(), flags=re.IGNORECASE)
            item[out_name] = _resolve_path_value(row, expr)
        projected.append(item)
    return out_cols, projected


def execute_select(
    sql: str,
    *,
    base_dn: str,
    searcher: Callable[[str, str, Sequence[str], int], list[Any]],
    fetch_limit: int = 1000,
) -> tuple[list[str], list[Row]]:
    parsed = parse_select(sql)
    base_table = get_table(parsed.from_table)
    tables: dict[str, TableDef] = {base_table.name: base_table}
    alias_map: dict[str, str] = {}
    if parsed.from_alias:
        alias_map[parsed.from_alias] = base_table.name

    left_rows = _qualify_rows(
        fetch_table_rows(table=base_table, base_dn=base_dn, searcher=searcher, size_limit=fetch_limit),
        base_table.name,
        parsed.from_alias,
    )

    for join in parsed.joins:
        right_table = get_table(join.table)
        tables[right_table.name] = right_table
        if join.alias:
            alias_map[join.alias] = right_table.name
        right_rows = _qualify_rows(
            fetch_table_rows(table=right_table, base_dn=base_dn, searcher=searcher, size_limit=fetch_limit),
            right_table.name,
            join.alias,
        )
        # normalize join keys to include aliases
        left_rows = _join_rows(left_rows, right_rows, join)

    if parsed.where:
        left_rows = [r for r in left_rows if _eval_where(parsed.where, r)]

    if parsed.group_by:
        # force aggregate projection
        cols, left_rows = _aggregate_rows(left_rows, parsed.group_by, parsed.columns)
    else:
        cols, left_rows = _project(left_rows, parsed.columns, tables)

    if parsed.order_by:
        for expr, direction in reversed(parsed.order_by):
            reverse = direction == "DESC"
            out_name = _output_col_name(expr)

            def sort_key(row, e=expr, n=out_name):
                val = row.get(n)
                if val is None:
                    val = _resolve_path_value(row, e)
                return (val is None, str(val) if val is not None else "")

            left_rows.sort(key=sort_key, reverse=reverse)

    if parsed.offset:
        left_rows = left_rows[parsed.offset :]
    if parsed.limit is not None:
        left_rows = left_rows[: parsed.limit]
    return cols, left_rows
