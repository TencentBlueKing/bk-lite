from copy import deepcopy

import pytest

from apps.opspilot.models import KnowledgePage, PageDirectoryChange, WikiDirectory, WikiGeneration
from apps.opspilot.services.wiki.directory_service import (
    DirectoryServiceError,
    archive_pages,
    delete_nested_directory,
    directory_page_type_mismatch_message,
    move_pages,
    restore_pages_auto,
)
from apps.opspilot.services.wiki.page_service import create_manual_page
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base, get_structure, save_structure

pytestmark = pytest.mark.django_db(transaction=True)


def _configured_kb(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    current = get_structure(knowledge_base)
    existing = []
    for directory in current["structure"]["directories"]:
        copied = deepcopy(directory)
        rules = copied.setdefault("rules", {})
        rules["default_for_page_types"] = [item for item in (rules.get("default_for_page_types") or []) if item != "concept"]
        existing.append({"kind": "existing", **copied})
    save_structure(
        knowledge_base,
        {
            "structure_version": current["structure_revision"]["version"],
            "base_generation_id": current["active_generation"]["id"],
            "structure": {
                "format_version": 1,
                "page_types": list(current["structure"]["page_types"]),
                "directories": [
                    *existing,
                    {
                        "kind": "new",
                        "client_ref": "concept-root",
                        "name": "概念知识",
                        "description": "概念页面默认目录",
                        "order": 10,
                        "rules": {
                            "allowed_page_types": ["concept"],
                            "default_for_page_types": ["concept"],
                        },
                        "parent": None,
                    },
                ],
            },
        },
        operator="admin",
    )
    knowledge_base.refresh_from_db()
    return knowledge_base


def test_restore_auto_routes_manual_page_to_unique_type_default(wiki_factory):
    knowledge_base = _configured_kb(wiki_factory)
    unclassified = knowledge_base.directories.get(key="__unclassified__")
    concept_root = knowledge_base.directories.get(name="概念知识")
    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="自动归类目标",
        body="正文",
        directory_id=unclassified.id,
        created_by="admin",
    )
    knowledge_base.refresh_from_db()
    before_generation_id = knowledge_base.active_generation_id

    result = restore_pages_auto(
        knowledge_base,
        page_ids=[page.id],
        base_generation_id=before_generation_id,
        structure_version=knowledge_base.active_structure_revision.revision_no,
        operator="admin",
    )

    knowledge_base.refresh_from_db()
    page.refresh_from_db()
    change = PageDirectoryChange.objects.get(page=page, generation_id=result["generation_id"])
    assert result["generation_id"] == knowledge_base.active_generation_id
    assert result["generation_id"] != before_generation_id
    assert page.directory_id == concept_root.id
    assert page.directory_assignment_mode == "auto"
    assert change.from_directory_id == unclassified.id
    assert change.to_directory_id == concept_root.id
    assert change.to_assignment_mode == "auto"
    assert change.source == "restore_auto"
    assert WikiGeneration.objects.get(pk=before_generation_id).status == "superseded"


def test_manual_move_then_restore_auto_creates_two_immutable_changes(wiki_factory):
    knowledge_base = _configured_kb(wiki_factory)
    concept_root = knowledge_base.directories.get(name="概念知识")
    unclassified = knowledge_base.directories.get(key="__unclassified__")
    page = create_manual_page(
        knowledge_base,
        page_type="concept",
        title="人工与自动边界",
        body="正文",
        directory_id=concept_root.id,
        created_by="admin",
    )
    knowledge_base.refresh_from_db()

    moved = move_pages(
        knowledge_base,
        page_ids=[page.id],
        target_directory_id=unclassified.id,
        base_generation_id=knowledge_base.active_generation_id,
        structure_version=knowledge_base.active_structure_revision.revision_no,
        operator="admin",
    )
    knowledge_base.refresh_from_db()
    page.refresh_from_db()
    assert page.directory_id == unclassified.id
    assert page.directory_assignment_mode == "manual"

    restored = restore_pages_auto(
        knowledge_base,
        page_ids=[page.id],
        base_generation_id=knowledge_base.active_generation_id,
        structure_version=knowledge_base.active_structure_revision.revision_no,
        operator="admin",
    )

    page.refresh_from_db()
    changes = list(PageDirectoryChange.objects.filter(page=page).order_by("id"))
    assert moved["generation_id"] != restored["generation_id"]
    assert page.directory_id == concept_root.id
    assert page.directory_assignment_mode == "auto"
    assert [(item.source, item.to_assignment_mode) for item in changes] == [
        ("manual_move", "manual"),
        ("restore_auto", "auto"),
    ]


def test_page_type_mismatch_message_uses_product_labels():
    assert (
        directory_page_type_mismatch_message(
            "待研究问题",
            page_types=["entity"],
            allowed_page_types=["query"],
        )
        == "「待研究问题」分类只允许「待研究问题」类型的页面，不能放入「实体」。"
    )


def test_move_rejects_entity_into_query_directory_with_clear_message(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    unclassified = knowledge_base.directories.get(key="__unclassified__")
    query_root = knowledge_base.directories.get(name="待研究问题")
    page = create_manual_page(
        knowledge_base,
        page_type="entity",
        title="订单实体",
        body="正文",
        directory_id=unclassified.id,
        created_by="admin",
    )
    knowledge_base.refresh_from_db()

    with pytest.raises(DirectoryServiceError) as exc_info:
        move_pages(
            knowledge_base,
            page_ids=[page.id],
            target_directory_id=query_root.id,
            base_generation_id=knowledge_base.active_generation_id,
            structure_version=knowledge_base.active_structure_revision.revision_no,
            operator="admin",
        )

    error = exc_info.value
    assert error.code == "directory_page_type_mismatch"
    assert str(error) == "「待研究问题」分类只允许「待研究问题」类型的页面，不能放入「实体」。"


def _add_nested_tables(knowledge_base):
    knowledge_base.refresh_from_db()
    current = get_structure(knowledge_base)
    unclassified = next(directory for directory in current["structure"]["directories"] if directory.get("key") == "__unclassified__")
    existing = [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]]
    save_structure(
        knowledge_base,
        {
            "structure_version": current["structure_revision"]["version"],
            "base_generation_id": current["active_generation"]["id"],
            "structure": {
                "format_version": 1,
                "page_types": list(current["structure"]["page_types"]),
                "directories": [
                    *existing,
                    {
                        "kind": "new",
                        "client_ref": "tables-folder",
                        "name": "tables",
                        "description": "",
                        "order": 20,
                        "rules": {
                            "allowed_page_types": list(current["structure"]["page_types"]),
                            "default_for_page_types": [],
                        },
                        "parent": {"id": unclassified["id"], "key": unclassified["key"]},
                    },
                ],
            },
        },
        operator="admin",
    )
    knowledge_base.refresh_from_db()
    return knowledge_base.directories.get(name="tables")


def test_delete_nested_directory_archives_pages_and_omits_folder(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    tables = _add_nested_tables(knowledge_base)
    unclassified = knowledge_base.directories.get(key="__unclassified__")
    page = create_manual_page(
        knowledge_base,
        page_type="entity",
        title="测试订单",
        body="正文",
        directory_id=tables.id,
        created_by="admin",
    )
    knowledge_base.refresh_from_db()

    delete_nested_directory(
        knowledge_base,
        directory_id=tables.id,
        base_generation_id=knowledge_base.active_generation_id,
        structure_version=knowledge_base.active_structure_revision.revision_no,
        operator="admin",
    )

    page.refresh_from_db()
    tables.refresh_from_db()
    assert page.status == "archived"
    assert page.directory_id == unclassified.id
    assert tables.status == "archived"
    assert not WikiDirectory.objects.filter(pk=tables.id, status="active").exists()
    current = get_structure(knowledge_base)
    assert all(node.get("id") != tables.id for node in current["structure"]["directories"])
    assert not KnowledgePage.objects.filter(pk=page.id, directory_id=tables.id).exists()


def test_delete_nested_directory_retries_after_pages_already_archived(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    tables = _add_nested_tables(knowledge_base)
    unclassified = knowledge_base.directories.get(key="__unclassified__")
    page = create_manual_page(
        knowledge_base,
        page_type="entity",
        title="残留订单",
        body="正文",
        directory_id=tables.id,
        created_by="admin",
    )
    knowledge_base.refresh_from_db()
    archive_pages(
        knowledge_base,
        page_ids=[page.id],
        base_generation_id=knowledge_base.active_generation_id,
        structure_version=knowledge_base.active_structure_revision.revision_no,
        operator="admin",
    )
    page.refresh_from_db()
    assert page.status == "archived"
    assert page.directory_id == tables.id
    knowledge_base.refresh_from_db()

    delete_nested_directory(
        knowledge_base,
        directory_id=tables.id,
        base_generation_id=knowledge_base.active_generation_id,
        structure_version=knowledge_base.active_structure_revision.revision_no,
        operator="admin",
    )

    page.refresh_from_db()
    tables.refresh_from_db()
    assert page.directory_id == unclassified.id
    assert tables.status == "archived"


def test_delete_nested_directory_rejects_top_level(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    concept = knowledge_base.directories.get(name="概念")

    with pytest.raises(DirectoryServiceError) as exc_info:
        delete_nested_directory(
            knowledge_base,
            directory_id=concept.id,
            base_generation_id=knowledge_base.active_generation_id,
            structure_version=knowledge_base.active_structure_revision.revision_no,
            operator="admin",
        )

    assert exc_info.value.code == "nested_directory_required"
