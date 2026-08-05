from copy import deepcopy

import pytest

from apps.opspilot.models import WikiGeneration, WikiStructureRevision

pytestmark = pytest.mark.django_db(transaction=True)


KB_BASE = "/api/v1/opspilot/wiki_mgmt/knowledge_base/"
DIRECTORY_BASE = "/api/v1/opspilot/wiki_mgmt/directory/"


def _data(response):
    body = response.json()
    return body.get("data", body)


def _create_kb(api_client, name="目录治理 API"):
    response = api_client.post(
        KB_BASE,
        {
            "name": name,
            "team": [1],
            "purpose_md": "# Purpose",
            "schema_md": "# Schema",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return _data(response)


def test_new_kb_readiness_enable_and_tree_are_connected(api_client):
    knowledge_base = _create_kb(api_client)

    readiness = api_client.get(f"{KB_BASE}{knowledge_base['id']}/directory_readiness/?enable_check=true")
    enabled = api_client.post(
        f"{KB_BASE}{knowledge_base['id']}/directory_enable/",
        {},
        format="json",
    )
    tree = api_client.get(f"{DIRECTORY_BASE}tree/?knowledge_base={knowledge_base['id']}")

    assert readiness.status_code == 200, readiness.content
    assert _data(readiness)["ready"] is True
    assert enabled.status_code == 200, enabled.content
    assert _data(enabled)["migration_state"] == "enabled"
    assert _data(enabled)["directory_enabled"] is True
    assert tree.status_code == 200, tree.content
    assert _data(tree)["enabled"] is True
    assert _data(tree)["migration_state"] == "enabled"
    assert _data(tree)["directories"][0]["key"] == "__unclassified__"


def test_structure_api_returns_retryable_409_without_partial_rows(api_client):
    knowledge_base = _create_kb(api_client, "结构 CAS")
    structure_response = api_client.get(f"{DIRECTORY_BASE}structure/?knowledge_base={knowledge_base['id']}")
    assert structure_response.status_code == 200, structure_response.content
    current = _data(structure_response)
    payload = {
        "structure_version": current["structure_revision"]["version"] + 1,
        "base_generation_id": current["active_generation"]["id"],
        "structure": {
            **deepcopy(current["structure"]),
            "directories": [{"kind": "existing", **deepcopy(directory)} for directory in current["structure"]["directories"]],
        },
    }
    before = (
        WikiStructureRevision.objects.filter(knowledge_base_id=knowledge_base["id"]).count(),
        WikiGeneration.objects.filter(knowledge_base_id=knowledge_base["id"]).count(),
    )

    response = api_client.put(
        f"{DIRECTORY_BASE}structure/?knowledge_base={knowledge_base['id']}",
        payload,
        format="json",
    )

    assert response.status_code == 409, response.content
    assert response.json()["code"] == "structure_version_conflict"
    assert response.json()["retryable"] is True
    assert response.json()["details"]["latest"]["structure_version"] == 1
    assert (
        WikiStructureRevision.objects.filter(knowledge_base_id=knowledge_base["id"]).count(),
        WikiGeneration.objects.filter(knowledge_base_id=knowledge_base["id"]).count(),
    ) == before


def test_directory_read_and_write_endpoints_enforce_function_permissions(
    api_client,
    authenticated_user,
):
    knowledge_base = _create_kb(api_client, "权限校验")
    authenticated_user.permission = {"opspilot": set()}

    read = api_client.get(f"{KB_BASE}{knowledge_base['id']}/directory_readiness/")
    write = api_client.post(
        f"{KB_BASE}{knowledge_base['id']}/directory_enable/",
        {},
        format="json",
    )

    assert read.status_code == 403
    assert write.status_code == 403
