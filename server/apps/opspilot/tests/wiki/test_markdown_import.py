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


def _export_style_markdown(title="作业平台", page_type="entity", body="作业平台正文"):
    return "\n".join(
        [
            "---",
            "id: 42",
            f'title: "{title}"',
            f'page_type: "{page_type}"',
            'status: "active"',
            'contribution: "human"',
            "tags:",
            '  - "蓝鲸"',
            '  - "运维"',
            "---",
            "",
            f"# {title}",
            "",
            body,
            "",
        ]
    )


@pytest.mark.django_db
def test_import_markdown_zip_creates_pages_from_front_matter():
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki.markdown_import_service import import_markdown_archive

    kb = _kb()
    content = _zip_with_markdown(
        {
            "pages/42-job.md": _export_style_markdown(
                title="作业平台",
                page_type="entity",
                body="用于执行作业和脚本。",
            ),
            "notes/readme.txt": "ignored",
        }
    )

    result = import_markdown_archive(kb, content, filename="wiki.zip", operator="admin")

    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 1
    page = KnowledgePage.objects.get(knowledge_base=kb, title="作业平台")
    assert page.page_type == "entity"
    assert page.tags == ["蓝鲸", "运维"]
    assert page.contribution == "human"
    assert page.update_method == "markdown_import"
    assert page.current_version.body == "用于执行作业和脚本。"
    assert page.current_version.change_type == "markdown_import"
    assert page.current_version.meta_snapshot["source"]["filename"] == "pages/42-job.md"


@pytest.mark.django_db
def test_import_markdown_updates_same_title_and_type_instead_of_creating_duplicate():
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki.markdown_import_service import import_markdown_archive
    from apps.opspilot.services.wiki.page_service import create_manual_page

    kb = _kb()
    existing = create_manual_page(
        kb,
        page_type="concept",
        title="CMDB",
        body="旧正文",
        tags=["旧标签"],
        created_by="u",
    )
    content = _export_style_markdown(title="CMDB", page_type="concept", body="新正文")

    result = import_markdown_archive(kb, content.encode("utf-8"), filename="cmdb.md", operator="admin")

    assert result.created == 0
    assert result.updated == 1
    assert KnowledgePage.objects.filter(knowledge_base=kb, title="CMDB", page_type="concept").count() == 1
    existing.refresh_from_db()
    assert existing.tags == ["蓝鲸", "运维"]
    assert existing.current_version.body == "新正文"
    assert existing.current_version.no == 2
    assert existing.current_version.created_by == "admin"


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
def test_import_markdown_rejects_unsupported_file_extension():
    from apps.opspilot.services.wiki.markdown_import_service import import_markdown_archive

    with pytest.raises(ValueError, match="仅支持导入 Markdown"):
        import_markdown_archive(object(), b"plain", filename="wiki.txt")


@pytest.mark.django_db
def test_import_markdown_zip_ignores_directories_and_non_markdown_entries():
    from apps.opspilot.services.wiki.markdown_import_service import import_markdown_archive

    kb = _kb()
    content = _zip_with_markdown(
        {
            "pages/": "",
            "pages/readme.txt": "ignored",
            "pages/blueking.md": "# 蓝鲸平台\n\n正文",
        }
    )

    result = import_markdown_archive(kb, content, filename="wiki.zip")

    assert result.created == 1
    assert result.skipped == 1
    assert result.pages[0]["title"] == "蓝鲸平台"


@pytest.mark.django_db
def test_import_markdown_endpoint_returns_counts_and_runs_incremental_cascade(api_client, monkeypatch):
    from apps.opspilot.models import BuildRecord, KnowledgePage
    from apps.opspilot.viewsets import wiki_kb_view

    kb = _kb()
    calls = []

    def fake_cascade(knowledge_base, page_ids, event, **kwargs):
        calls.append((knowledge_base.id, list(page_ids), event, kwargs))
        return {"status": "success", "affected_page_ids": list(page_ids)}

    monkeypatch.setattr(wiki_kb_view, "cascade", fake_cascade, raising=False)
    upload = SimpleUploadedFile(
        "wiki.zip",
        _zip_with_markdown({"pages/cmdb.md": _export_style_markdown(title="CMDB", page_type="entity")}),
        content_type="application/zip",
    )

    response = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/import_markdown/",
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["created"] == 1
    assert data["updated"] == 0
    page = KnowledgePage.objects.get(knowledge_base=kb, title="CMDB")
    assert calls == [(kb.id, [page.id], "markdown_import", {})]
    assert BuildRecord.objects.filter(
        knowledge_base=kb,
        trigger="markdown_import",
        affected_pages=[page.id],
        status="success",
    ).exists()
