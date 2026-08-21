#!/usr/bin/env python3
"""Inventory Python logging smells for BK-Lite.

This is a deterministic candidate collector, not a correctness oracle. Every
finding still requires control-flow and operational-context review.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


LOG_LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal"}
ERROR_LEVELS = {"warning", "warn", "error", "exception", "critical", "fatal"}
TERMINAL_LEVELS = {"error", "exception", "critical", "fatal"}
RAW_NAMES = {"body", "config", "content", "data", "kwargs", "output", "payload", "request", "response", "result"}
SENSITIVE_PARTS = {"authorization", "cookie", "credential", "password", "passwd", "private_key", "secret", "token"}
SAFE_SENSITIVE_SUFFIXES = (
    "_configured",
    "_enabled",
    "_exists",
    "_expire_time",
    "_expiration_time",
    "_id",
    "_max_usage",
    "_present",
    "_provided",
    "_set",
    "_ttl",
)
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "migrate_patch",
    "migrations",
    "node_modules",
    "venv",
}


RULES = {
    "L001": ("P2", "formatted-message", "动态日志模板会破坏聚合并产生急切求值"),
    "L002": ("P2", "manual-traceback", "手工格式化 traceback 易重复、难结构化"),
    "L003": ("P1", "missing-traceback", "except 中的失败日志没有 traceback 候选"),
    "L004": ("P2", "log-then-raise", "异常在本层记录后继续抛出，可能被上层重复记录"),
    "L005": ("P1", "swallowed-exception", "异常可能被默认值或 pass 静默吞掉"),
    "L006": ("P2", "multi-error-burst", "同一 except 中发出多条终态错误日志"),
    "L007": ("P2", "info-in-loop", "循环内 INFO 可能产生高频噪声"),
    "L008": ("P3", "decorative-log", "装饰性日志不提供可查询的操作证据"),
    "L009": ("P1", "raw-or-unbounded", "完整 payload/result/response 等对象可能泄露或放大日志"),
    "L010": ("P0", "sensitive-data", "敏感命名对象可能进入日志"),
    "L011": ("P2", "print-bypass", "print 绕过日志级别、上下文和路由"),
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    priority: str
    category: str
    path: str
    line: int
    message: str
    evidence: str


def _is_logger_call(node: ast.AST) -> tuple[ast.Call, str] | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    level = node.func.attr.lower()
    if level not in LOG_LEVELS:
        return None
    target = ast.unparse(node.func.value).lower()
    if "log" not in target:
        return None
    return node, level


def _all_logger_calls(nodes: Sequence[ast.stmt]) -> list[tuple[ast.Call, str]]:
    calls: list[tuple[ast.Call, str]] = []
    for statement in nodes:
        for candidate in ast.walk(statement):
            info = _is_logger_call(candidate)
            if info:
                calls.append(info)
    return sorted(calls, key=lambda item: (item[0].lineno, item[0].col_offset))


def _has_truthy_exc_info(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg != "exc_info":
            continue
        if isinstance(keyword.value, ast.Constant):
            return bool(keyword.value.value)
        return True
    return False


def _direct_value_names(node: ast.AST) -> set[str]:
    """Return names whose values are emitted, not merely used to compute a field.

    ``self.config.servers`` emits ``servers`` rather than the whole ``config``;
    ``bool(token)`` and ``len(payload)`` emit bounded metadata rather than the
    underlying value. Keeping that distinction avoids high-severity noise.
    """

    if isinstance(node, ast.Name):
        return {node.id.lower()}
    if isinstance(node, ast.Attribute):
        return {node.attr.lower()}
    if isinstance(node, (ast.FormattedValue, ast.Starred)):
        return _direct_value_names(node.value)
    if isinstance(node, ast.JoinedStr):
        return {
            name
            for value in node.values
            if isinstance(value, ast.FormattedValue)
            for name in _direct_value_names(value)
        }
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return {name for value in node.elts for name in _direct_value_names(value)}
    if isinstance(node, ast.Dict):
        return {
            name
            for value in node.values
            for name in _direct_value_names(value)
        }
    if isinstance(node, ast.BinOp):
        return _direct_value_names(node.left) | _direct_value_names(node.right)
    if isinstance(node, ast.Call):
        function_name = ""
        if isinstance(node.func, ast.Name):
            function_name = node.func.id.lower()
        elif isinstance(node.func, ast.Attribute):
            function_name = node.func.attr.lower()

        if function_name in {"bool", "len"}:
            return set()
        if function_name in {"get", "getitem"}:
            return set()
        return {
            name
            for value in [*node.args, *(keyword.value for keyword in node.keywords)]
            for name in _direct_value_names(value)
        }
    return set()


def _logged_value_names(call: ast.Call) -> set[str]:
    names: set[str] = set()
    if call.args and _is_formatted_message(call.args[0]):
        names.update(_direct_value_names(call.args[0]))
    for argument in call.args[1:]:
        names.update(_direct_value_names(argument))
    for keyword in call.keywords:
        if keyword.arg in {"exc_info", "stack_info"}:
            continue
        if keyword.arg:
            names.add(keyword.arg.lower())
        names.update(_direct_value_names(keyword.value))
    return names


def _contains_name(names: Iterable[str], parts: set[str]) -> set[str]:
    matches: set[str] = set()
    for name in names:
        if name.endswith(SAFE_SENSITIVE_SUFFIXES):
            continue
        for part in parts:
            if name == part or name.startswith(f"{part}_") or name.endswith(f"_{part}"):
                matches.add(name)
    return matches


def _is_default_return(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {None, False}
    if isinstance(value, ast.Dict):
        return not value.keys
    return isinstance(value, (ast.List, ast.Set, ast.Tuple)) and not value.elts


def _is_formatted_message(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"


def _static_message(call: ast.Call) -> str | None:
    if not call.args:
        return None
    message = call.args[0]
    if isinstance(message, ast.Constant) and isinstance(message.value, str):
        return message.value
    if isinstance(message, ast.BinOp) and isinstance(message.op, ast.Mult):
        if isinstance(message.left, ast.Constant) and isinstance(message.left.value, str):
            if isinstance(message.right, ast.Constant) and isinstance(message.right.value, int):
                return message.left.value * message.right.value
    return None


def _is_decorative(message: str) -> bool:
    stripped = message.strip()
    if len(stripped) >= 3 and set(stripped) <= set("=-_*#~ "):
        return True
    symbol_count = sum(unicodedata.category(char) == "So" for char in stripped)
    return symbol_count > 0 and len(stripped) < 100


class LogVisitor(ast.NodeVisitor):
    def __init__(self, *, path: str, source: str) -> None:
        self.path = path
        self.source = source
        self.findings: list[Finding] = []
        self._except_stack: list[ast.ExceptHandler] = []
        self._missing_traceback_handlers: set[int] = set()
        self._loop_depth = 0

    def _add(self, rule_id: str, node: ast.AST, detail: str | None = None) -> None:
        priority, category, default_message = RULES[rule_id]
        evidence = ast.get_source_segment(self.source, node) or ast.unparse(node)
        evidence = " ".join(evidence.split())
        if len(evidence) > 240:
            evidence = f"{evidence[:237]}..."
        self.findings.append(
            Finding(
                rule_id=rule_id,
                priority=priority,
                category=category,
                path=self.path,
                line=getattr(node, "lineno", 1),
                message=detail or default_message,
                evidence=evidence,
            )
        )

    def visit_For(self, node: ast.For) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_While(self, node: ast.While) -> None:
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        calls = _all_logger_calls(node.body)
        terminal_calls = [(call, level) for call, level in calls if level in TERMINAL_LEVELS]
        raises = [child for statement in node.body for child in ast.walk(statement) if isinstance(child, ast.Raise)]

        if len(terminal_calls) > 1:
            self._add(
                "L006",
                terminal_calls[0][0],
                f"同一 except 中发现 {len(terminal_calls)} 条 ERROR/EXCEPTION 候选",
            )

        if calls and raises:
            first_raise_line = min(item.lineno for item in raises)
            prior_logs = [call for call, level in calls if level in ERROR_LEVELS and call.lineno < first_raise_line]
            if prior_logs:
                self._add("L004", prior_logs[0])

        has_raise = bool(raises)
        swallowed = [child for statement in node.body for child in ast.walk(statement) if isinstance(child, ast.Pass)]
        swallowed.extend(
            child
            for statement in node.body
            for child in ast.walk(statement)
            if isinstance(child, ast.Return) and _is_default_return(child)
        )
        if swallowed and not has_raise:
            self._add("L005", swallowed[0])

        self._except_stack.append(node)
        self.generic_visit(node)
        self._except_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        info = _is_logger_call(node)
        if info:
            call, level = info
            if call.args and _is_formatted_message(call.args[0]):
                self._add("L001", call)

            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and ast.unparse(child.func) == "traceback.format_exc"
                for child in ast.walk(call)
            ):
                self._add("L002", call)

            if self._except_stack and level in ERROR_LEVELS and level != "exception" and not _has_truthy_exc_info(call):
                handler_id = id(self._except_stack[-1])
                if handler_id not in self._missing_traceback_handlers:
                    self._add("L003", call)
                    self._missing_traceback_handlers.add(handler_id)

            if self._loop_depth and level == "info":
                self._add("L007", call)

            message = _static_message(call)
            if message is not None and _is_decorative(message):
                self._add("L008", call)

            names = _logged_value_names(call)
            sensitive = _contains_name(names, SENSITIVE_PARTS)
            if sensitive:
                self._add("L010", call, f"日志参数包含敏感命名候选: {', '.join(sorted(sensitive))}")

            raw = _contains_name(names, RAW_NAMES)
            if raw and level in {"info", "warning", "warn", "error", "exception", "critical", "fatal"}:
                self._add("L009", call, f"非 DEBUG 日志包含原始/无界对象候选: {', '.join(sorted(raw))}")

        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self._add("L011", node)

        self.generic_visit(node)


def _is_excluded(path: Path, *, include_tests: bool) -> bool:
    if any(part in DEFAULT_EXCLUDED_DIRS for part in path.parts):
        return True
    if include_tests:
        return False
    return path.name.startswith("test_") or path.name.endswith("_test.py") or "tests" in path.parts


def _iter_python_files(paths: Sequence[Path], *, include_tests: bool) -> Iterable[Path]:
    seen: set[Path] = set()
    for path in paths:
        candidates = [path] if path.is_file() else path.rglob("*.py")
        for candidate in candidates:
            if candidate.suffix != ".py" or _is_excluded(candidate, include_tests=include_tests):
                continue
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield candidate


def scan_file(path: Path, *, display_path: str | None = None) -> tuple[list[Finding], str | None]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return [], str(exc)
    visitor = LogVisitor(path=display_path or str(path), source=source)
    visitor.visit(tree)
    return visitor.findings, None


def scan_paths(paths: Sequence[Path], *, root: Path, include_tests: bool) -> tuple[list[Finding], list[dict[str, str]]]:
    findings: list[Finding] = []
    errors: list[dict[str, str]] = []
    for path in sorted(_iter_python_files(paths, include_tests=include_tests)):
        try:
            display_path = str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            display_path = str(path)
        file_findings, error = scan_file(path, display_path=display_path)
        findings.extend(file_findings)
        if error:
            errors.append({"path": display_path, "error": error})
    findings.sort(key=lambda item: (item.path, item.line, item.rule_id))
    return findings, errors


def _summary(findings: Sequence[Finding]) -> dict[str, object]:
    by_rule = Counter(item.rule_id for item in findings)
    by_priority = Counter(item.priority for item in findings)
    return {
        "total": len(findings),
        "by_priority": dict(sorted(by_priority.items())),
        "by_rule": dict(sorted(by_rule.items())),
    }


def render_json(
    findings: Sequence[Finding], errors: Sequence[dict[str, str]], *, summary_only: bool = False
) -> str:
    payload: dict[str, object] = {"summary": _summary(findings), "parse_errors": list(errors)}
    if not summary_only:
        payload["findings"] = [asdict(item) for item in findings]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_markdown(
    findings: Sequence[Finding], errors: Sequence[dict[str, str]], *, summary_only: bool = False
) -> str:
    summary = _summary(findings)
    lines = [
        "# Logging Candidate Inventory",
        "",
        "> 这是机械候选清单，不是审计结论；必须结合调用链和运行频率人工复核。",
        "",
        f"- Total: {summary['total']}",
        f"- By priority: {json.dumps(summary['by_priority'], ensure_ascii=False)}",
        f"- By rule: {json.dumps(summary['by_rule'], ensure_ascii=False)}",
    ]
    if not summary_only:
        lines.extend(
            [
                "",
                "| Rule | Priority | Category | Location | Why | Evidence |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in findings:
            evidence = item.evidence.replace("|", "\\|").replace("`", "'")
            message = item.message.replace("|", "\\|")
            lines.append(
                f"| {item.rule_id} | {item.priority} | {item.category} | "
                f"`{item.path}:{item.line}` | {message} | `{evidence}` |"
            )
    if errors:
        lines.extend(["", "## Parse errors", ""])
        lines.extend(f"- `{item['path']}`: {item['error']}" for item in errors)
    return "\n".join(lines)


def render_text(
    findings: Sequence[Finding], errors: Sequence[dict[str, str]], *, summary_only: bool = False
) -> str:
    lines = [json.dumps(_summary(findings), ensure_ascii=False)]
    if not summary_only:
        lines.extend(
            f"{item.rule_id}\t{item.priority}\t{item.path}:{item.line}\t{item.category}\t{item.message}"
            for item in findings
        )
    lines.extend(f"PARSE_ERROR\t{item['path']}\t{item['error']}" for item in errors)
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["server", "agents/stargazer"], help="Files or directories to scan")
    parser.add_argument("--root", default=".", help="Repository root used for relative paths")
    parser.add_argument("--format", choices=("json", "markdown", "text"), default="text")
    parser.add_argument("--summary-only", action="store_true", help="Print counts and parse errors without findings")
    parser.add_argument("--output", help="Optional output path; stdout is used by default")
    parser.add_argument("--include-tests", action="store_true", help="Include test files and test directories")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root)
    paths = [Path(item) for item in args.paths]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        print(f"Missing scan paths: {', '.join(missing)}", file=sys.stderr)
        return 2

    findings, errors = scan_paths(paths, root=root, include_tests=args.include_tests)
    if args.format == "json":
        output = render_json(findings, errors, summary_only=args.summary_only)
    elif args.format == "markdown":
        output = render_markdown(findings, errors, summary_only=args.summary_only)
    else:
        output = render_text(findings, errors, summary_only=args.summary_only)

    if args.output:
        Path(args.output).write_text(f"{output}\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
