"""SNMPv3 USM 算法名称规范化。

采集任务历史值 ``sha`` / ``aes`` 分别表示 SHA-1 与 AES-128。
"""

from __future__ import annotations

SNMP_INTEGRITY_VALUES = ("md5", "sha", "sha224", "sha256", "sha384", "sha512")
SNMP_PRIVACY_VALUES = ("des", "aes", "aes256")

_INTEGRITY_ALIASES = {
    "md5": "md5",
    "sha": "sha",
    "sha1": "sha",
    "sha-1": "sha",
    "hmac-sha": "sha",
    "hmac-sha1": "sha",
    "sha224": "sha224",
    "sha-224": "sha224",
    "sha256": "sha256",
    "sha-256": "sha256",
    "sha384": "sha384",
    "sha-384": "sha384",
    "sha512": "sha512",
    "sha-512": "sha512",
}

_PRIVACY_ALIASES = {
    "des": "des",
    "aes": "aes",
    "aes128": "aes",
    "aes-128": "aes",
    "aes256": "aes256",
    "aes-256": "aes256",
}


def _canon(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def normalize_integrity(value: object) -> str | None:
    return _INTEGRITY_ALIASES.get(_canon(value))


def normalize_privacy(value: object) -> str | None:
    return _PRIVACY_ALIASES.get(_canon(value))
