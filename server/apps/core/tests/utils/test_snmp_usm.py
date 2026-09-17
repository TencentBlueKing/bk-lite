import pytest

from apps.core.utils.snmp_usm import normalize_integrity, normalize_privacy

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sha", "sha"),
        ("SHA", "sha"),
        ("SHA-1", "sha"),
        ("sha256", "sha256"),
        ("SHA-256", "sha256"),
        ("sha-384", "sha384"),
        ("MD5", "md5"),
        ("unknown", None),
    ],
)
def test_normalize_integrity_aliases(raw, expected):
    assert normalize_integrity(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aes", "aes"),
        ("AES", "aes"),
        ("AES-128", "aes"),
        ("aes256", "aes256"),
        ("AES-256", "aes256"),
        ("DES", "des"),
        ("unknown", None),
    ],
)
def test_normalize_privacy_aliases(raw, expected):
    assert normalize_privacy(raw) == expected
