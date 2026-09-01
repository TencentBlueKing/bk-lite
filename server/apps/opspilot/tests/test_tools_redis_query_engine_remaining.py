"""Redis 搜索工具：索引列表/信息/向量检索成功与 RedisError。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import query_engine as qe

pytestmark = pytest.mark.unit
MOD = "apps.opspilot.metis.llm.tools.redis.query_engine"


def _run(func, client, **kwargs):
    normalized = {"mode": "single", "items": [{"name": "redis-1"}]}
    with (
        patch(f"{MOD}.build_redis_normalized_from_runnable", return_value=normalized),
        patch(f"{MOD}.get_redis_connection_from_item", return_value=client),
    ):
        return func(**kwargs)


def test_redis_index_helpers_success_and_unsupported():
    client = MagicMock()
    client.execute_command.return_value = ["idx-a"]
    client.ft.return_value.info.return_value = {"num_docs": 3}
    client.ft.return_value.search.return_value = SimpleNamespace(total=9)
    assert _run(qe.redis_get_indexes.func, client, config={}) == {"success": True, "data": ["idx-a"]}
    assert _run(qe.redis_get_index_info.func, client, index_name="idx-a", config={}) == {
        "success": True,
        "data": {"num_docs": 3},
    }
    assert _run(qe.redis_get_indexed_keys_number.func, client, index_name="idx-a", config={}) == {
        "success": True,
        "data": {"index_name": "idx-a", "total": 9},
    }
    client.execute_command.side_effect = RedisError("no FT")
    assert _run(qe.redis_get_indexes.func, client, config={}) == {
        "success": False,
        "error": "no FT",
        "error_type": "unsupported_feature",
    }


def test_redis_vector_hybrid_search_and_create_index():
    client = MagicMock()
    client.ft.return_value.create_index.return_value = True
    assert _run(qe.redis_create_vector_index_hash.func, client, index_name="v", config={}) == {
        "success": True,
        "data": {"index_name": "v", "created": True},
    }
    doc = SimpleNamespace(id="d1", score="0.1")
    client.ft.return_value.search.return_value = SimpleNamespace(docs=[doc])
    searched = _run(
        qe.redis_vector_search_hash.func,
        client,
        query_vector=[0.1, 0.2],
        index_name="v",
        config={},
    )
    assert searched == {"success": True, "data": [{"id": "d1", "score": "0.1"}]}
    hybrid = _run(
        qe.redis_hybrid_search.func,
        client,
        query_vector=[0.1, 0.2],
        filter_expression="@city:beijing",
        index_name="v",
        config={},
    )
    assert hybrid == {"success": True, "data": [{"id": "d1", "score": "0.1"}]}
    client.ft.return_value.search.side_effect = RedisError("no module")
    assert _run(
        qe.redis_vector_search_hash.func,
        client,
        query_vector=[0.1],
        index_name="v",
        config={},
    ) == {
        "success": False,
        "error": "no module",
        "error_type": "unsupported_feature",
    }
