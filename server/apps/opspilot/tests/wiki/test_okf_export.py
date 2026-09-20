import hashlib
import io
import zipfile
from pathlib import PurePosixPath

import pytest
import yaml

from apps.opspilot.services.wiki.markdown_export_service import QuotaExceededError
from apps.opspilot.services.wiki.markdown_import_service import split_front_matter_block
from apps.opspilot.services.wiki.okf_export_service import DEFAULT_MAX_OKF_EXPORT_BYTES, build_okf_export_zip, posix_relpath, zip_root_name
from apps.opspilot.tests.wiki.test_okf_import import PNG_BYTES, _add_root_directories, _zip_bytes

_UTF8_FLAG = 0x800


def _patch_page_media(monkeypatch):
    saved = {}

    class Storage:
        def exists(self, path):
            return path in saved

        def save(self, path, content):
            saved[path] = content.read() if hasattr(content, "read") else content
            return path

        def delete(self, path):
            saved.pop(path, None)

        def url(self, path):
            return f"https://cdn/{path}"

        def open(self, path, mode="rb"):
            if path not in saved:
                raise FileNotFoundError(path)
            return io.BytesIO(saved[path])

        def listdir(self, bucket):
            return [(name, None) for name in saved]

        @property
        def bucket(self):
            return "munchkin-private"

    from apps.opspilot.services.wiki import parsed_media_service

    monkeypatch.setattr(parsed_media_service, "_MEDIA_STORAGE", Storage())
    return saved


def _parse_md(text):
    raw, body = split_front_matter_block(text)
    loaded = yaml.safe_load(raw or "") or {}
    return loaded, body


def _open_okf_zip(content):
    archive = zipfile.ZipFile(io.BytesIO(content))
    names = archive.namelist()
    root = zip_root_name_from_members(names)
    return archive, names, root


def zip_root_name_from_members(names):
    tops = {PurePosixPath(name).parts[0] for name in names if name.strip("/")}
    assert len(tops) == 1
    return next(iter(tops))


def test_posix_relpath_from_nested_page():
    assert posix_relpath("assets/ab.png", "guides") == "../assets/ab.png"
    assert posix_relpath("assets/ab.png", "") == "assets/ab.png"
    assert posix_relpath("assets/ab.png", "a/b") == "../../assets/ab.png"


@pytest.mark.django_db
def test_export_okf_endpoint_returns_zip_attachment(api_client, wiki_factory):
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base(name="导出库")
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    page = create_manual_page(kb, page_type="concept", title="作业平台", body="作业平台正文", created_by="u")

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/export_okf/")

    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"] == f'attachment; filename="wiki-kb-{kb.id}-okf.zip"'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert "manifest.json" not in names
    assert any(name.endswith("/index.md") for name in names)
    assert any(str(page.id) in name and name.endswith(".md") for name in names)


@pytest.mark.django_db
def test_export_okf_endpoint_without_generation_returns_409(api_client, wiki_factory):
    kb = wiki_factory.knowledge_base()
    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/export_okf/")
    assert response.status_code == 409
    payload = response.json()
    assert payload["result"] is False
    assert payload["code"]


@pytest.mark.django_db
def test_export_okf_endpoint_rejects_cross_team(api_client, wiki_factory):
    foreign = wiki_factory.knowledge_base(name="foreign-okf", team=[2])
    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{foreign.id}/export_okf/")
    assert response.status_code == 403, response.content


@pytest.mark.django_db
def test_export_okf_endpoint_quota_returns_400(api_client, wiki_factory, monkeypatch):
    from apps.opspilot.viewsets import wiki_kb_view

    kb = wiki_factory.knowledge_base()

    def boom(_kb):
        raise QuotaExceededError("max_bytes", "导出内容超过 200 MB 上限,已停止")

    monkeypatch.setattr(wiki_kb_view, "build_okf_export_zip", boom)
    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/export_okf/")
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "max_bytes"
    assert "200" in payload["message"]


@pytest.mark.django_db
def test_export_okf_max_pages_raises(wiki_factory):
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    create_manual_page(kb, page_type="concept", title="页一", body="a", created_by="u")
    create_manual_page(kb, page_type="concept", title="页二", body="b", created_by="u")
    with pytest.raises(QuotaExceededError) as exc:
        build_okf_export_zip(kb, max_pages=1)
    assert exc.value.code == "max_pages"


@pytest.mark.django_db
def test_export_okf_max_bytes_raises(wiki_factory):
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    create_manual_page(kb, page_type="concept", title="大页", body="x" * 200, created_by="u")
    with pytest.raises(QuotaExceededError) as exc:
        build_okf_export_zip(kb, max_bytes=10)
    assert exc.value.code == "max_bytes"


@pytest.mark.django_db
def test_export_markdown_endpoint_unchanged(api_client, wiki_factory):
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    page = create_manual_page(kb, page_type="concept", title="作业平台", body="作业平台正文", created_by="u")
    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/knowledge_base/{kb.id}/export_markdown/")
    assert response.status_code == 200, response.content
    assert response["Content-Disposition"] == f'attachment; filename="wiki-kb-{kb.id}-markdown.zip"'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert "manifest.json" in names
    assert f"pages/unclassified/{page.id}-作业平台.md" in names


@pytest.mark.django_db
def test_export_okf_native_page_uses_display_directory_and_synthesizes_generated(wiki_factory):
    from apps.opspilot.models import WikiDirectory
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    kb = wiki_factory.knowledge_base(name="运维知识库")
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    _add_root_directories(kb, ["运维手册"])
    directory = WikiDirectory.objects.get(knowledge_base=kb, name="运维手册", status="active")
    page = create_manual_page(
        kb,
        page_type="concept",
        title="重启指南",
        body="先停服务。",
        created_by="u",
        directory_id=directory.pk,
        tags=["okf:unverified", "runbook"],
    )

    content, stats = build_okf_export_zip(kb)
    assert stats["pages"] == 1
    archive, names, root = _open_okf_zip(content)
    with archive:
        assert root == zip_root_name("运维知识库")
        assert f"{root}/index.md" in names
        assert f"{root}/log.md" in names
        assert "manifest.json" not in names
        page_names = [name for name in names if name.endswith(".md") and not name.endswith(("/index.md", "/log.md"))]
        assert page_names == [f"{root}/运维手册/{page.id}-重启指南.md"]
        assert all("dir_" not in name for name in names)
        for info in archive.infolist():
            assert info.flag_bits & _UTF8_FLAG
        index = archive.read(f"{root}/index.md").decode("utf-8")
        front, _body = _parse_md(index)
        assert front["okf_version"] == "0.2"
        exported = archive.read(page_names[0]).decode("utf-8")
        meta, body = _parse_md(exported)
    assert meta["type"] == "concept"
    assert meta["title"] == "重启指南"
    assert meta["tags"] == ["runbook"]
    assert meta["generated"]["by"] == "process:opspilot-llm-wiki/1"
    assert "verified" not in meta
    assert "先停服务。" in body
    assert "okf:" not in str(meta.get("tags") or [])


@pytest.mark.django_db
def test_export_okf_keeps_broken_locator_and_succeeds(wiki_factory, monkeypatch):
    from apps.opspilot.services.wiki.okf_import_service import page_media_locator
    from apps.opspilot.services.wiki.page_service import create_manual_page
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    _patch_page_media(monkeypatch)
    kb = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    locator = page_media_locator(kb.pk, "deadbeefdeadbeefdeadbeefdeadbeef", ".png")
    create_manual_page(
        kb,
        page_type="concept",
        title="裂图页",
        body=f'可见 ![x]({locator}) 与 <img src="{locator}">',
        created_by="u",
    )
    content, stats = build_okf_export_zip(kb)
    assert stats["pages"] == 1
    assert stats["images"] == 0
    archive, names, _root = _open_okf_zip(content)
    with archive:
        assert not any("/assets/" in name for name in names)
        page_name = next(name for name in names if name.endswith(".md") and not name.endswith(("index.md", "log.md")))
        exported = archive.read(page_name).decode("utf-8")
    assert f"![x]({locator})" in exported
    assert f'<img src="{locator}">' in exported


@pytest.mark.django_db(transaction=True)
def test_export_okf_round_trip_preflight_and_visible_images(wiki_factory, monkeypatch):
    from apps.opspilot.models import KnowledgePage
    from apps.opspilot.services.wiki.markdown_import_governance_service import (
        execute_markdown_import,
        inspect_markdown_archive,
        preflight_markdown_import,
    )
    from apps.opspilot.services.wiki.okf_import_service import page_media_locator
    from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base

    saved = _patch_page_media(monkeypatch)
    kb = wiki_factory.knowledge_base(name="round-trip")
    bootstrap_knowledge_base(kb, operator="admin")
    kb.refresh_from_db()
    digest = hashlib.sha256(PNG_BYTES).hexdigest()
    locator = page_media_locator(kb.pk, digest, ".png")
    original = _zip_bytes(
        {
            "index.md": '---\nokf_version: "0.2"\n---\n',
            "log.md": "# log\n",
            "tables/orders.md": "\n".join(
                [
                    "---",
                    "type: entity",
                    "title: Customer Orders",
                    "tags: [sales]",
                    "---",
                    "",
                    "One row per order.",
                ]
            ),
            "metrics/revenue.md": "\n".join(
                [
                    "---",
                    "type: Metric",
                    "title: Revenue",
                    "description: Recognized revenue for a fiscal year.",
                    "tags: [finance]",
                    "generated:",
                    "  by: reference_agent/gemini-2.5-flash",
                    "  at: '2026-07-10T22:48:04+00:00'",
                    "verified: { by: human:jsmith@acme, at: 2026-07-01T09:00:00Z }",
                    "---",
                    "",
                    "Computed from [orders](/tables/orders.md).",
                    "![chart](../assets/x.png)",
                ]
            ),
            "assets/x.png": PNG_BYTES,
        }
    )
    preflight = preflight_markdown_import(
        kb,
        original,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf", "create_directories_from_folders": True},
    )
    execute_markdown_import(kb, preflight["token"], original, filename="okf.zip", actor="admin")
    assert locator in saved
    pages = {page.title: page for page in KnowledgePage.objects.filter(knowledge_base=kb)}
    assert locator in pages["Revenue"].current_version.body
    generated_at = pages["Revenue"].current_version.meta_snapshot["okf"]["generated"]["at"]

    content, stats = build_okf_export_zip(kb)
    assert stats["pages"] == 2
    assert stats["images"] == 1

    archive, names, root = _open_okf_zip(content)
    with archive:
        asset_name = next(name for name in names if "/assets/" in name)
        assert archive.read(asset_name) == PNG_BYTES
        revenue_path = f"{root}/metrics/revenue.md"
        orders_path = f"{root}/tables/orders.md"
        revenue = archive.read(revenue_path).decode("utf-8")
        orders = archive.read(orders_path).decode("utf-8")
        index = archive.read(f"{root}/index.md").decode("utf-8")
        for info in archive.infolist():
            assert info.flag_bits & _UTF8_FLAG

    revenue_meta, revenue_body = _parse_md(revenue)
    orders_meta, _orders_body = _parse_md(orders)
    index_meta, _index_body = _parse_md(index)
    assert index_meta["okf_version"] == "0.2"
    assert revenue_meta["type"] == "Metric"
    assert orders_meta["type"] == "entity"
    assert revenue_meta["title"] == "Revenue"
    assert revenue_meta["generated"]["by"] == "reference_agent/gemini-2.5-flash"
    assert revenue_meta["generated"]["at"] == generated_at
    assert revenue_meta["verified"]
    assert "okf:" not in str(revenue_meta.get("tags") or [])
    assert "finance" in (revenue_meta.get("tags") or [])
    assert "[orders](/tables/orders.md)" in revenue_body
    assert "[[" not in revenue_body
    relative = posix_relpath(asset_name.split("/", 1)[1], "metrics")
    assert f"![chart]({relative})" in revenue_body
    assert locator not in revenue_body

    inspected = inspect_markdown_archive(content, "okf.zip", import_format="okf")
    assert inspected.okf_version == "0.2"
    types = {document["okf_type"] for document in inspected.documents}
    assert types == {"Metric", "entity"}
    assert len(inspected.documents) == 2
    again = preflight_markdown_import(
        kb,
        content,
        filename="okf.zip",
        actor="admin",
        options={"import_format": "okf"},
    )
    assert again["preview"]["okf"]["images"]["count"] == 1
    assert again["preview"]["counts"]["total"] == 2


def test_default_okf_quota_is_200mb():
    assert DEFAULT_MAX_OKF_EXPORT_BYTES == 200 * 1024 * 1024
