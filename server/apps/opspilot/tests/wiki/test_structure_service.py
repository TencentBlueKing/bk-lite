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


def _save_payload(knowledge_base, *, client_ref="manual-runbook"):
    current = get_structure(knowledge_base)
    existing = [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]]
    page_types = list(current["structure"]["page_types"])
    preferred = next((item for item in page_types if item.casefold() == "concept"), page_types[0])
    return {
        "structure_version": current["structure_revision"]["version"],
        "base_generation_id": current["active_generation"]["id"],
        "structure": {
            "format_version": 1,
            "page_types": page_types,
            "directories": [
                *existing,
                {
                    "kind": "new",
                    "client_ref": client_ref,
                    "name": "运行手册",
                    "description": "管理员维护的运行手册",
                    "order": 10,
                    "rules": {
                        "allowed_page_types": [preferred],
                        "default_for_page_types": [],
                    },
                    "parent": None,
                },
            ],
        },
    }


def test_bootstrap_is_idempotent_and_creates_one_active_pair(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)

    first_generation_id = knowledge_base.active_generation_id
    directory_count = WikiDirectory.objects.filter(knowledge_base=knowledge_base).count()
    assert directory_count >= 1
    result = bootstrap_knowledge_base(knowledge_base, operator="admin")

    knowledge_base.refresh_from_db()
    assert knowledge_base.directory_migration_state == "ready"
    assert knowledge_base.directory_enabled is False
    assert knowledge_base.active_generation_id == first_generation_id
    assert result["active_generation"]["id"] == first_generation_id
    assert WikiDirectory.objects.filter(knowledge_base=knowledge_base).count() == directory_count
    assert WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count() == 1
    assert WikiGeneration.objects.filter(knowledge_base=knowledge_base).count() == 1


def test_save_structure_atomically_activates_revision_and_governance_generation(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    previous_generation_id = knowledge_base.active_generation_id

    result = save_structure(knowledge_base, _save_payload(knowledge_base), operator="admin")

    knowledge_base.refresh_from_db()
    created = WikiDirectory.objects.get(knowledge_base=knowledge_base, name="运行手册")
    assert created.origin == "manual"
    assert result["client_ref_map"] == [{"client_ref": "manual-runbook", "id": created.id, "key": created.key}]
    assert result["structure_revision"]["version"] == 2
    assert result["active_generation"]["id"] == knowledge_base.active_generation_id
    assert knowledge_base.active_generation_id != previous_generation_id
    assert knowledge_base.active_structure_revision_id == result["structure_revision"]["id"]
    assert WikiGeneration.objects.get(pk=previous_generation_id).status == "superseded"


def test_stale_structure_cas_rolls_back_without_creating_rows(wiki_factory):
    knowledge_base = _bootstrap(wiki_factory)
    payload = _save_payload(knowledge_base)
    payload["structure_version"] += 1
    before = {
        "directories": WikiDirectory.objects.filter(knowledge_base=knowledge_base).count(),
        "revisions": WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count(),
        "generations": WikiGeneration.objects.filter(knowledge_base=knowledge_base).count(),
    }

    with pytest.raises(StructureServiceError) as captured:
        save_structure(knowledge_base, payload, operator="admin")

    assert captured.value.code == "structure_version_conflict"
    assert captured.value.retryable is True
    assert WikiDirectory.objects.filter(knowledge_base=knowledge_base).count() == before["directories"]
    assert WikiStructureRevision.objects.filter(knowledge_base=knowledge_base).count() == before["revisions"]
    assert WikiGeneration.objects.filter(knowledge_base=knowledge_base).count() == before["generations"]
