"""Redis sorted set 工具：zadd/zrange/zrem/zscore/zcard/zrevrange/zrangebyscore/zrank。"""
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from apps.opspilot.metis.llm.tools.redis import sorted_set as zs

pytestmark = pytest.mark.unit
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 6379, "db": 0}}


@pytest.fixture
def client():
    mock = MagicMock()
    with patch.object(zs, "get_redis_connection_from_item", return_value=mock):
        yield mock


def test_sorted_set_write_read_rank_and_error(client):
    client.zadd.return_value = 2
    out = zs.redis_zadd.invoke({"key": "lb", "members": {"a": 1.0, "b": 2.0}, "config": CONFIG})
    assert out == {"success": True, "data": {"added": 2}, "key": "lb"}
    client.zadd.assert_called_once_with("lb", {"a": 1.0, "b": 2.0})

    client.zrange.return_value = ["a", "b"]
    out = zs.redis_zrange.invoke({"key": "lb", "start": 0, "end": -1, "config": CONFIG})
    assert out["success"] is True
    assert out["data"] == ["a", "b"]
    client.zrange.assert_called_once_with("lb", 0, -1, withscores=False)

    client.zrem.return_value = 1
    out = zs.redis_zrem.invoke({"key": "lb", "member": "a", "config": CONFIG})
    assert out["data"] == {"removed": 1}

    client.zscore.return_value = 2.5
    out = zs.redis_zscore.invoke({"key": "lb", "member": "b", "config": CONFIG})
    assert out["data"] == {"key": "lb", "member": "b", "score": 2.5}

    client.zcard.return_value = 3
    out = zs.redis_zcard.invoke({"key": "lb", "config": CONFIG})
    assert out["data"] == {"key": "lb", "count": 3}

    client.zrevrange.return_value = [("b", 2.0)]
    out = zs.redis_zrevrange.invoke({"key": "lb", "start": 0, "end": 0, "withscores": True, "config": CONFIG})
    assert out["data"] == [["b", 2.0]]
    client.zrevrange.assert_called_once_with("lb", 0, 0, withscores=True)

    client.zrangebyscore.return_value = ["b"]
    out = zs.redis_zrangebyscore.invoke({"key": "lb", "min_score": 1.5, "max_score": 3.0, "config": CONFIG})
    assert out["data"] == ["b"]
    client.zrangebyscore.assert_called_once_with("lb", 1.5, 3.0, withscores=False)

    client.zrank.return_value = 0
    out = zs.redis_zrank.invoke({"key": "lb", "member": "a", "config": CONFIG})
    assert out["data"] == {"key": "lb", "member": "a", "rank": 0}

    client.zadd.side_effect = RedisError("down")
    err = zs.redis_zadd.invoke({"key": "lb", "members": {"a": 1.0}, "config": CONFIG})
    assert err == {"success": False, "error": "down", "error_type": "redis_error"}
