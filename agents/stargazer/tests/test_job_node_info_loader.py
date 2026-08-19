import json

import pytest
import service.node_info_loader as node_info_loader_module
from service.node_info_loader import load_node_infos


@pytest.mark.asyncio
async def test_load_node_infos_calls_exact_batch_subject_with_scope(monkeypatch):
    captured = {}

    async def request(subject, payload=None, timeout=10.0):
        captured.update(
            subject=subject,
            payload=json.loads(payload),
            timeout=timeout,
        )
        return {
            "success": True,
            "result": {
                "nodes": [
                    {
                        "id": "node-1",
                        "ip": "10.0.0.1",
                        "operating_system": "linux",
                    }
                ]
            },
        }

    monkeypatch.setattr(node_info_loader_module, "nats_request", request)

    nodes = await load_node_infos(
        ("10.0.0.1", "10.0.0.2"),
        collect_task_id=91,
        cloud_region_id=7,
        timeout_seconds=6.0,
    )

    assert captured == {
        "subject": "bklite.get_nodes_by_ips",
        "payload": {
            "args": [
                {
                    "ips": ["10.0.0.1", "10.0.0.2"],
                    "collect_task_id": 91,
                    "cloud_region_id": 7,
                }
            ],
            "kwargs": {},
        },
        "timeout": 6.0,
    }
    assert nodes[0]["id"] == "node-1"


@pytest.mark.asyncio
async def test_load_node_infos_requires_collect_task_identity(monkeypatch):
    async def unexpected_request(*_args, **_kwargs):
        raise AssertionError("unscoped request must not be published")

    monkeypatch.setattr(node_info_loader_module, "nats_request", unexpected_request)

    with pytest.raises(ValueError, match="collect_task_id is required"):
        await load_node_infos(("10.0.0.1",))
