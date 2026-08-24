"""Job 节点信息批量查询 Adapter。"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from core.infra.nats_utils import nats_request


async def load_node_infos(
    ips: Sequence[str],
    *,
    collect_task_id: Any = None,
    cloud_region_id: Any = None,
    timeout_seconds: float = 10.0,
) -> list[Mapping[str, Any]]:
    if collect_task_id in (None, ""):
        raise ValueError("collect_task_id is required for node info lookup")
    query: dict[str, Any] = {
        "ips": list(ips),
        "collect_task_id": collect_task_id,
    }
    if cloud_region_id not in (None, ""):
        query["cloud_region_id"] = cloud_region_id

    payload = json.dumps({"args": [query], "kwargs": {}}).encode()
    response = await nats_request(
        "bklite.get_nodes_by_ips",
        payload=payload,
        timeout=timeout_seconds,
    )
    if not isinstance(response, Mapping) or not response.get("success"):
        detail = response.get("error") if isinstance(response, Mapping) else "invalid response"
        raise RuntimeError(f"node info batch query failed: {detail}")
    result = response.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("nodes"), list):
        raise RuntimeError("node info batch query returned invalid result")
    return [node for node in result["nodes"] if isinstance(node, Mapping)]
