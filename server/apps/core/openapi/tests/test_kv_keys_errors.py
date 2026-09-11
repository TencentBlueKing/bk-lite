"""kv.keys 错误分类：空 bucket 与超时/断连不得写成空注册表。"""

import json
from types import SimpleNamespace

import pytest
from nats.js.errors import NoKeysError

from apps.core.openapi import kv, renderer

pytestmark = pytest.mark.unit

SAMPLE_ENTRY = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "auth_mode": "trusted-header",
    "shared_secret_ref": "env:TEST_ITSM_SECRET",
    "required_roles": [],
    "enabled": True,
}


class FakeKV:
    def __init__(self, keys_side_effect, values=None):
        self._keys_side_effect = keys_side_effect
        self._values = dict(values or {})

    async def keys(self):
        effect = self._keys_side_effect
        if callable(effect):
            effect = effect()
        if isinstance(effect, BaseException):
            raise effect
        return list(effect)

    async def get(self, key):
        return SimpleNamespace(value=json.dumps(self._values[key]).encode())


class FakeJS:
    def __init__(self, store):
        self._store = store

    async def key_value(self, bucket):
        return self._store


class FakeNC:
    def __init__(self, store):
        self._store = store

    def jetstream(self):
        return FakeJS(self._store)

    async def close(self):
        return None


def install_kv(monkeypatch, keys_side_effect, values=None):
    store = FakeKV(keys_side_effect, values=values)

    async def fake_get_nc_client(*args, **kwargs):
        return FakeNC(store)

    monkeypatch.setattr("nats_client.clients.get_nc_client", fake_get_nc_client)
    return store


def test_nokeys_error_returns_empty_registry(monkeypatch):
    install_kv(monkeypatch, NoKeysError())
    assert kv.fetch_entries() == {}


@pytest.mark.parametrize("exc", [TimeoutError("kv.keys timeout"), Exception("nats disconnected")])
def test_keys_failure_returns_none(monkeypatch, exc):
    install_kv(monkeypatch, exc)
    assert kv.fetch_entries() is None


def test_refresh_keeps_snapshot_when_keys_times_out(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_ITSM_SECRET", "s3cret")
    monkeypatch.setattr(renderer, "fetch_entries", kv.fetch_entries)

    state = {"calls": 0}

    def keys_effect():
        state["calls"] += 1
        if state["calls"] == 1:
            return ["itsm"]
        raise TimeoutError("kv.keys timeout")

    install_kv(monkeypatch, keys_effect, values={"itsm": dict(SAMPLE_ENTRY)})

    first = renderer.refresh_snapshot()
    assert "openapi-v1-itsm" in first["http"]["routers"]
    assert renderer._snapshot["services"] == ["itsm"]

    second = renderer.refresh_snapshot()
    assert state["calls"] == 2
    assert "openapi-v1-itsm" in second["http"]["routers"]
    assert renderer._snapshot["services"] == ["itsm"]
    assert renderer._snapshot["entries"]["itsm"]["base_url"] == "http://itsm-svc:8000"
