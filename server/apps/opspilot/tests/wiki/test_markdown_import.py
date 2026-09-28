import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _zip_with_markdown(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_parse_markdown_without_front_matter_uses_heading_then_filename():
    from apps.opspilot.services.wiki.markdown_import_service import parse_markdown_document

    with_heading = parse_markdown_document("pages/123-fallback_name.md", "\n# 蓝鲸平台\n\n正文")
    without_heading = parse_markdown_document("pages/123-fallback_name.md", "纯正文")

    assert with_heading.title == "蓝鲸平台"
    assert with_heading.page_type == "concept"
    assert with_heading.tags == []
    assert with_heading.body == "正文"
    assert without_heading.title == "fallback name"
    assert without_heading.body == "纯正文"


def test_parse_markdown_tolerates_loose_front_matter_values_and_missing_boundary():
    from apps.opspilot.services.wiki.markdown_import_service import parse_markdown_document

    loose = parse_markdown_document(
        "loose.md",
        "\n".join(
            [
                "---",
                "",
                "title: CMDB",
                "ignored line",
                "page_type: entity",
                "tags:",
                "  - 运维",
                "---",
                "",
                "# CMDB",
                "",
                "正文",
            ]
        ),
    )
    missing_boundary = parse_markdown_document("missing.md", "---\ntitle: 未闭合\n正文")

    assert loose.title == "CMDB"
    assert loose.page_type == "entity"
    assert loose.tags == ["运维"]
    assert loose.body == "正文"
    assert missing_boundary.title == "missing"
    assert missing_boundary.body == "---\ntitle: 未闭合\n正文"


@pytest.mark.django_db
def test_legacy_import_endpoint_rejects_non_okf(api_client):
    from apps.opspilot.models import BuildRecord, KnowledgePage, WikiImportPreflight

    kb = _kb()
    upload = SimpleUploadedFile(
        "wiki.zip",
        _zip_with_markdown({"pages/cmdb.md": "# CMDB\n\n正文"}),
        content_type="application/zip",
    )

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/import_markdown/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 400, response.content
    body = response.json()
    assert body["result"] is False
    assert body["code"] == "import_format_unsupported"
    assert not KnowledgePage.objects.filter(knowledge_base=kb).exists()
    assert not BuildRecord.objects.filter(knowledge_base=kb, trigger="markdown_import").exists()
    assert not WikiImportPreflight.objects.filter(knowledge_base=kb).exists()
