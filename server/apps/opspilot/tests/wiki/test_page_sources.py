import json

import pytest


def _kb():
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _page(kb, title="CMDB"):
    from apps.opspilot.models import KnowledgePage, PageVersion

    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type="entity",
        title=title,
        contribution="ai",
        status="active",
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body="配置平台用于管理业务资源。",
        change_type="ai_create",
        is_current=True,
    )
    page.current_version = version
    page.save(update_fields=["current_version"])
    return page


def _material(kb):
    from apps.opspilot.models import Material, MaterialVersion

    material = Material.objects.create(
        knowledge_base=kb,
        name="蓝鲸平台介绍.pptx",
        material_type="file",
        status="done",
        content_hash="hash-current",
    )
    version = MaterialVersion.objects.create(
        material=material,
        content_locator="wiki/parsed/1/2/hash-current.md",
        content_hash="hash-current",
    )
    material.current_version = version
    material.save(update_fields=["current_version"])
    return material, version


@pytest.mark.django_db
def test_page_sources_endpoint_returns_material_version_and_chunk_locator(api_client):
    from apps.opspilot.models import PageEvidence

    kb = _kb()
    page = _page(kb)
    material, version = _material(kb)
    locator = {
        "kind": "material_chunk",
        "chunk_index": 2,
        "chunk_count": 8,
        "start": 120,
        "end": 380,
        "snippet": "CMDB 是蓝鲸配置平台，负责资源模型和实例管理。",
        "content_locator": version.content_locator,
    }
    PageEvidence.objects.create(
        page=page,
        material=material,
        material_version=version,
        locator=json.dumps(locator, ensure_ascii=False),
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/sources/")

    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["page_id"] == page.id
    assert data["page_title"] == page.title
    assert len(data["sources"]) == 1
    source = data["sources"][0]
    assert source["material"]["id"] == material.id
    assert source["material"]["name"] == "蓝鲸平台介绍.pptx"
    assert source["material"]["material_type"] == "file"
    assert source["material"]["status"] == "done"
    assert source["material_version"]["id"] == version.id
    assert source["material_version"]["content_hash"] == "hash-current"
    assert source["material_version"]["content_locator"] == version.content_locator
    assert source["locator"]["chunk_index"] == 2
    assert source["locator"]["chunk_count"] == 8
    assert source["snippet"] == locator["snippet"]


@pytest.mark.django_db
def test_page_sources_endpoint_keeps_raw_locator_when_locator_is_not_json(api_client):
    from apps.opspilot.models import PageEvidence

    kb = _kb()
    page = _page(kb, "JOB")
    material, version = _material(kb)
    PageEvidence.objects.create(
        page=page,
        material=material,
        material_version=version,
        locator="legacy locator text",
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/page/{page.id}/sources/")

    assert response.status_code == 200, response.content
    source = response.json()["data"]["sources"][0]
    assert source["locator"] == {}
    assert source["locator_raw"] == "legacy locator text"
    assert source["snippet"] == ""
