"""migrate / Django setup 不得加载 python-docx、reportlab；附件生成仍可用。"""

import ast
from pathlib import Path

import pytest

from apps.opspilot.services.workflow_attachment_service import build_attachment_bytes

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
    assert "docx" not in names
    assert not any(name == "reportlab" or name.startswith("reportlab.") for name in names)


def test_build_attachment_bytes_md_keeps_utf8():
    assert build_attachment_bytes("# 报告", "md", title="日报") == "# 报告".encode("utf-8")


def test_build_attachment_bytes_docx_is_office_zip():
    payload = build_attachment_bytes("第一行\n第二行", "docx", title="巡检")
    assert payload[:2] == b"PK"
    assert len(payload) > 1000


def test_build_attachment_bytes_pdf_has_header():
    payload = build_attachment_bytes("hello <tag> & value", "pdf", title="Inspection")
    assert payload.startswith(b"%PDF")
    assert len(payload) > 200
