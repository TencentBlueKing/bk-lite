"""Synchronous SNMP client used by Stargazer monitor collectors."""

from urllib.parse import urlsplit


class SnmpCollectionError(RuntimeError):
    """Raised when an SNMP transport or protocol operation fails."""


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_protocol(value, default):
    normalized = str(value or default).strip().lower()
    return normalized


def _parse_target(config):
    raw_target = config.get("host") or config.get("base_url") or config.get("ip") or ""
    raw_target = str(raw_target).strip()
    if not raw_target:
        raise ValueError("SNMP target host is required")

    parsed = urlsplit(raw_target if "://" in raw_target else f"//{raw_target}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"Invalid SNMP target: {raw_target!r}")

    configured_port = config.get("port") or config.get("snmp_port")
    port = _as_int(configured_port or parsed.port, 161)
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid SNMP port: {port}")
    return host, port


class SnmpClient:
    """Small pysnmp wrapper supporting v2c and v3 GET/WALK operations."""

    def __init__(
        self,
        config,
        *,
        cmdgen_module=None,
        protocols=None,
    ):
        self.config = dict(config or {})
        self.host, self.port = _parse_target(self.config)
        self.timeout = _as_int(self.config.get("timeout"), 5)
        self.retries = _as_int(self.config.get("retries"), 1)

        if cmdgen_module is None:
            from pysnmp.entity.rfc3413.oneliner import cmdgen

            cmdgen_module = cmdgen
        if protocols is None:
            from pysnmp.hlapi import (
                usmAesCfb128Protocol,
                usmDESPrivProtocol,
                usmHMACMD5AuthProtocol,
                usmHMACSHAAuthProtocol,
            )

            protocols = {
                "sha": usmHMACSHAAuthProtocol,
                "md5": usmHMACMD5AuthProtocol,
                "aes": usmAesCfb128Protocol,
                "des": usmDESPrivProtocol,
            }

        self._cmdgen = cmdgen_module
        self._protocols = protocols
        self._command_generator = self._cmdgen.CommandGenerator()

    def _auth(self):
        username = self.config.get("username") or self.config.get("sec_name")
        explicit_version = str(self.config.get("version") or "").lower()
        use_v3 = explicit_version in {"3", "v3"} or bool(username)
        if not use_v3:
            community = self.config.get("community")
            if not community:
                raise ValueError("SNMP v2c community is required")
            return self._cmdgen.CommunityData(community)

        if not username:
            raise ValueError("SNMP v3 username is required")

        auth_key = self.config.get("auth_key") or self.config.get("authkey")
        priv_key = self.config.get("priv_key") or self.config.get("privkey")
        level = self.config.get("sec_level") or self.config.get("level")
        if not level:
            level = "authPriv" if priv_key else "authNoPriv" if auth_key else "noAuthNoPriv"
        level = str(level)
        kwargs = {}
        if level != "noAuthNoPriv":
            if not auth_key:
                raise ValueError(f"SNMP v3 {level} requires auth_key")
            auth_protocol = _normalize_protocol(
                self.config.get("auth_protocol") or self.config.get("integrity"),
                "sha",
            )
            if auth_protocol not in {"sha", "md5"}:
                raise ValueError(f"Unsupported SNMP auth protocol: {auth_protocol}")
            kwargs.update(
                authKey=auth_key,
                authProtocol=self._protocols[auth_protocol],
            )
        if level == "authPriv":
            if not priv_key:
                raise ValueError("SNMP v3 authPriv requires priv_key")
            priv_protocol = _normalize_protocol(
                self.config.get("priv_protocol") or self.config.get("privacy"),
                "aes",
            )
            if priv_protocol not in {"aes", "des"}:
                raise ValueError(f"Unsupported SNMP privacy protocol: {priv_protocol}")
            kwargs.update(
                privKey=priv_key,
                privProtocol=self._protocols[priv_protocol],
            )
        return self._cmdgen.UsmUserData(username, **kwargs)

    def _target(self):
        return self._cmdgen.UdpTransportTarget(
            (self.host, self.port),
            timeout=self.timeout,
            retries=self.retries,
        )

    @staticmethod
    def _pretty(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        pretty_print = getattr(value, "prettyPrint", None)
        return pretty_print() if callable(pretty_print) else value

    @staticmethod
    def _raise_on_error(error_indication, error_status, error_index):
        if error_indication:
            raise SnmpCollectionError(str(error_indication))
        if error_status:
            pretty_print = getattr(error_status, "prettyPrint", None)
            message = pretty_print() if callable(pretty_print) else str(error_status)
            raise SnmpCollectionError(f"{message} at index {error_index}")

    def get(self, oid):
        result = self._command_generator.getCmd(
            self._auth(),
            self._target(),
            self._cmdgen.MibVariable(str(oid).lstrip(".")),
            lookupMib=False,
        )
        error_indication, error_status, error_index, var_binds = result
        self._raise_on_error(error_indication, error_status, error_index)
        if not var_binds:
            return None
        return self._pretty(var_binds[0][1])

    def walk(self, base_oid):
        result = self._command_generator.nextCmd(
            self._auth(),
            self._target(),
            self._cmdgen.MibVariable(str(base_oid).lstrip(".")),
            lookupMib=False,
            lexicographicMode=False,
        )
        error_indication, error_status, error_index, var_bind_table = result
        self._raise_on_error(error_indication, error_status, error_index)

        values = {}
        for var_binds in var_bind_table or []:
            for oid, value in var_binds:
                oid_text = str(self._pretty(oid)).lstrip(".")
                values[f".{oid_text}"] = self._pretty(value)
        return values


class SnmpApiAdapter:
    """Compatibility adapter for existing storage monitor request calls."""

    def __init__(self, client):
        self.client = client

    def request(self, method, endpoint, params=None, **_kwargs):
        if str(method).upper() != "GET":
            raise ValueError(f"Unsupported SNMP adapter method: {method}")
        oid = (params or {}).get("oid")
        if not oid:
            raise ValueError("SNMP oid is required")
        if endpoint == "/snmp/get":
            return {"value": self.client.get(oid)}
        if endpoint == "/snmp/walk":
            return {"data": {full_oid: {"value": value} for full_oid, value in self.client.walk(oid).items()}}
        raise ValueError(f"Unsupported SNMP adapter endpoint: {endpoint}")

    def logout(self):
        return None
