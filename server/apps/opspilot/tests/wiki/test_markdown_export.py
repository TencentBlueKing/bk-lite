import io
import zipfile

import pytest

from apps.opspilot.models import WikiKnowledgeBase
from apps.opspilot.services.wiki.page_service import create_manual_page
from apps.opspilot.tests.wiki.factories import create_unsafe_legacy_page_without_version


def _kb(name="kb"):
    return WikiKnowledgeBase.objects.create(name=name, team=[1])


def _page(kb, title, body, page_type="concept", tags=None):
    return create_manual_page(
        kb,
        page_type=page_type,
        title=title,
        body=body,
        tags=tags or [],
        created_by="u",
    )


def _inactive_page(kb, title, _body, *, status):
    return create_unsafe_legacy_page_without_version(
        knowledge_base=kb,
        title=title,
        status=status,
        contribution="ai",
        page_type="concept",
    )


@pytest.mark.django_db
def test_export_markdown_zip_contains_active_pages_with_metadata():
    from apps.opspilot.services.wiki.markdown_export_service import build_markdown_export_zip

    kb = _kb("蓝鲸知识库")
    active = _page(kb, "CMDB/配置平台", "配置平台正文", page_type="entity", tags=["CMDB", "资源"])
    archived = _inactive_page(kb, "归档页", "旧正文", status="archived")
    source_invalid = _inactive_page(kb, "失效页", "失效正文", status="source_invalid")

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
def test_export_markdown_endpoint_removed(api_client):
    kb = _kb("kb export")
    _page(kb, "作业平台", "作业平台正文")

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/export_markdown/")

    assert response.status_code == 404, response.content
