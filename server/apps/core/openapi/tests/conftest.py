"""网关测试公共 fixture。

读侧 TTL 回源上线后，_me / _docs / _auth 在快照过期时会真实回源 KV；
测试中默认按「KV 不可达」处理（fetch_entries → None，降级快照），保证
不真连 NATS。需要外部注册条目的测试自行 monkeypatch fetch_entries 并调用
refresh_snapshot 预热（覆盖本 fixture 的默认值）。
"""

import pytest

from apps.core.openapi import renderer

_EMPTY_SNAPSHOT = {
    "config": None,
    "services": [],
    "entries": {},
    "checked_at": 0.0,
    "fetch_started_at": 0.0,
}


@pytest.fixture(autouse=True)
def _isolate_openapi_kv(monkeypatch):
    monkeypatch.setattr(renderer, "fetch_entries", lambda: None)
    with renderer._lock:
        renderer._snapshot.update(_EMPTY_SNAPSHOT)
    yield
    with renderer._lock:
        renderer._snapshot.update(_EMPTY_SNAPSHOT)
