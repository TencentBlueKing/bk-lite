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
    assert "openpyxl" not in names
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


def test_build_attachment_bytes_csv_has_utf8_bom():
    payload = build_attachment_bytes("name,count\nweb,2", "csv")
    assert payload.startswith(b"\xef\xbb\xbf")
    assert payload.decode("utf-8-sig") == "name,count\nweb,2"


@pytest.mark.django_db
def test_refresh_attachment_download_urls_resigns_expired_history_link(monkeypatch):
    import json

    from django.core.files.base import ContentFile
    from django.core.signing import SignatureExpired

    from apps.opspilot.models import WorkflowAttachmentAsset
    from apps.opspilot.services import workflow_attachment_service as attachment_service

    asset = WorkflowAttachmentAsset.objects.create(
        execution_id="exec-history",
        attachment_id="att-history",
        filename="子网地址使用率.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file=ContentFile(b"xlsx", name="subnet.xlsx"),
    )
    stale = attachment_service.build_signed_attachment_download_url(asset)
    token = stale.rsplit("/download/", 1)[1].rstrip("/")
    stored = json.dumps(
        [{"type": "TOOL_CALL_RESULT", "content": json.dumps({"file_url": stale, "filename": asset.filename})}],
        ensure_ascii=False,
    )
    monkeypatch.setattr(attachment_service, "workflow_attachment_download_max_age", lambda: -1)
    with pytest.raises(SignatureExpired):
        attachment_service.resolve_signed_attachment_token(token)

    refreshed = attachment_service.refresh_attachment_download_urls(stored)
    fresh_token = refreshed.split("/download/", 1)[1].split("/", 1)[0]
    monkeypatch.setattr(attachment_service, "workflow_attachment_download_max_age", lambda: 24 * 60 * 60)
    resolved = attachment_service.resolve_signed_attachment_token(fresh_token)
    assert resolved is not None
    assert resolved.id == asset.id


def test_build_attachment_bytes_xlsx_keeps_header_row():
    from io import BytesIO

    from openpyxl import load_workbook

    payload = build_attachment_bytes("name,count\nweb,2", "xlsx")
    sheet = load_workbook(BytesIO(payload)).active
    assert [cell.value for cell in next(sheet.iter_rows(max_row=1))] == ["name", "count"]
    assert [cell.value for cell in next(sheet.iter_rows(min_row=2, max_row=2))] == ["web", "2"]
