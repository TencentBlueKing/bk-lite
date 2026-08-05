from copy import deepcopy

import pytest

from apps.opspilot.models import PageDirectoryChange, WikiGeneration
from apps.opspilot.services.wiki.directory_service import move_pages, restore_pages_auto
from apps.opspilot.services.wiki.page_service import create_manual_page
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base, get_structure, save_structure

pytestmark = pytest.mark.django_db(transaction=True)


def _configured_kb(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
    bootstrap_knowledge_base(knowledge_base, operator="admin")
    knowledge_base.refresh_from_db()
    current = get_structure(knowledge_base)
    existing = [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]]
    save_structure(
        knowledge_base,
        {
            "structure_version": current["structure_revision"]["version"],
            "base_generation_id": current["active_generation"]["id"],
            "structure": {
                "format_version": 1,
                "page_types": ["concept"],
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
