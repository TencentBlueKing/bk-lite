from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph
from docxtpl import DocxTemplate
from openpyxl import load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from xlsxjinja import BookWriter

MAX_TEMPLATE_BYTES = 5 * 1024 * 1024
MAX_TEMPLATE_ENTRIES = 200
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_TEMPLATE_TAGS = 200
MAX_LOOP_DEPTH = 10
CARBONE_MARKER = re.compile(r"\{d\.")
IDENT = re.compile(r"^[A-Za-z_][\w]*$")
ATTR_PATH = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$")
FOR_TAG = re.compile(
    r"^(?:(?:tr|tc|p|r)\s+)?for\s+([A-Za-z_][\w]*)\s+in\s+(.+?)(?:\s*if\s+.+)?$",
    re.IGNORECASE,
)
ENDFOR_TAG = re.compile(r"^(?:(?:tr|tc|p|r)\s+)?endfor\b", re.IGNORECASE)
DENIED_PATH_SEGMENTS = {"password", "passwd", "secret", "token", "credential", "private_key", "cookie", "authorization"}
_MISSING = object()


class ReportTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedReportTemplate:
    format: str
    placeholders: tuple[str, ...]
    loops: tuple[str, ...]
    required_metrics: tuple[str, ...]
    sha256: str
    size: int


def _validate_zip(content: bytes, fmt: str) -> None:
    if len(content) > MAX_TEMPLATE_BYTES:
        raise ReportTemplateError("模板超过 5 MiB 限额")
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as error:
        raise ReportTemplateError(f"{fmt} 不是有效的 Office Open XML 文件") from error
    infos = archive.infolist()
    if len(infos) > MAX_TEMPLATE_ENTRIES or sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
        raise ReportTemplateError("模板解压规模超过安全限额")
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise ReportTemplateError("模板包含非法文件路径")
        lowered = name.lower()
        if "vbaproject" in lowered or lowered.startswith("xl/externallinks/"):
            raise ReportTemplateError("模板不得包含宏或外部数据连接")
        if info.compress_size and info.file_size / info.compress_size > 100:
            raise ReportTemplateError("模板包含异常压缩条目")
    for info in infos:
        if info.filename.endswith(".rels"):
            payload = archive.read(info).decode("utf-8", errors="ignore").lower()
            if 'targetmode="external"' in payload:
                raise ReportTemplateError("模板不得包含外部链接")


def _document_text(content: bytes, fmt: str) -> str:
    if fmt == "docx":
        document = Document(BytesIO(content))
        chunks: list[str] = []
        for child in document.element.body:
            tag = child.tag.split("}")[-1]
            if tag == "p":
                chunks.append(Paragraph(child, document).text)
            elif tag == "tbl":
                table = Table(child, document)
                chunks.extend(cell.text for row in table.rows for cell in row.cells)
        return "\n".join(chunks)
    if fmt == "xlsx":
        workbook = load_workbook(BytesIO(content), data_only=False, read_only=True)
        return "\n".join(str(cell.value) for sheet in workbook.worksheets for row in sheet.iter_rows() for cell in row if isinstance(cell.value, str))
    raise ReportTemplateError("只支持 docx 或 xlsx 模板")


def _expr_path(expr: str) -> str | None:
    cleaned = expr.split("|", 1)[0].strip()
    if not cleaned or not ATTR_PATH.match(cleaned):
        return None
    return cleaned


def _path_segments(path: str) -> list[str]:
    return [part for part in path.split(".") if part]


def _deny_sensitive(path: str) -> None:
    denied = sorted({segment.lower() for segment in _path_segments(path)}.intersection(DENIED_PATH_SEGMENTS))
    if denied:
        raise ReportTemplateError(f"模板不得引用敏感字段: {path}")


def _resolve_iterable(raw: str, bindings: dict[str, str]) -> str:
    path = _expr_path(raw)
    if path is None:
        raise ReportTemplateError(f"模板循环语法错误: {raw}")
    parts = _path_segments(path)
    if not parts:
        raise ReportTemplateError(f"模板循环语法错误: {raw}")
    root = parts[0]
    if root in bindings:
        return ".".join([bindings[root], *parts[1:]])
    return path


def _absolute_placeholder(path: str, bindings: dict[str, str]) -> str:
    parts = _path_segments(path)
    if not parts:
        return path
    root = parts[0]
    if root in bindings:
        return ".".join([bindings[root], *parts[1:]]) if len(parts) > 1 else bindings[root]
    return path


def parse_report_template(content: bytes, fmt: str) -> ParsedReportTemplate:
    normalized = fmt.lower().lstrip(".")
    if normalized not in {"docx", "xlsx"}:
        raise ReportTemplateError("只支持 docx 或 xlsx 模板")
    _validate_zip(content, normalized)
    text = _document_text(content, normalized)
    if CARBONE_MARKER.search(text):
        raise ReportTemplateError("模板请使用 Jinja 语法 {{ 字段 }} / {% for %}，不支持 Carbone {d.字段}")

    tokens = re.findall(r"(\{\{.*?\}\}|\{%.*?%\})", text, flags=re.DOTALL)
    if len(tokens) > MAX_TEMPLATE_TAGS:
        raise ReportTemplateError("模板占位符数量超过 200 个")

    bindings: dict[str, str] = {}
    loop_stack: list[str] = []
    loops: list[str] = []
    labels: list[str] = []

    for token in tokens:
        if token.startswith("{{"):
            path = _expr_path(token[2:-2].strip())
            if path is None:
                continue
            absolute = _absolute_placeholder(path, bindings)
            _deny_sensitive(absolute)
            labels.append(absolute)
            continue

        tag = " ".join(token[2:-2].split())
        for_match = FOR_TAG.match(tag)
        if for_match:
            loop_var = for_match.group(1)
            if not IDENT.match(loop_var):
                raise ReportTemplateError(f"模板循环变量非法: {loop_var}")
            iterable = _resolve_iterable(for_match.group(2), bindings)
            _deny_sensitive(iterable)
            if len(loop_stack) >= MAX_LOOP_DEPTH:
                raise ReportTemplateError("模板循环嵌套超过 10 层")
            if iterable not in loops:
                loops.append(iterable)
            loop_stack.append(loop_var)
            bindings[loop_var] = iterable
            continue
        if ENDFOR_TAG.match(tag):
            if not loop_stack:
                raise ReportTemplateError("模板循环缺少开始标记")
            finished = loop_stack.pop()
            bindings.pop(finished, None)

    if loop_stack:
        raise ReportTemplateError(f"模板循环缺少结束标记: {bindings.get(loop_stack[-1], loop_stack[-1])}")

    if len(loops) > 20:
        raise ReportTemplateError("模板循环数量超过 20 个")
    placeholders = tuple(dict.fromkeys(labels))
    return ParsedReportTemplate(
        format=normalized,
        placeholders=placeholders,
        loops=tuple(loops),
        required_metrics=placeholders,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


def _lookup(data: Any, parts: list[str]) -> Any:
    value = data
    for name in parts:
        if isinstance(value, list):
            value = value[0] if value else _MISSING
        if value is _MISSING:
            return _MISSING
        if not isinstance(value, dict) or name not in value:
            return _MISSING
        value = value[name]
    return value


_CATEGORY_ORDER = ["计算", "内存", "磁盘", "网络", "系统健康", "进程热点", "基础服务", "安全浅检", "更新账龄"]
_RED_FILL = PatternFill("solid", fgColor="FDEDEC")
_AMBER_FILL = PatternFill("solid", fgColor="FEF5E7")
_GREEN_FILL = PatternFill("solid", fgColor="E8F8F5")
_GRAY_FILL = PatternFill("solid", fgColor="F4F6F7")
_RED_FONT = Font(name="Calibri", size=11, bold=True, color="C0392B")
_AMBER_FONT = Font(name="Calibri", size=11, bold=True, color="B9770E")
_GREEN_FONT = Font(name="Calibri", size=11, bold=True, color="196F3D")
_GRAY_FONT = Font(name="Calibri", size=11, bold=True, color="7F8C8D")


def _display_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value in (None, "") else str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _unit_suffix(unit: str) -> str:
    if unit == "%":
        return "%"
    if unit == "days":
        return "天"
    return unit


def _threshold_line(metric: dict[str, Any], which: str) -> str:
    unit = str(metric.get("unit") or "")
    if unit == "bool":
        return "—"
    try:
        warning = float(metric.get("warning_threshold"))
        critical = float(metric.get("critical_threshold"))
    except (TypeError, ValueError):
        return "—"
    if warning == 0 and critical == 0:
        return "—"
    number = warning if which == "warning" else critical
    return f"≥{_display_number(number)}{_unit_suffix(unit)}"


def _value_text(metric: dict[str, Any]) -> str:
    unit = str(metric.get("unit") or "")
    if unit == "bool":
        return str(metric.get("detail") or "")
    suffix = _unit_suffix(unit)
    number = _display_number(metric.get("value"))
    return f"{number}{suffix}" if number else ""


def _status_text(status: str) -> str:
    return {"CRITICAL": "严重", "WARNING": "告警", "NORMAL": "正常"}.get(status, status)


def _annotate_metric(metric: dict[str, Any]) -> dict[str, Any]:
    copied = dict(metric)
    if not copied.get("display_name"):
        copied["display_name"] = copied.get("metric_name") or ""
    copied["value_text"] = _value_text(copied)
    copied["warning_line"] = _threshold_line(copied, "warning")
    copied["critical_line"] = _threshold_line(copied, "critical")
    copied["status_text"] = _status_text(str(copied.get("health_status") or ""))
    return copied


def _format_collected_at(value: Any) -> str:
    text = str(value or "").strip().replace("T", " ").replace("Z", "")
    if "+" in text:
        text = text.split("+", 1)[0]
    return text[:19]


def _metric_summary(results: list[Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        payload = item.get("data") if isinstance(item.get("data"), dict) else {}
        for metric in payload.get("metrics") or []:
            if not isinstance(metric, dict):
                continue
            key = (
                metric.get("category") or "",
                metric.get("display_name") or metric.get("metric_name") or "",
                str(metric.get("unit") or ""),
                _display_number(metric.get("warning_threshold")),
                _display_number(metric.get("critical_threshold")),
            )
            bucket = groups.setdefault(
                key,
                {"metric": metric, "critical_count": 0, "warning_count": 0, "normal_count": 0},
            )
            status = metric.get("health_status")
            if status == "CRITICAL":
                bucket["critical_count"] += 1
            elif status == "WARNING":
                bucket["warning_count"] += 1
            elif status == "NORMAL":
                bucket["normal_count"] += 1
    rows = []
    for bucket in groups.values():
        metric = bucket["metric"]
        critical = bucket["critical_count"]
        warning = bucket["warning_count"]
        rows.append(
            {
                "category": metric.get("category") or "",
                "name": metric.get("display_name") or metric.get("metric_name") or "",
                "warning_line": metric.get("warning_line") or "—",
                "critical_line": metric.get("critical_line") or "—",
                "critical_count": critical,
                "warning_count": warning,
                "normal_count": bucket["normal_count"],
                "conclusion": "需关注" if critical or warning else "健康",
            }
        )
    rows.sort(
        key=lambda row: (
            0 if row["critical_count"] else 1 if row["warning_count"] else 2,
            _CATEGORY_ORDER.index(row["category"]) if row["category"] in _CATEGORY_ORDER else len(_CATEGORY_ORDER),
            row["name"],
        )
    )
    return rows


def prepare_report_data(data: dict[str, Any]) -> dict[str, Any]:
    """Copy job results into the flat fields the health report template prints."""
    results: list[Any] = []
    collected_at = ""
    for item in list(data.get("results") or []):
        if not isinstance(item, dict):
            results.append(item)
            continue
        row = dict(item)
        payload = row.get("data")
        if not isinstance(payload, dict):
            payload = {
                "collected_at": "",
                "conclusion": str(row.get("error") or row.get("status") or ""),
                "host": {},
                "metrics": [],
            }
        copied = dict(payload)
        metrics = [_annotate_metric(metric) for metric in list(copied.get("metrics") or []) if isinstance(metric, dict)]
        copied["metrics"] = metrics
        copied["critical"] = [metric for metric in metrics if metric.get("health_status") == "CRITICAL"]
        copied["warning"] = [metric for metric in metrics if metric.get("health_status") == "WARNING"]
        copied["normal"] = [metric for metric in metrics if metric.get("health_status") == "NORMAL"]
        copied["critical_count"] = len(copied["critical"])
        copied["warning_count"] = len(copied["warning"])
        copied["normal_count"] = len(copied["normal"])
        copied["metric_count"] = len(metrics)
        if not collected_at:
            collected_at = _format_collected_at(copied.get("collected_at"))
        row["data"] = copied
        results.append(row)
    buckets = [_host_bucket(item) for item in results]
    summary = dict(data.get("summary") or {})
    summary.update(
        {
            "total": len(results),
            "succeeded": buckets.count("critical") + buckets.count("warning") + buckets.count("healthy"),
            "failed": len(results) - (buckets.count("critical") + buckets.count("warning") + buckets.count("healthy")),
            "critical_hosts": buckets.count("critical"),
            "warning_hosts": buckets.count("warning"),
            "healthy_hosts": buckets.count("healthy"),
            "collected_at": collected_at,
        }
    )
    return {**data, "results": results, "summary": summary, "metric_summary": _metric_summary(results)}


def _host_bucket(item: Any) -> str | None:
    if not isinstance(item, dict) or str(item.get("status") or "").upper() != "SUCCESS":
        return None
    payload = item.get("data") if isinstance(item.get("data"), dict) else {}
    critical = int(payload.get("critical_count") or 0)
    warning = int(payload.get("warning_count") or 0)
    if critical:
        return "critical"
    if warning:
        return "warning"
    return "healthy"


def _header_map(worksheet) -> dict[str, int]:
    headers = {}
    for cell in worksheet[1]:
        if isinstance(cell.value, str) and cell.value:
            headers[cell.value] = cell.column
    return headers


def _paint_conclusion_sheet(worksheet, headers: dict[str, int]) -> bool:
    critical_col = headers.get("严重项", headers.get("严重"))
    warning_col = headers.get("告警项", headers.get("告警"))
    conclusion_col = headers.get("结论")
    if not critical_col or not warning_col or not conclusion_col:
        return False
    critical = get_column_letter(critical_col)
    warning = get_column_letter(warning_col)
    conclusion = get_column_letter(conclusion_col)
    cell_range = f"{conclusion}2:{conclusion}{max(worksheet.max_row, 2)}"
    worksheet.conditional_formatting.add(
        cell_range,
        FormulaRule(formula=[f"${critical}2>0"], fill=_RED_FILL, font=_RED_FONT, stopIfTrue=True),
    )
    worksheet.conditional_formatting.add(
        cell_range,
        FormulaRule(formula=[f"AND(${critical}2=0,${warning}2>0)"], fill=_AMBER_FILL, font=_AMBER_FONT, stopIfTrue=True),
    )
    worksheet.conditional_formatting.add(cell_range, CellIsRule(operator="equal", formula=['"健康"'], fill=_GREEN_FILL, font=_GREEN_FONT))
    worksheet.conditional_formatting.add(cell_range, CellIsRule(operator="equal", formula=['"未采集"'], fill=_GRAY_FILL, font=_GRAY_FONT))
    last = get_column_letter(worksheet.max_column)
    worksheet.auto_filter.ref = f"A1:{last}{max(worksheet.max_row, 1)}"
    worksheet.freeze_panes = "A2"
    return True


def _paint_status_column(worksheet, headers: dict[str, int]) -> bool:
    status_col = headers.get("健康状态") or headers.get("状态")
    if not status_col:
        return False
    column = get_column_letter(status_col)
    cell_range = f"{column}2:{column}{max(worksheet.max_row, 2)}"
    worksheet.conditional_formatting.add(cell_range, CellIsRule(operator="equal", formula=['"严重"'], fill=_RED_FILL, font=_RED_FONT))
    worksheet.conditional_formatting.add(cell_range, CellIsRule(operator="equal", formula=['"告警"'], fill=_AMBER_FILL, font=_AMBER_FONT))
    worksheet.conditional_formatting.add(cell_range, CellIsRule(operator="equal", formula=['"正常"'], fill=_GREEN_FILL, font=_GREEN_FONT))
    worksheet.conditional_formatting.add(cell_range, CellIsRule(operator="equal", formula=['"未采集"'], fill=_GRAY_FILL, font=_GRAY_FONT))
    last = get_column_letter(worksheet.max_column)
    worksheet.auto_filter.ref = f"A1:{last}{max(worksheet.max_row, 1)}"
    worksheet.freeze_panes = "A2"
    return True


def _coerce_integer_cells(worksheet) -> None:
    for row in worksheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and re.fullmatch(r"-?\d+", cell.value):
                cell.value = int(cell.value)


def _paint_health_report(content: bytes) -> bytes:
    workbook = load_workbook(BytesIO(content))
    painted = False
    for worksheet in workbook.worksheets:
        headers = _header_map(worksheet)
        painted = _paint_conclusion_sheet(worksheet, headers) or painted
        painted = _paint_status_column(worksheet, headers) or painted
    if not painted:
        return content
    for worksheet in workbook.worksheets:
        worksheet.sheet_view.view = "normal"
        if not worksheet.sheet_view.zoomScale:
            worksheet.sheet_view.zoomScale = 120
        worksheet.sheet_properties.pageSetUpPr.fitToPage = False
        _coerce_integer_cells(worksheet)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


_STATUS_FILLS = {"严重": "FDEDEC", "告警": "FEF5E7", "正常": "E8F8F5", "未采集": "F4F6F7"}
_STATUS_FONTS = {"严重": "C0392B", "告警": "B9770E", "正常": "196F3D", "未采集": "7F8C8D"}


def _shade_docx_cell(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for child in list(tc_pr):
        if child.tag == qn("w:shd"):
            tc_pr.remove(child)
    tc_pr.append(tc_pr.makeelement(qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): color}))


def _paint_health_docx(content: bytes) -> bytes:
    document = Document(BytesIO(content))
    painted = False
    for table in document.tables:
        if not table.rows:
            continue
        headers = [cell.text.strip() for cell in table.rows[0].cells]
        status_col = next((index for index, header in enumerate(headers) if header in {"状态", "健康状态"}), None)
        if status_col is None:
            continue
        for row in table.rows[1:]:
            cell = row.cells[status_col]
            label = cell.text.strip()
            color = _STATUS_FILLS.get(label)
            if not color:
                continue
            _shade_docx_cell(cell, color)
            font_color = _STATUS_FONTS[label]
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.name = "Calibri"
                    run.font.size = Pt(8)
                    run.font.color.rgb = RGBColor.from_string(font_color)
            painted = True
    if not painted:
        return content
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def missing_template_fields(parsed: ParsedReportTemplate, data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for label in parsed.placeholders:
        parts = _path_segments(label)
        if not parts:
            continue
        if _lookup(data, parts) is _MISSING:
            missing.append(label)
    return missing


def _render_docx(content: bytes, data: dict[str, Any]) -> bytes:
    template = DocxTemplate(BytesIO(content))
    try:
        template.render(data)
    except Exception as error:  # noqa: BLE001 - surface engine failures as template errors
        raise ReportTemplateError(f"Word 模板渲染失败: {error}") from error
    output = BytesIO()
    template.save(output)
    rendered = output.getvalue()
    if not rendered:
        raise ReportTemplateError("Word 模板渲染返回了空文档")
    return rendered


def _render_xlsx(content: bytes, data: dict[str, Any]) -> bytes:
    try:
        writer = BookWriter(BytesIO(content))
        sheet_names = [state.name for state in writer.sheet_resource_map.sheet_state_list]
        payloads = [
            {
                **data,
                "tpl_name": sheet_name,
                "sheet_name": sheet_name,
            }
            for sheet_name in sheet_names
        ] or [data]
        writer.render_book(payloads)
        output = BytesIO()
        writer.save(output)
    except Exception as error:  # noqa: BLE001 - surface engine failures as template errors
        raise ReportTemplateError(f"Excel 模板渲染失败: {error}") from error
    rendered = output.getvalue()
    if not rendered:
        raise ReportTemplateError("Excel 模板渲染返回了空文档")
    return rendered


def render_report(content: bytes, fmt: str, data: dict[str, Any]) -> bytes:
    parsed = parse_report_template(content, fmt)
    if not isinstance(data, dict):
        raise ReportTemplateError("文档数据必须是 JSON 对象")
    prepared = prepare_report_data(data)
    if parsed.format == "docx":
        return _paint_health_docx(_render_docx(content, prepared))
    return _paint_health_report(_render_xlsx(content, prepared))
