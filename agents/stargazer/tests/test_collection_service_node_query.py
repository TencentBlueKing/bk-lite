import json

import pytest

import service.collection_service as collection_service_module
from service.collection_service import CollectionService


def _service(params):
    service = CollectionService.__new__(CollectionService)
    service._node_info = None
    service.namespace = "bklite"
    service.params = params
    service.host = params.get("host")
    service.connect_ip = params.get("connect_ip") or service.host
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize("organization_id", ["org-42", None])
async def test_set_node_info_scopes_query_and_filters_ip(
    monkeypatch, organization_id
):
    params = {"host": "10.0.0.1", "model_id": "host"}
    if organization_id:
        params["organization_id"] = organization_id
    captured = []

    async def request(_subject, payload=None, timeout=10.0):
        captured.append(json.loads(payload))
        return {"success": False, "result": {"nodes": []}}

    monkeypatch.setattr(collection_service_module, "nats_request", request)
    await _service(params).set_node_info()

    query = captured[0]["args"][0]
    assert query["ip"] == "10.0.0.1"
    assert query["page_size"] == 1
    if organization_id:
        assert query["organization_ids"] == [organization_id]
        assert "skip_permission" not in query
    else:
        assert query["skip_permission"] is True


@pytest.mark.asyncio
async def test_set_node_info_reads_matching_node(monkeypatch):
    async def request(_subject, payload=None, timeout=10.0):
        return {
            "success": True,
            "result": {
                "nodes": [
                    {"ip": "10.0.0.3", "os": "Linux", "node_id": "n-123"}
                ]
            },
        }

    monkeypatch.setattr(collection_service_module, "nats_request", request)
    service = _service(
        {
            "host": "10.0.0.3",
            "model_id": "host",
            "organization_id": "org-7",
        }
    )
    await service.set_node_info()

    assert service._node_info["node_id"] == "n-123"
