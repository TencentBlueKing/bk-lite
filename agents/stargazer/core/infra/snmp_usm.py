"""SNMPv3 USM 认证/加密算法名称映射。

采集任务历史值 ``sha`` / ``aes`` 分别表示 SHA-1 与 AES-128。
网络设备采集、拓扑采集和连通性探测共用这里的协议对象，避免静默回落到 MD5/DES。
"""

from __future__ import annotations

INTEGRITY_CHOICES = ("sha", "sha224", "sha256", "sha384", "sha512", "md5")
PRIVACY_CHOICES = ("aes", "aes256", "des")
SUPPORTED_INTEGRITY = set(INTEGRITY_CHOICES)
SUPPORTED_PRIVACY = set(PRIVACY_CHOICES)

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

_LEVEL_ALIASES = {
    "noauthnopriv": "noAuthNoPriv",
    "authnopriv": "authNoPriv",
    "authpriv": "authPriv",
}


def _canon(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def normalize_integrity(value: object) -> str | None:
    return _INTEGRITY_ALIASES.get(_canon(value))


def normalize_privacy(value: object) -> str | None:
    return _PRIVACY_ALIASES.get(_canon(value))


def normalize_security_level(value: object, default: str | None = "authPriv") -> str | None:
    raw = value if value not in (None, "") else default
    if raw in (None, ""):
        return None
    return _LEVEL_ALIASES.get(str(raw).strip().lower())


def _load_protocol_maps() -> tuple[dict, dict]:
    from pysnmp.hlapi import (
        usmAesCfb128Protocol,
        usmAesCfb256Protocol,
        usmDESPrivProtocol,
        usmHMAC128SHA224AuthProtocol,
        usmHMAC192SHA256AuthProtocol,
        usmHMAC256SHA384AuthProtocol,
        usmHMAC384SHA512AuthProtocol,
        usmHMACMD5AuthProtocol,
        usmHMACSHAAuthProtocol,
    )

    return (
        {
            "md5": usmHMACMD5AuthProtocol,
            "sha": usmHMACSHAAuthProtocol,
            "sha224": usmHMAC128SHA224AuthProtocol,
            "sha256": usmHMAC192SHA256AuthProtocol,
            "sha384": usmHMAC256SHA384AuthProtocol,
            "sha512": usmHMAC384SHA512AuthProtocol,
        },
        {
            "des": usmDESPrivProtocol,
            "aes": usmAesCfb128Protocol,
            "aes256": usmAesCfb256Protocol,
        },
    )


def default_protocol_map() -> dict:
    auth_map, priv_map = _load_protocol_maps()
    return {**auth_map, **priv_map}


def integrity_protocol(value: object):
    canonical = normalize_integrity(value)
    if canonical is None:
        return None
    auth_map, _ = _load_protocol_maps()
    return auth_map.get(canonical)


def privacy_protocol(value: object):
    canonical = normalize_privacy(value)
    if canonical is None:
        return None
    _, priv_map = _load_protocol_maps()
    return priv_map.get(canonical)


def v3_usm_kwargs(*, level, integrity, privacy, authkey, privkey) -> dict:
    """Build UsmUserData kwargs for SNMPv3. Empty dict means noAuthNoPriv."""
    canonical_level = normalize_security_level(level)
    if canonical_level not in {"noAuthNoPriv", "authNoPriv", "authPriv"}:
        raise ValueError("Invalid SNMP security level.")
    if canonical_level == "noAuthNoPriv":
        return {}
    auth_proto = integrity_protocol(integrity)
    if auth_proto is None or len(str(authkey or "")) < 8:
        raise ValueError("Authentication algorithm and an authkey of at least 8 characters are required.")
    kwargs = {"authKey": authkey, "authProtocol": auth_proto}
    if canonical_level != "authPriv":
        return kwargs
    priv_proto = privacy_protocol(privacy)
    if priv_proto is None or len(str(privkey or "")) < 8:
        raise ValueError("Privacy algorithm and a privkey of at least 8 characters are required.")
    kwargs.update(privKey=privkey, privProtocol=priv_proto)
    return kwargs
