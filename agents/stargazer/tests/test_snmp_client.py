import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _Pretty:
    def __init__(self, value):
        self.value = value

    def prettyPrint(self):
        return str(self.value)


class _FakeBackend:
    def __init__(self):
        self.get_result = (None, None, 0, [])
        self.walk_result = (None, None, 0, [])
        self.get_calls = []
        self.walk_calls = []

    def getCmd(self, *args, **kwargs):
        self.get_calls.append((args, kwargs))
        return self.get_result

    def nextCmd(self, *args, **kwargs):
        self.walk_calls.append((args, kwargs))
        return self.walk_result


class _FakeCmdgen:
    def __init__(self, backend):
        self.backend = backend
        self.community_calls = []
        self.usm_calls = []
        self.target_calls = []

    def CommandGenerator(self):
        return self.backend

    def CommunityData(self, community):
        self.community_calls.append(community)
        return ("community", community)

    def UsmUserData(self, username, **kwargs):
        self.usm_calls.append((username, kwargs))
        return ("usm", username, kwargs)

    def UdpTransportTarget(self, target, **kwargs):
        self.target_calls.append((target, kwargs))
        return ("target", target, kwargs)

    def MibVariable(self, oid):
        return ("oid", oid)


def _client(config, backend=None):
    from core.monitor.snmp_client import SnmpClient

    backend = backend or _FakeBackend()
    cmdgen = _FakeCmdgen(backend)
    protocols = {
        "sha": "SHA",
        "md5": "MD5",
        "aes": "AES",
        "des": "DES",
    }
    return (
        SnmpClient(config, cmdgen_module=cmdgen, protocols=protocols),
        backend,
        cmdgen,
    )


def test_v2c_get_uses_community_target_and_transport_limits():
    client, backend, cmdgen = _client(
        {
            "base_url": "udp://storage.example.com:2161",
            "community": "private",
            "timeout": 7,
            "retries": 3,
        }
    )
    backend.get_result = (
        None,
        None,
        0,
        [(_Pretty("1.3.6.1.2.1.1.3.0"), _Pretty("12345"))],
    )

    assert client.get("1.3.6.1.2.1.1.3.0") == "12345"
    assert cmdgen.community_calls == ["private"]
    assert cmdgen.target_calls == [(("storage.example.com", 2161), {"timeout": 7, "retries": 3})]


def test_v3_auth_priv_maps_credentials_and_protocols():
    client, backend, cmdgen = _client(
        {
            "host": "10.0.0.8",
            "username": "snmp-user",
            "auth_key": "auth-secret",
            "priv_key": "priv-secret",
            "auth_protocol": "MD5",
            "priv_protocol": "DES",
        }
    )
    backend.get_result = (
        None,
        None,
        0,
        [(_Pretty("1.3.6.1.2.1.1.1.0"), _Pretty("storage"))],
    )

    client.get("1.3.6.1.2.1.1.1.0")

    assert cmdgen.usm_calls == [
        (
            "snmp-user",
            {
                "authKey": "auth-secret",
                "authProtocol": "MD5",
                "privKey": "priv-secret",
                "privProtocol": "DES",
            },
        )
    ]


def test_walk_returns_full_dot_prefixed_oids_and_stops_at_subtree():
    client, backend, _ = _client({"host": "10.0.0.9", "community": "public"})
    backend.walk_result = (
        None,
        None,
        0,
        [
            [(_Pretty("1.3.6.1.4.1.9.1.1"), _Pretty("up"))],
            [(_Pretty(".1.3.6.1.4.1.9.1.2"), _Pretty("down"))],
        ],
    )

    assert client.walk("1.3.6.1.4.1.9.1") == {
        ".1.3.6.1.4.1.9.1.1": "up",
        ".1.3.6.1.4.1.9.1.2": "down",
    }
    assert backend.walk_calls[0][1]["lexicographicMode"] is False


def test_protocol_error_raises_collection_error():
    from core.monitor.snmp_client import SnmpCollectionError

    client, backend, _ = _client({"host": "10.0.0.10", "community": "public"})
    backend.get_result = (None, _Pretty("authorizationError"), 1, [])

    with pytest.raises(SnmpCollectionError, match="authorizationError"):
        client.get("1.3.6.1.2.1.1.1.0")


def test_v2c_does_not_silently_fall_back_to_public_community():
    client, _, _ = _client({"host": "10.0.0.12"})

    with pytest.raises(ValueError, match="community is required"):
        client.get("1.3.6.1.2.1.1.1.0")


def test_api_adapter_exposes_existing_get_and_walk_response_shapes():
    from core.monitor.snmp_client import SnmpApiAdapter

    client, backend, _ = _client({"host": "10.0.0.11", "community": "public"})
    backend.get_result = (
        None,
        None,
        0,
        [(_Pretty("1.3.6.1.2.1.1.1.0"), _Pretty("array"))],
    )
    backend.walk_result = (
        None,
        None,
        0,
        [[(_Pretty("1.3.6.1.2.1.2.2.1.1.1"), _Pretty("1"))]],
    )
    adapter = SnmpApiAdapter(client)

    assert adapter.request("GET", "/snmp/get", params={"oid": "1.3.6.1.2.1.1.1.0"}) == {"value": "array"}
    assert adapter.request("GET", "/snmp/walk", params={"oid": "1.3.6.1.2.1.2.2.1.1"}) == {"data": {".1.3.6.1.2.1.2.2.1.1.1": {"value": "1"}}}
