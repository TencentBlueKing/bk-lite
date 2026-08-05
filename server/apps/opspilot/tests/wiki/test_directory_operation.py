from copy import deepcopy

import pytest
from django.core.cache import cache

from apps.opspilot.services.wiki.directory_operation_service import _decode_operation_token, execute_directory_operation, preview_directory_operation
from apps.opspilot.services.wiki.directory_service import DirectoryServiceError
from apps.opspilot.services.wiki.structure_service import bootstrap_knowledge_base, get_structure, save_structure

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def use_operation_token_cache(settings, use_dummy_cache_backend):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "wiki-directory-operation-tests",
        }
    }


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
                        "client_ref": "empty-manual",
                        "name": "Empty Manual",
                        "description": "",
                        "order": 10,
                        "rules": {
                            "allowed_page_types": ["concept"],
                            "default_for_page_types": [],
                        },
                        "parent": None,
                    },
                ],
            },
        },
        operator="admin",
    )
    knowledge_base.refresh_from_db()
    return knowledge_base, knowledge_base.directories.get(name="Empty Manual")


def _preview(knowledge_base, directory):
    return preview_directory_operation(
        knowledge_base,
        {
            "structure_version": knowledge_base.active_structure_revision.revision_no,
            "base_generation_id": knowledge_base.active_generation_id,
            "action": "archive",
            "source": {"id": directory.id, "key": directory.key},
        },
    )


def _execute_payload(preview):
    binding = preview["binding"]
    return {
        "structure_version": binding["structure_version"],
        "base_generation_id": binding["base_generation_id"],
        "action": binding["action"],
        "source": binding["source"],
        "impact_hash": binding["impact_hash"],
        "operation_token": preview["operation_token"],
    }


def test_operation_token_binds_impact_is_single_use_and_mismatch_does_not_consume(wiki_factory):
    knowledge_base, directory = _configured_kb(wiki_factory)
    preview = _preview(knowledge_base, directory)
    payload = _execute_payload(preview)
    mismatched = {**payload, "impact_hash": "0" * 64}

    assert preview["can_execute"] is True
    assert preview["single_use"] is True
    with pytest.raises(DirectoryServiceError) as captured:
        execute_directory_operation(knowledge_base, mismatched, operator="admin")
    assert captured.value.code == "operation_token_binding_mismatch"

    result = execute_directory_operation(knowledge_base, payload, operator="admin")
    directory.refresh_from_db()
    assert result["action_result"]["action"] == "archive"
    assert directory.status == "archived"
    assert directory.accepts_pages is False
    token_payload = _decode_operation_token(preview["operation_token"])
    consumed_key = f"wiki-directory-operation-consumed:{token_payload['jti']}"
    assert cache.get(consumed_key) is True

    with pytest.raises(DirectoryServiceError) as replayed:
        execute_directory_operation(knowledge_base, payload, operator="admin")
    assert replayed.value.code == "operation_token_replayed"


def test_operation_token_rejects_changed_structure_without_partial_archive(wiki_factory):
    knowledge_base, directory = _configured_kb(wiki_factory)
    preview = _preview(knowledge_base, directory)
    payload = _execute_payload(preview)
    current = get_structure(knowledge_base)
    save_structure(
        knowledge_base,
        {
            "structure_version": current["structure_revision"]["version"],
            "base_generation_id": current["active_generation"]["id"],
            "structure": {
                **deepcopy(current["structure"]),
                "directories": [{"kind": "existing", **deepcopy(node)} for node in current["structure"]["directories"]],
            },
        },
        operator="admin",
    )

    with pytest.raises(DirectoryServiceError) as captured:
        execute_directory_operation(knowledge_base, payload, operator="admin")

    directory.refresh_from_db()
    assert captured.value.status_code == 409
    assert captured.value.retryable is True
    assert directory.status == "active"
    assert directory.accepts_pages is True
