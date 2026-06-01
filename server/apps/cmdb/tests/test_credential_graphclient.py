"""CMDB 凭据加解密与图客户端驱动选择覆盖测试。

对照 spec/prd/CMDB：采集凭据 Fernet 加解密；图数据库驱动按环境变量切换(FalkorDB/Neo4j)。
"""

import pytest

from apps.cmdb.utils.credential import Credential


# --------------------------------------------------------------------------
# Credential
# --------------------------------------------------------------------------


def test_credential_roundtrip(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "my-secret-key")
    cred = Credential()
    enc = cred.encrypt_data("hello world")
    assert enc != "hello world"
    assert cred.decrypt_data(enc) == "hello world"


def test_credential_key_is_deterministic(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "fixed-key")
    k1 = Credential().get_key()
    k2 = Credential().get_key()
    assert k1 == k2
    assert len(k1) == 44  # urlsafe base64 of 32 bytes


# --------------------------------------------------------------------------
# GraphClient 驱动选择
# --------------------------------------------------------------------------


def test_graphclient_driver_type_falkordb(monkeypatch):
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    monkeypatch.setenv("FALKORDB_HOST", "10.0.0.1")
    client = GraphClient.__new__(GraphClient)
    assert client._get_driver_type() == GraphClient.DRIVER_FALKORDB


def test_graphclient_driver_type_neo4j(monkeypatch):
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    monkeypatch.delenv("FALKORDB_HOST", raising=False)
    client = GraphClient.__new__(GraphClient)
    assert client._get_driver_type() == GraphClient.DRIVER_NEO4J


def test_graphclient_init_unsupported_driver(monkeypatch):
    from apps.cmdb.graph.drivers import graph_client as gc

    client = gc.GraphClient.__new__(gc.GraphClient)
    client._client = None
    client._kwargs = {}
    monkeypatch.setattr(client, "_get_driver_type", lambda: "mongodb")
    with pytest.raises(ValueError):
        client._init_client()


def test_graphclient_getattr_uninitialized():
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    client = GraphClient.__new__(GraphClient)
    client._client = None
    with pytest.raises(RuntimeError):
        _ = client.some_method


def test_graphclient_proxies_to_client():
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    class FakeClient:
        def query(self):
            return "ok"

    client = GraphClient.__new__(GraphClient)
    client._client = FakeClient()
    assert client.query() == "ok"


def test_graphclient_close():
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    closed = {"v": False}

    class FakeClient:
        def close(self):
            closed["v"] = True

    client = GraphClient.__new__(GraphClient)
    client._client = FakeClient()
    client.close()
    assert closed["v"] is True
