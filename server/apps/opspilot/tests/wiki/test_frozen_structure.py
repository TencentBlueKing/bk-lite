import logging
from copy import deepcopy

import pytest
from rest_framework.test import APIClient

from apps.opspilot.models import WikiDirectory, WikiKnowledgeBase
from apps.opspilot.services.wiki.frozen_structure_migration_service import (
    ensure_frozen_structure,
    ensure_frozen_structure_if_needed,
    frozen_structure_missing,
    introduction_from_purpose,
)
from apps.opspilot.services.wiki.purpose_schema_service import FROZEN_ROOT_KEYS
from apps.opspilot.services.wiki.structure_service import (
    StructureServiceError,
    bootstrap_knowledge_base,
    get_structure,
    save_structure,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _bootstrap(wiki_factory, **overrides):
    knowledge_base = wiki_factory.knowledge_base(**overrides)
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    return knowledge_base


def _payload(knowledge_base):
    current = get_structure(knowledge_base)
    return {
        "structure_version": current["structure_revision"]["version"],
        "base_generation_id": current["active_generation"]["id"],
        "structure": {
            "format_version": 1,
            "page_types": list(current["structure"]["page_types"]),
            "directories": [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]],
        },
    }


def test_bootstrap_creates_six_frozen_roots_and_unclassified(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    directories = list(WikiDirectory.objects.filter(knowledge_base=knowledge_base, status="active"))
    names = {item.name for item in directories}
    assert {"待归类", "实体", "概念", "待研究问题", "对比", "综合", "来源"} <= names
    frozen = [item for item in directories if item.key in FROZEN_ROOT_KEYS]
    assert {item.origin for item in frozen} == {"system"}
    source = next(item for item in frozen if item.name == "来源")
    assert source.accepts_pages is False
    page_types = get_structure(knowledge_base)["structure"]["page_types"]
    assert "source" not in page_types
    assert {"entity", "concept", "query", "comparison", "synthesis"} <= set(page_types)


def test_save_structure_rejects_frozen_root_rename_and_omission(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    entity = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="实体")
    renamed = _payload(knowledge_base)
    for item in renamed["structure"]["directories"]:
        if item["id"] == entity.pk:
            item["name"] = "实体库"
    with pytest.raises(StructureServiceError) as captured:
        save_structure(knowledge_base, renamed, operator="admin")
    assert captured.value.code == "frozen_directory_invariant"

    omitted = _payload(knowledge_base)
    omitted["structure"]["directories"] = [item for item in omitted["structure"]["directories"] if item["id"] != entity.pk]
    with pytest.raises(StructureServiceError) as captured:
        save_structure(knowledge_base, omitted, operator="admin")
    assert captured.value.code == "system_directory_omission_forbidden"


def test_save_structure_allows_manual_root_sibling(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    payload = _payload(knowledge_base)
    payload["structure"]["directories"].append(
        {
            "kind": "new",
            "client_ref": "manual-ops",
            "name": "运维专题",
            "description": "",
            "order": 80,
            "rules": {"allowed_page_types": ["concept"], "default_for_page_types": []},
            "parent": None,
        }
    )
    save_structure(knowledge_base, payload, operator="admin")
    created = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="运维专题")
    assert created.origin == "manual"
    assert created.parent_id is None


def test_introduction_from_purpose_skips_heading():
    assert introduction_from_purpose("## Purpose\n\n**收录运维问答**\n", "kb") == "收录运维问答"
    assert introduction_from_purpose("# 只有标题", "示例库") == "示例库"


def test_stock_kb_gains_frozen_roots_and_keeps_old_directories(wiki_factory, caplog):
    knowledge_base = wiki_factory.knowledge_base(introduction="", purpose_md="## Purpose\n\n收录故障处置")
    WikiDirectory.objects.create(
        knowledge_base=knowledge_base,
        key="__unclassified__",
        name="待归类",
        description="系统待归类目录",
        origin="system",
        status="active",
        accepts_pages=True,
        sort_order=0,
    )
    WikiDirectory.objects.create(
        knowledge_base=knowledge_base,
        key="schema_question",
        name="问答",
        description="旧模板目录",
        origin="schema",
        status="active",
        accepts_pages=True,
        sort_order=10,
    )

    caplog.set_level(logging.INFO, logger="opspilot")
    result = ensure_frozen_structure(knowledge_base, operator="migrator")
    knowledge_base.refresh_from_db()
    assert result["changed"] is True
    assert any(
        rec.msg == "wiki_frozen_structure_applied kb_id=%s" and rec.args == (knowledge_base.pk,) for rec in caplog.records
    )
    assert knowledge_base.introduction == "收录故障处置"
    names = set(WikiDirectory.objects.filter(knowledge_base=knowledge_base, status="active").values_list("name", flat=True))
    assert {"实体", "概念", "来源", "问答", "待归类"} <= names
    leftover = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="问答")
    assert leftover.origin == "schema"
    assert leftover.key == "schema_question"


def _hide_frozen_root(knowledge_base, key="schema_source"):
    # 不物理删除：bootstrap 后 overview 等对目录是 PROTECT。
    # origin 改成 manual，避免激活修订时多出一个非法 system 目录。
    WikiDirectory.objects.filter(knowledge_base=knowledge_base, key=key).update(
        key=f"retired_{key}",
        name="已退役来源",
        origin="manual",
        accepts_pages=True,
    )


def test_directory_tree_backfills_missing_frozen_roots(api_client, wiki_factory):
    knowledge_base = _bootstrap(wiki_factory, introduction="收录故障处置")
    _hide_frozen_root(knowledge_base)
    assert frozen_structure_missing(knowledge_base) is True

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/directory/tree/?knowledge_base={knowledge_base.id}")
    assert response.status_code == 200, response.content
    names = {item["name"] for item in response.json()["data"]["directories"]}
    assert {"实体", "概念", "来源", "待归类"} <= names
    assert frozen_structure_missing(knowledge_base) is False
    assert ensure_frozen_structure_if_needed(knowledge_base, operator="migrator")["changed"] is False


def test_ensure_keeps_roots_when_revision_activation_fails(wiki_factory, monkeypatch, caplog):
    knowledge_base = _bootstrap(wiki_factory, introduction="收录故障处置")
    _hide_frozen_root(knowledge_base)

    def _boom(*args, **kwargs):
        raise StructureServiceError("generation_incomplete", "generation 完整性校验失败")

    monkeypatch.setattr(
        "apps.opspilot.services.wiki.frozen_structure_migration_service.save_structure",
        _boom,
    )
    caplog.set_level(logging.ERROR, logger="opspilot")
    result = ensure_frozen_structure(knowledge_base, operator="migrator")
    assert result["changed"] is True
    assert WikiDirectory.objects.filter(knowledge_base=knowledge_base, key="schema_source").exists()
    assert any(rec.msg == "wiki_frozen_structure_revision_failed kb_id=%s" and rec.args == (knowledge_base.pk,) for rec in caplog.records)


def test_ensure_activates_revision_when_frozen_root_was_missing(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory, introduction="收录故障处置")
    _hide_frozen_root(knowledge_base)
    result = ensure_frozen_structure(knowledge_base, operator="migrator")
    assert result["changed"] is True
    knowledge_base.refresh_from_db()
    snapshot_keys = {
        item["key"]
        for item in get_structure(knowledge_base)["structure"]["directories"]
        if item.get("parent") is None
    }
    assert FROZEN_ROOT_KEYS <= snapshot_keys
    assert WikiDirectory.objects.filter(knowledge_base=knowledge_base, key="schema_source", origin="system").exists()


def test_kb_api_requires_introduction_and_hides_purpose_fields(api_client):
    base = "/api/v1/opspilot/wiki_mgmt/knowledge_base/"
    missing = api_client.post(base, {"name": "kb-no-intro", "team": [1]}, format="json")
    assert missing.status_code == 400

    created = api_client.post(
        base,
        {"name": "kb-intro", "team": [1], "introduction": "目标与收录范围", "purpose_md": "# hidden", "schema_md": "# hidden"},
        format="json",
    )
    assert created.status_code in (200, 201), created.content
    data = created.json().get("data", created.json())
    assert data["introduction"] == "目标与收录范围"
    assert "purpose_md" not in data
    assert "schema_md" not in data
    assert data["template_key"] == "general"

    templates = api_client.get(base + "templates/")
    assert templates.status_code == 404

    generate = api_client.post(base + "generate_purpose_schema/", {"template_key": "ops_qa"}, format="json")
    assert generate.status_code == 404

    kb = WikiKnowledgeBase.objects.get(id=data["id"])
    blank = api_client.patch(f"{base}{kb.id}/", {"introduction": "   "}, format="json")
    assert blank.status_code == 400


def test_schema_fingerprint_tracks_introduction_not_purpose(wiki_factory):
    from apps.opspilot.services.wiki.decision_service import compute_schema_fingerprint

    knowledge_base = _bootstrap(wiki_factory, introduction="收录运维问答")
    original = compute_schema_fingerprint(knowledge_base)
    knowledge_base.purpose_md = "# changed purpose"
    knowledge_base.schema_md = "# changed schema"
    knowledge_base.save(update_fields=["purpose_md", "schema_md", "updated_at"])
    assert compute_schema_fingerprint(knowledge_base) == original
    knowledge_base.introduction = "收录变更后的范围"
    knowledge_base.save(update_fields=["introduction", "updated_at"])
    assert compute_schema_fingerprint(knowledge_base) != original


def test_manual_and_build_pages_land_in_type_roots_without_source_pages(wiki_factory):
    from types import SimpleNamespace

    from apps.opspilot.services.wiki import build_service
    from apps.opspilot.services.wiki.page_service import create_manual_page

    knowledge_base = _bootstrap(wiki_factory)
    entity_page = create_manual_page(
        knowledge_base,
        page_type="entity",
        title="作业平台",
        body="实体正文",
        created_by="admin",
    )
    concept_page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="发布流程",
        body="概念正文",
        created_by="admin",
    )
    entity_page.refresh_from_db()
    concept_page.refresh_from_db()
    assert entity_page.directory.key == "schema_entity"
    assert concept_page.directory.key == "schema_concept"

    snapshot = get_structure(knowledge_base)["structure"]
    finalized = build_service._finalize_material_pages(
        [
            {"page_type": "entity", "title": "实体根验证页", "body": "配置管理平台负责资源模型。"},
            {"page_type": "source", "title": "手册", "body": "这是资料摘要，不应落成知识页。"},
            {"page_type": "faq", "title": "未知类型验证页", "body": "未知类型应落到概念根。"},
        ],
        kb=SimpleNamespace(id=knowledge_base.pk),
        structure_revision=SimpleNamespace(structure_snapshot=snapshot),
        source_metadata={"source_title": "手册", "display_name": "手册"},
    )
    assert {page["page_type"] for page in finalized} == {"entity", "concept"}
    by_title = {page["title"]: page for page in finalized}
    assert by_title["实体根验证页"]["directory_key"] == "schema_entity"
    assert by_title["未知类型验证页"]["directory_key"] == "schema_concept"
