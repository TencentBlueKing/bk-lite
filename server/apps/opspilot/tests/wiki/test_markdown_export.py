import io
import zipfile

import pytest


def _kb(name="kb"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _page(kb, title, body, page_type="concept", status="active", tags=None):
    from apps.opspilot.services.wiki.page_service import create_manual_page

    page = create_manual_page(
        kb,
        page_type=page_type,
        title=title,
        body=body,
        tags=tags or [],
        created_by="u",
    )
    if page.status != status:
        page.status = status
        page.save(update_fields=["status"])
    return page


@pytest.mark.django_db
def test_export_markdown_zip_contains_active_pages_with_metadata():
    from apps.opspilot.services.wiki.markdown_export_service import build_markdown_export_zip

    kb = _kb("蓝鲸知识库")
    active = _page(kb, "CMDB/配置平台", "配置平台正文", page_type="entity", tags=["CMDB", "资源"])
    archived = _page(kb, "归档页", "旧正文", status="archived")
    source_invalid = _page(kb, "失效页", "失效正文", status="source_invalid")

    content, count = build_markdown_export_zip(kb)

    assert count == 1
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        assert names == [f"pages/{active.id}-CMDB_配置平台.md"]
        exported = archive.read(names[0]).decode("utf-8")

    assert f"id: {active.id}" in exported
    assert 'title: "CMDB/配置平台"' in exported
    assert 'page_type: "entity"' in exported
    assert 'status: "active"' in exported
    assert '- "CMDB"' in exported
    assert "# CMDB/配置平台" in exported
    assert "配置平台正文" in exported
    assert str(archived.id) not in exported
    assert str(source_invalid.id) not in exported


@pytest.mark.django_db
def test_export_markdown_endpoint_returns_zip_attachment(api_client):
    kb = _kb("kb export")
    page = _page(kb, "作业平台", "作业平台正文")

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/export_markdown/")

    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"] == f'attachment; filename="wiki-kb-{kb.id}-markdown.zip"'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [f"pages/{page.id}-作业平台.md"]
        assert "作业平台正文" in archive.read(archive.namelist()[0]).decode("utf-8")
