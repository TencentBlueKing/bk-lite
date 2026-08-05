from copy import deepcopy

import pytest

from apps.opspilot.models import WikiDirectory, WikiGeneration, WikiStructureRevision
from apps.opspilot.services.wiki.structure_service import StructureServiceError, bootstrap_knowledge_base, get_structure, save_structure

pytestmark = pytest.mark.django_db(transaction=True)


def _bootstrap(wiki_factory):
    knowledge_base = wiki_factory.knowledge_base()
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
            "page_types": ["concept"],
            "directories": [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]],
        },
    }


def _new_node(client_ref, name, *, parent=None, default=False):
    return {
        "kind": "new",
        "client_ref": client_ref,
        "name": name,
        "description": "",
        "order": 10,
        "rules": {
            "allowed_page_types": ["concept"],
            "default_for_page_types": ["concept"] if default else [],
        },
        "parent": parent,
    }


def _assert_atomic_rejection(knowledge_base, payload, expected_code):
    before = (
        WikiDirectory.objects.filter(knowledge_base=knowledge_base).count(),
        WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count(),
        WikiGeneration.objects.filter(knowledge_base=knowledge_base).count(),
    )

    with pytest.raises(StructureServiceError) as captured:
        save_structure(knowledge_base, payload, operator="admin")

    assert captured.value.code == expected_code
    assert (
        WikiDirectory.objects.filter(knowledge_base=knowledge_base).count(),
        WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count(),
        WikiGeneration.objects.filter(knowledge_base=knowledge_base).count(),
    ) == before


def test_structure_rejects_normalized_duplicate_sibling_names_atomically(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    payload = _payload(knowledge_base)
    payload["structure"]["directories"].extend(
        [
            _new_node("first", "Run Book"),
            _new_node("second", " run\u3000book "),
        ]
    )

    _assert_atomic_rejection(
        knowledge_base,
        payload,
        "directory_sibling_name_duplicate",
    )


def test_structure_rejects_cycle_and_depth_above_eight_atomically(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    cycle_payload = _payload(knowledge_base)
    cycle_payload["structure"]["directories"].extend(
        [
            _new_node("cycle-a", "Cycle A", parent={"client_ref": "cycle-b"}),
            _new_node("cycle-b", "Cycle B", parent={"client_ref": "cycle-a"}),
        ]
    )
    _assert_atomic_rejection(knowledge_base, cycle_payload, "directory_cycle")

    depth_payload = _payload(knowledge_base)
    for index in range(9):
        depth_payload["structure"]["directories"].append(
            _new_node(
                f"depth-{index}",
                f"Depth {index}",
                parent=None if index == 0 else {"client_ref": f"depth-{index - 1}"},
            )
        )
    _assert_atomic_rejection(
        knowledge_base,
        depth_payload,
        "directory_depth_exceeded",
    )


def test_structure_rejects_cross_kb_parent_atomically(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    foreign = _bootstrap(wiki_factory)
    foreign_directory = foreign.directories.get(key="__unclassified__")
    payload = _payload(knowledge_base)
    payload["structure"]["directories"].append(
        _new_node(
            "cross-kb-child",
            "Cross KB Child",
            parent={"id": foreign_directory.id, "key": foreign_directory.key},
        )
    )

    _assert_atomic_rejection(
        knowledge_base,
        payload,
        "directory_parent_knowledge_base_mismatch",
    )


def test_structure_rejects_duplicate_page_type_default_atomically(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    payload = _payload(knowledge_base)
    payload["structure"]["directories"].extend(
        [
            _new_node("default-a", "Default A", default=True),
            _new_node("default-b", "Default B", default=True),
        ]
    )

    _assert_atomic_rejection(
        knowledge_base,
        payload,
        "page_type_default_duplicate",
    )


def test_structure_rejects_unclassified_mutation_atomically(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    payload = _payload(knowledge_base)
    payload["structure"]["directories"][0]["name"] = "Renamed"

    _assert_atomic_rejection(
        knowledge_base,
        payload,
        "unclassified_directory_invariant",
    )
