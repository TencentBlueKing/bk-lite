"""网关测试公共 fixture。

读侧 TTL 回源上线后，_me / _docs / _auth 在快照过期时会真实回源 KV；
测试中默认按「KV 不可达」处理（fetch_entries → None，降级快照），保证
不真连 NATS。需要外部注册条目的测试自行 monkeypatch fetch_entries 并调用
refresh_snapshot 预热（覆盖本 fixture 的默认值）。
"""

import pytest

from apps.core.openapi import allowlist as allowlist_mod
from apps.core.openapi import renderer

_EMPTY_SNAPSHOT = {
    "config": None,
    "services": [],
    "entries": {},
    "normalized": {},
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


@pytest.fixture(autouse=True)
def _isolate_openapi_allowlist(request, monkeypatch):
    """无 DB 的单元测试：允许清单只读 env，不查库。

    带 django_db 标记的用例保持真实查询（allowlist 的 DB 行为由
    test_allowlist.py 覆盖）；否则查询异常会让 refresh_snapshot 走
    「DB 不可达沿用快照」分支，掩盖被测的注册表新鲜度逻辑。
    """
    if request.node.get_closest_marker("django_db"):
        return
    monkeypatch.setattr(allowlist_mod, "db_hosts", list)
