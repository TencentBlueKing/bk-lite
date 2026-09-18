import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.infra.snmp_usm import integrity_protocol, normalize_integrity, normalize_privacy, privacy_protocol  # noqa: E402


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sha", "sha"),
        ("SHA-1", "sha"),
        ("sha256", "sha256"),
        ("SHA-256", "sha256"),
        ("sha224", "sha224"),
        ("sha384", "sha384"),
        ("sha512", "sha512"),
        ("md5", "md5"),
        ("nope", None),
    ],
)
def test_normalize_integrity_aliases(raw, expected):
    assert normalize_integrity(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aes", "aes"),
        ("AES-128", "aes"),
        ("aes256", "aes256"),
        ("AES-256", "aes256"),
        ("des", "des"),
        ("nope", None),
    ],
)
def test_normalize_privacy_aliases(raw, expected):
    assert normalize_privacy(raw) == expected


def test_integrity_protocol_maps_sha_family_to_distinct_oids():
    sha1 = integrity_protocol("sha")
    sha256 = integrity_protocol("SHA-256")
    sha224 = integrity_protocol("sha224")
    assert sha1 is not None
    assert sha256 is not None
    assert sha1 != sha256
    assert sha224 != sha256
    assert integrity_protocol("unknown") is None


def test_privacy_protocol_maps_aes128_and_aes256_to_distinct_oids():
    aes128 = privacy_protocol("aes")
    aes256 = privacy_protocol("aes256")
    assert aes128 is not None
    assert aes256 is not None
    assert aes128 != aes256
    assert privacy_protocol("aes") == privacy_protocol("AES-128")


def test_snmp_facts_canonicalizes_sha256_aes256_and_legacy_sha():
    from plugins.inputs.network.snmp_facts import SnmpFacts

    modern = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v3",
            "username": "u",
            "level": "authPriv",
            "integrity": "SHA-256",
            "authkey": "authkey1",
            "privacy": "aes256",
            "privkey": "privkey1",
        }
    )
    assert modern.integrity == "sha256"
    assert modern.privacy == "aes256"
    assert modern._get_integrity_proto() == integrity_protocol("sha256")
    assert modern._get_privacy_proto() == privacy_protocol("aes256")

    legacy = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v3",
            "username": "u",
            "level": "authPriv",
            "integrity": "sha",
            "authkey": "authkey1",
            "privacy": "AES",
            "privkey": "privkey1",
        }
    )
    assert (legacy.integrity, legacy.privacy) == ("sha", "aes")
    assert legacy._get_integrity_proto() == integrity_protocol("SHA-1")
    assert modern._get_snmp_auth().authProtocol == integrity_protocol("sha256")
    assert modern._get_snmp_auth().privProtocol == privacy_protocol("aes256")


def test_snmp_facts_rejects_unknown_integrity():
    from plugins.inputs.network.snmp_facts import SnmpFacts

    with pytest.raises(ValueError, match="Authentication algorithm"):
        SnmpFacts(
            {
                "host": "127.0.0.1",
                "version": "v3",
                "username": "u",
                "level": "authNoPriv",
                "integrity": "blake2",
                "authkey": "authkey1",
            }
        )


def test_snmp_topo_auth_maps_sha256_aes256_and_rejects_unknown():
    from plugins.inputs.network_topo.snmp_topo import SnmpAuth

    modern = SnmpAuth(
        version="v3",
        username="u",
        level="authpriv",
        integrity="SHA-256",
        privacy="AES-256",
        authkey="authkey1",
        privkey="privkey1",
    )
    usm = modern.auth()
    assert modern.integrity == "sha256"
    assert modern.privacy == "aes256"
    assert usm.authProtocol == integrity_protocol("sha256")
    assert usm.privProtocol == privacy_protocol("aes256")
    assert usm.authProtocol != integrity_protocol("sha")
    assert usm.privProtocol != privacy_protocol("aes")

    with pytest.raises(Exception, match="Privacy algorithm"):
        SnmpAuth(
            version="v3",
            username="u",
            level="authPriv",
            integrity="sha256",
            privacy="blake2",
            authkey="authkey1",
            privkey="privkey1",
        )
